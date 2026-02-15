from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable


_WORKS_CITED_HEADING = "#### **Works cited**"


@dataclass(frozen=True)
class CandidateMeta:
    citekey: str
    title: str
    year: str | None
    authors: list[str]
    doi: str | None
    url: str | None


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _find_works_cited_heading(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line.strip() == _WORKS_CITED_HEADING:
            return i
    raise ValueError(f"Works cited heading not found: {_WORKS_CITED_HEADING!r}")


def _build_matched_map(match_result: dict[str, Any]) -> dict[str, str]:
    refs = match_result.get("refs")
    if not isinstance(refs, list):
        raise ValueError("match_result.json missing refs[]")

    out: dict[str, str] = {}
    for r in refs:
        if not isinstance(r, dict):
            continue
        ref_id = str(r.get("ref_id") or "").strip()
        match = r.get("match")
        if not ref_id or not isinstance(match, dict):
            continue
        if match.get("status") != "matched":
            continue
        citekey = str(match.get("citekey") or "").strip()
        if not citekey:
            continue
        out[ref_id] = citekey
    return out


def _iter_candidate_objects(match_result: dict[str, Any]) -> Iterable[dict[str, Any]]:
    refs = match_result.get("refs")
    if not isinstance(refs, list):
        return
    for r in refs:
        if not isinstance(r, dict):
            continue
        candidates = r.get("candidates")
        if not isinstance(candidates, list):
            continue
        for c in candidates:
            if isinstance(c, dict):
                yield c


def _build_candidate_meta_by_citekey(match_result: dict[str, Any]) -> dict[str, CandidateMeta]:
    out: dict[str, CandidateMeta] = {}
    for c in _iter_candidate_objects(match_result):
        citekey = str(c.get("citekey") or "").strip()
        if not citekey or citekey in out:
            continue
        title = str(c.get("title") or "").strip()
        year_raw = c.get("year")
        year = str(year_raw).strip() if year_raw is not None and str(year_raw).strip() else None
        authors_raw = c.get("authors")
        authors = [str(a).strip() for a in authors_raw] if isinstance(authors_raw, list) else []
        authors = [a for a in authors if a]
        doi_raw = c.get("doi")
        doi = str(doi_raw).strip() if doi_raw is not None and str(doi_raw).strip() else None
        url_raw = c.get("url")
        url = str(url_raw).strip() if url_raw is not None and str(url_raw).strip() else None

        out[citekey] = CandidateMeta(
            citekey=citekey,
            title=title,
            year=year,
            authors=authors,
            doi=doi,
            url=url,
        )
    return out


def _family_and_initials(author: str) -> tuple[str, str]:
    text = author.strip()
    if not text:
        return "", ""
    if "," in text:
        family, given = (p.strip() for p in text.split(",", 1))
    else:
        parts = [p for p in re.split(r"\s+", text) if p]
        if len(parts) == 1:
            return parts[0], ""
        family, given = parts[-1], " ".join(parts[:-1])

    initials = ""
    for token in re.split(r"[\s\-]+", given):
        t = re.sub(r"[^A-Za-z]", "", token)
        if not t:
            continue
        initials += t[0].upper() + "."
    return family, initials


def _format_authors_harvard(authors: list[str]) -> tuple[str, str]:
    if not authors:
        return "Anon.", "anon."

    families_and_initials = [_family_and_initials(a) for a in authors]
    families_and_initials = [(f, i) for f, i in families_and_initials if f]
    if not families_and_initials:
        return "Anon.", "anon."

    first_family = families_and_initials[0][0]
    first_sort_key = first_family.lower()

    def fmt_one(f: str, i: str) -> str:
        if i:
            return f"{f}, {i}"
        return f

    if len(families_and_initials) == 1:
        return fmt_one(*families_and_initials[0]), first_sort_key
    if len(families_and_initials) == 2:
        a1 = fmt_one(*families_and_initials[0])
        a2 = fmt_one(*families_and_initials[1])
        return f"{a1} and {a2}", first_sort_key

    a1 = fmt_one(*families_and_initials[0])
    return f"{a1} et al.", first_sort_key


def _format_reference_entry(meta: CandidateMeta) -> tuple[str, str, int | None, str]:
    authors_text, author_sort = _format_authors_harvard(meta.authors)
    year_text = meta.year.strip() if meta.year and meta.year.strip() else "n.d."
    title = meta.title.strip() if meta.title.strip() else "Untitled"

    year_num: int | None
    try:
        year_num = int(year_text) if year_text.isdigit() else None
    except Exception:
        year_num = None

    if meta.doi:
        body = f"{authors_text} ({year_text}) '{title}'. doi: {meta.doi}."
    elif meta.url:
        body = f"{authors_text} ({year_text}) '{title}'. Available at: {meta.url}."
    else:
        body = f"{authors_text} ({year_text}) '{title}'."

    line = f"- {body} [[{meta.citekey}]]"
    return line, author_sort, year_num, title.lower()


def _build_reference_section(unique_citekeys: list[str], meta_by_citekey: dict[str, CandidateMeta]) -> list[str]:
    entries: list[tuple[str, str, int | None, str]] = []
    for ck in unique_citekeys:
        meta = meta_by_citekey.get(ck)
        if meta is None:
            meta = CandidateMeta(citekey=ck, title="Untitled", year=None, authors=[], doi=None, url=None)
        entries.append(_format_reference_entry(meta))

    def sort_key(item: tuple[str, str, int | None, str]) -> tuple[int, str, int, str]:
        _, author_sort, year_num, title_sort = item
        anon = 1 if author_sort == "anon." else 0
        year_sort = year_num if year_num is not None else 9999
        return (anon, author_sort, year_sort, title_sort)

    entries.sort(key=sort_key)
    lines: list[str] = ["#### **Reference**", ""]
    lines.extend([e[0] for e in entries])
    lines.append("")
    return lines


def _append_links_in_works_cited(lines: list[str], works_idx: int, matched: dict[str, str]) -> None:
    entry_re = re.compile(r"^\s*(\d{1,3})\.\s+")

    starts: list[tuple[int, str]] = []
    for i in range(works_idx + 1, len(lines)):
        m = entry_re.match(lines[i])
        if m:
            starts.append((i, m.group(1)))

    if not starts:
        return

    starts.append((len(lines), "__END__"))
    for (start_i, ref_id), (next_i, _) in zip(starts, starts[1:]):
        citekey = matched.get(ref_id)
        if not citekey:
            continue
        end_i = next_i - 1
        if end_i < start_i:
            continue
        marker = f"[[{citekey}]]"
        if marker in lines[end_i]:
            continue
        lines[end_i] = lines[end_i].rstrip() + f" {marker}"


_CITATION_LINE_SKIP = re.compile(r"^\s*(?:#|\d+\.|\|)")
_CITATION_GROUP = re.compile(
    r"(?P<prefix>\s)"
    r"(?P<seq>\d{1,3}(?:\s*[,，]\s*\d{1,3})*)"
    r"(?P<suffix>[。！？?；;：:\)\]）])"
)


def _replace_in_body(lines: list[str], works_idx: int, matched: dict[str, str]) -> None:
    def replace_group(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        seq = match.group("seq")
        suffix = match.group("suffix")

        parts = re.split(r"(\s*[,，]\s*)", seq)
        out_parts: list[str] = []
        for part in parts:
            if not part:
                continue
            if re.fullmatch(r"\s*[,，]\s*", part):
                out_parts.append(part)
                continue
            num = part.strip()
            ck = matched.get(num)
            out_parts.append(f"[[{ck}]]" if ck else num)
        return prefix + "".join(out_parts) + suffix

    for i in range(0, works_idx):
        line = lines[i]
        if _CITATION_LINE_SKIP.match(line):
            continue
        lines[i] = _CITATION_GROUP.sub(replace_group, line)


def process_gemini_dr(doc_path: str, match_result_path: str) -> str:
    match_result = _load_json(match_result_path)
    matched = _build_matched_map(match_result)

    with open(doc_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    works_idx = _find_works_cited_heading(lines)

    _replace_in_body(lines, works_idx, matched)
    _append_links_in_works_cited(lines, works_idx, matched)

    unique_citekeys: list[str] = []
    seen: set[str] = set()
    for ref_id, citekey in matched.items():
        if citekey not in seen:
            unique_citekeys.append(citekey)
            seen.add(citekey)

    meta_by_citekey = _build_candidate_meta_by_citekey(match_result)
    ref_section = _build_reference_section(unique_citekeys, meta_by_citekey)

    lines = lines[:works_idx] + ref_section + lines[works_idx:]
    return "\n".join(lines) + "\n"


def _default_output_path(doc_path: str) -> str:
    base, ext = os.path.splitext(doc_path)
    if not ext:
        ext = ".md"
    return f"{base}_processed{ext}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gemini-dr-link")
    p.add_argument("--doc-path", required=True)
    p.add_argument("--match-result", required=True)
    p.add_argument("--output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_path = args.output or _default_output_path(args.doc_path)
    content = process_gemini_dr(args.doc_path, args.match_result)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
