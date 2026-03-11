from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TMP_DIRNAME = ".literature_explainer_tmp"
SOURCE_MD_FILENAME = "source.md"
SOURCE_META_FILENAME = "source_meta.json"
PDF_SIGNATURE = b"%PDF-"
HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
REFERENCES_RE = re.compile(r"\b(references|bibliography)\b|参考文献", re.IGNORECASE)
LITERAL_STRING_RE = re.compile(r"\((?:\\.|[^\\)])*\)")
TJ_ARRAY_RE = re.compile(r"\[(.*?)\]\s*TJ", re.DOTALL)
TJ_SINGLE_RE = re.compile(r"(\((?:\\.|[^\\)])*\))\s*Tj")
TEXT_BLOCK_RE = re.compile(r"BT(.*?)ET", re.DOTALL)


@dataclass
class DispatchPaths:
    paper_key: str
    source_md_path: Path
    source_meta_path: Path


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_paths(paper_key: str) -> DispatchPaths:
    tmp_dir = Path.cwd() / TMP_DIRNAME / paper_key
    return DispatchPaths(
        paper_key=paper_key,
        source_md_path=tmp_dir / SOURCE_MD_FILENAME,
        source_meta_path=tmp_dir / SOURCE_META_FILENAME,
    )


def input_hash_from_bytes(source_bytes: bytes) -> str:
    return "sha256:" + hashlib.sha256(source_bytes).hexdigest()


def paper_key_from_input_hash(input_hash: str) -> str:
    digest = input_hash.split(":", 1)[-1]
    return digest[:16]


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _detect_source_type(source_path: Path) -> tuple[str | None, str | None, str | None]:
    try:
        head = source_path.read_bytes()[:8]
    except Exception as exc:  # noqa: BLE001
        return None, None, f"read source failed: {exc}"

    if head.startswith(PDF_SIGNATURE):
        return "pdf", "pdf_signature", None

    try:
        source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, None, "input is neither PDF signature nor UTF-8 text"
    except Exception as exc:  # noqa: BLE001
        return None, None, f"read source as utf-8 failed: {exc}"

    return "markdown", "utf8_text", None


def _extension_warning(source_path: Path, source_type: str) -> list[str]:
    suffix = source_path.suffix.lower()
    if not suffix:
        return []
    if source_type == "pdf" and suffix != ".pdf":
        return [f"source_path extension '{suffix}' ignored; content detected as PDF"]
    if source_type == "markdown" and suffix not in (".md", ".markdown", ".txt"):
        return [f"source_path extension '{suffix}' ignored; content detected as UTF-8 text"]
    return []


def _quality_metrics(markdown_text: str) -> dict[str, int]:
    lines = markdown_text.splitlines()
    return {
        "char_count": len(markdown_text),
        "non_empty_lines": sum(1 for line in lines if line.strip()),
        "heading_lines": sum(1 for line in lines if HEADING_RE.search(line)),
        "references_keyword_hits": len(REFERENCES_RE.findall(markdown_text)),
    }


def _convert_markdown_source(source_path: Path) -> str:
    return source_path.read_text(encoding="utf-8")


def _convert_pdf_with_pymupdf4llm(source_path: Path) -> str:
    try:
        import pymupdf4llm  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"pymupdf4llm unavailable: {exc}") from exc

    try:
        markdown = pymupdf4llm.to_markdown(str(source_path))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"pymupdf4llm conversion failed: {exc}") from exc

    if isinstance(markdown, bytes):
        markdown = markdown.decode("utf-8", errors="replace")
    elif not isinstance(markdown, str):
        markdown = str(markdown)

    normalized = markdown.strip()
    if not normalized:
        raise RuntimeError("pymupdf4llm returned empty markdown")
    return normalized + "\n"


def _decode_pdf_literal(token: str) -> str:
    assert token.startswith("(") and token.endswith(")")
    body = token[1:-1]
    chars: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            chars.append(char)
            index += 1
            continue
        if index + 1 >= len(body):
            break
        nxt = body[index + 1]
        if nxt in "()\\":
            chars.append(nxt)
            index += 2
            continue
        if nxt == "n":
            chars.append("\n")
            index += 2
            continue
        if nxt == "r":
            chars.append("\r")
            index += 2
            continue
        if nxt == "t":
            chars.append("\t")
            index += 2
            continue
        if nxt == "b":
            chars.append("\b")
            index += 2
            continue
        if nxt == "f":
            chars.append("\f")
            index += 2
            continue
        if nxt.isdigit():
            octal = nxt
            step = 2
            while index + step < len(body) and len(octal) < 3 and body[index + step].isdigit():
                octal += body[index + step]
                step += 1
            chars.append(chr(int(octal, 8)))
            index += step
            continue
        chars.append(nxt)
        index += 2
    return "".join(chars)


def _extract_text_from_pdf_stream(stream_bytes: bytes) -> str:
    stripped = stream_bytes.strip(b"\r\n")
    decoded_candidates: list[bytes] = [stripped]
    try:
        decoded_candidates.insert(0, zlib.decompress(stripped))
    except Exception:  # noqa: BLE001
        pass

    extracted_blocks: list[str] = []
    for candidate in decoded_candidates:
        try:
            text = candidate.decode("latin-1", errors="ignore")
        except Exception:  # noqa: BLE001
            continue

        text_blocks = TEXT_BLOCK_RE.findall(text) or [text]
        for block in text_blocks:
            fragments: list[str] = []
            for array_match in TJ_ARRAY_RE.finditer(block):
                fragments.extend(_decode_pdf_literal(item) for item in LITERAL_STRING_RE.findall(array_match.group(1)))
            for single_match in TJ_SINGLE_RE.finditer(block):
                fragments.append(_decode_pdf_literal(single_match.group(1)))
            if not fragments:
                fragments.extend(_decode_pdf_literal(item) for item in LITERAL_STRING_RE.findall(block))
            cleaned = " ".join(part.strip() for part in fragments if part.strip()).strip()
            if cleaned:
                extracted_blocks.append(cleaned)

        if extracted_blocks:
            break

    return "\n\n".join(extracted_blocks)


def _convert_pdf_with_stdlib(source_path: Path) -> str:
    pdf_bytes = source_path.read_bytes()
    stream_pattern = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
    text_parts: list[str] = []
    for match in stream_pattern.finditer(pdf_bytes):
        extracted = _extract_text_from_pdf_stream(match.group(1))
        if extracted:
            text_parts.append(extracted)

    if not text_parts:
        raise RuntimeError("stdlib fallback could not recover any text from PDF streams")

    deduped: list[str] = []
    seen: set[str] = set()
    for part in text_parts:
        normalized = part.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    markdown = "\n\n".join(deduped).strip()
    if not markdown:
        raise RuntimeError("stdlib fallback produced empty markdown")
    return markdown + "\n"


def dispatch_source(
    source_path: Path,
    *,
    output_paths: DispatchPaths | None = None,
    disable_pymupdf4llm: bool = False,
) -> tuple[dict[str, Any], int]:
    warnings: list[str] = []

    if not source_path.exists():
        paths = output_paths or DispatchPaths(
            paper_key="",
            source_md_path=Path.cwd() / TMP_DIRNAME / SOURCE_MD_FILENAME,
            source_meta_path=Path.cwd() / TMP_DIRNAME / SOURCE_META_FILENAME,
        )
        error = {"code": "FILE_NOT_FOUND", "message": f"source_path not found: {source_path}"}
        missing_payload = {
            "paper_key": "",
            "input_hash": "",
            "source_md_path": str(paths.source_md_path),
            "source_meta_path": str(paths.source_meta_path),
            "warnings": warnings,
            "error": error,
        }
        missing_meta = {
            "generated_at": utc_now_iso(),
            "source_path": str(source_path),
            "input_hash": "",
            "paper_key": "",
            "source_type": "",
            "detection_method": "",
            "conversion_backend": "",
            "fallback_reason": "",
            "quality": {
                "char_count": 0,
                "non_empty_lines": 0,
                "heading_lines": 0,
                "references_keyword_hits": 0,
            },
            "error": error,
        }
        _write_json(paths.source_meta_path, missing_meta)
        return missing_payload, 2

    source_bytes = source_path.read_bytes()
    input_hash = input_hash_from_bytes(source_bytes)
    paper_key = paper_key_from_input_hash(input_hash)
    paths = output_paths or default_paths(paper_key)

    meta: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "source_path": str(source_path),
        "input_hash": input_hash,
        "paper_key": paper_key,
        "source_type": "",
        "detection_method": "",
        "conversion_backend": "",
        "fallback_reason": "",
        "quality": {
            "char_count": 0,
            "non_empty_lines": 0,
            "heading_lines": 0,
            "references_keyword_hits": 0,
        },
        "error": None,
    }

    payload: dict[str, Any] = {
        "paper_key": paper_key,
        "input_hash": input_hash,
        "source_md_path": str(paths.source_md_path),
        "source_meta_path": str(paths.source_meta_path),
        "warnings": warnings,
        "error": None,
    }

    source_type, detection_method, detect_error = _detect_source_type(source_path)
    if detect_error is not None or source_type is None or detection_method is None:
        error = {"code": "UNSUPPORTED_INPUT", "message": detect_error or "unable to detect source format"}
        meta["error"] = error
        payload["error"] = error
        _write_json(paths.source_meta_path, meta)
        return payload, 2

    warnings.extend(_extension_warning(source_path, source_type))
    meta["source_type"] = source_type
    meta["detection_method"] = detection_method

    try:
        if source_type == "markdown":
            markdown = _convert_markdown_source(source_path)
            meta["conversion_backend"] = "direct_copy"
        else:
            warnings.append("source input detected as PDF")
            markdown = ""
            fallback_reason = ""
            if disable_pymupdf4llm:
                fallback_reason = "pymupdf4llm disabled by environment"
            else:
                try:
                    markdown = _convert_pdf_with_pymupdf4llm(source_path)
                    meta["conversion_backend"] = "pymupdf4llm"
                except Exception as exc:  # noqa: BLE001
                    fallback_reason = str(exc)
            if not markdown:
                warnings.append("PDF conversion fell back to stdlib text extraction")
                warnings.append("fallback markdown quality may be low for multi-column/layout-heavy PDFs")
                markdown = _convert_pdf_with_stdlib(source_path)
                meta["conversion_backend"] = "stdlib_fallback"
                meta["fallback_reason"] = fallback_reason
    except Exception as exc:  # noqa: BLE001
        error = {"code": "CONVERT_FAILED", "message": str(exc)}
        meta["error"] = error
        payload["error"] = error
        _write_json(paths.source_meta_path, meta)
        return payload, 2

    _write_text(paths.source_md_path, markdown)
    meta["quality"] = _quality_metrics(markdown)
    _write_json(paths.source_meta_path, meta)
    return payload, 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch source input to normalized markdown for literature-digest.")
    parser.add_argument("--source-path", required=True, help="Path to the original input file (markdown or PDF).")
    parser.add_argument("--out-md", default="", help="Optional output markdown path.")
    parser.add_argument("--out-meta", default="", help="Optional output metadata path.")
    args = parser.parse_args()

    output_paths: DispatchPaths | None = None
    if Path(args.source_path).exists():
        source_bytes = Path(args.source_path).read_bytes()
        defaults = default_paths(paper_key_from_input_hash(input_hash_from_bytes(source_bytes)))
        output_paths = DispatchPaths(
            paper_key=defaults.paper_key,
            source_md_path=Path(args.out_md) if args.out_md else defaults.source_md_path,
            source_meta_path=Path(args.out_meta) if args.out_meta else defaults.source_meta_path,
        )
    elif args.out_md and args.out_meta:
        output_paths = DispatchPaths(
            paper_key="",
            source_md_path=Path(args.out_md),
            source_meta_path=Path(args.out_meta),
        )
    payload, code = dispatch_source(
        Path(args.source_path),
        output_paths=output_paths,
        disable_pymupdf4llm=bool(os.environ.get("LITERATURE_DIGEST_DISABLE_PYMUPDF4LLM")),
    )
    print(json.dumps(payload, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
