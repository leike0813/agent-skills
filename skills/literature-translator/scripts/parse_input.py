#!/usr/bin/env python3
"""
parse_input.py — Input type detection and normalization for literature-translator.

Detects file type from extension or directory structure, validates accessibility,
normalizes to Markdown, and outputs metadata JSON.

This script does NOT perform semantic analysis or translation.
"""
import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path


SUPPORTED_EXTENSIONS = {".md", ".pdf", ".tex"}
TEXT_LIKE_EXTENSIONS = {".md", ".txt", ""}
LATEX_DIRECTORY_MARKERS = {".tex", ".bib", ".cls", ".sty"}


def classify_input(path: Path) -> dict:
    """Classify the input path and return metadata."""
    if not path.exists():
        return {"error": f"path does not exist: {path}"}

    if path.is_dir():
        return classify_directory(path)

    ext = path.suffix.lower()
    if ext in SUPPORTED_EXTENSIONS or ext == "" or ext == ".txt":
        return classify_file(path, ext)

    return {"error": f"unsupported file extension: {ext}"}


def classify_directory(path: Path) -> dict:
    """Classify a directory input — look for LaTeX project."""
    tex_files = []
    for f in path.iterdir():
        if f.is_file() and f.suffix.lower() == ".tex":
            tex_files.append(f)

    if not tex_files:
        all_files = [f.name for f in path.iterdir() if f.is_file()]
        return {"error": f"no .tex files found in directory; files: {all_files}"}

    # Try to find main file (one that begins with \documentclass)
    main_candidates = []
    for f in tex_files:
        content = f.read_text(encoding="utf-8", errors="replace")
        if re.search(r'\\documentclass(\[.*?\])?\{', content):
            main_candidates.append(f)

    main_file = main_candidates[0] if len(main_candidates) == 1 else tex_files[0]
    if len(main_candidates) > 1:
        main_file = main_candidates[0]  # take first with documentclass

    return {
        "type": "latex_directory",
        "main_file": str(main_file.resolve()),
        "directory": str(path.resolve()),
        "tex_files": [str(f.resolve()) for f in tex_files],
    }


def classify_file(path: Path, ext: str) -> dict:
    """Classify a single file input."""
    # Try to read first bytes to validate
    try:
        with open(path, "rb") as f:
            header = f.read(512)
    except OSError as e:
        return {"error": f"cannot read file: {e}"}

    # Check if binary
    if is_binary(header):
        if ext == ".pdf":
            return {
                "type": "pdf",
                "path": str(path.resolve()),
                "note": "PDF extraction requires external tool (e.g., mineru)",
            }
        return {"error": f"binary file not supported: {ext}"}

    # Text file
    try:
        text = header.decode("utf-8")
    except UnicodeDecodeError:
        text = header.decode("utf-8", errors="replace")

    if ext == ".tex":
        return {
            "type": "latex",
            "path": str(path.resolve()),
        }

    # Check if it looks like LaTeX content even without .tex extension
    if re.search(r'\\documentclass|\\begin\{|\\section\{', text[:2000]):
        return {
            "type": "latex",
            "path": str(path.resolve()),
            "note": "detected LaTeX content in non-.tex file",
        }

    return {
        "type": "markdown",
        "path": str(path.resolve()),
    }


def is_binary(header: bytes) -> bool:
    """Check if bytes indicate a binary file."""
    if b"\x00" in header[:256]:
        return True
    first = header[0] if header[0] < 128 else 65
    cat = unicodedata.category(chr(first))
    return cat.startswith("C") and first not in (0x09, 0x0A, 0x0D)  # allow tab, LF, CR


def normalize_markdown(meta: dict, workspace: Path) -> tuple[str, str]:
    """Normalize input to a standard markdown file. Returns (normalized_path, error)."""
    input_type = meta.get("type", "")

    if input_type == "markdown":
        src = Path(meta["path"])
        dst = workspace / "normalized.md"
        shutil.copy2(src, dst)
        return str(dst), ""

    if input_type in ("latex", "latex_directory"):
        return normalize_latex(meta, workspace)

    if input_type == "pdf":
        return "", "PDF extraction requires external tool (mineru or similar). Run the tool manually and provide the extracted .md file as input."

    if "error" in meta:
        return "", meta["error"]

    return "", f"unknown input type: {input_type}"


def normalize_latex(meta: dict, workspace: Path) -> tuple[str, str]:
    """Basic LaTeX to Markdown conversion for common constructs."""
    src = Path(meta.get("main_file", meta.get("path", "")))
    if not src or not src.exists():
        return "", f"LaTeX source not found"

    try:
        text = src.read_text(encoding="utf-8")
    except Exception as e:
        return "", f"cannot read LaTeX file: {e}"

    lines = text.split("\n")
    output_lines = []
    inside_math = False
    inside_code = False

    for line in lines:
        stripped = line.strip()

        # Preserve display math environments
        if stripped.startswith("\\[") or stripped.startswith("$$"):
            output_lines.append("<!-- BLOCK_MATH -->")
            output_lines.append(line)
            inside_math = True
            continue
        if inside_math:
            output_lines.append(line)
            if stripped.endswith("\\]") or stripped.endswith("$$"):
                output_lines.append("<!-- BLOCK_MATH_END -->")
                inside_math = False
            continue

        # Preserve verbatim/code environments
        if stripped.startswith("\\begin{verbatim}") or stripped.startswith("\\begin{lstlisting}"):
            output_lines.append("<!-- BLOCK_CODE -->")
            output_lines.append(line)
            inside_code = True
            continue
        if inside_code:
            output_lines.append(line)
            if stripped.startswith("\\end{verbatim}") or stripped.startswith("\\end{lstlisting}"):
                output_lines.append("<!-- BLOCK_CODE_END -->")
                inside_code = False
            continue

        # Skip preamble
        if stripped.startswith("\\documentclass") or stripped.startswith("\\usepackage"):
            continue
        if stripped.startswith("\\bibliographystyle") or stripped.startswith("\\bibliography"):
            output_lines.append(f"\n## References\n")
            continue

        # Commands to simple markdown
        line = re.sub(r'\\(section\*?)\{(.+?)\}', r'## \2', line)
        line = re.sub(r'\\(subsection\*?)\{(.+?)\}', r'### \2', line)
        line = re.sub(r'\\(subsubsection\*?)\{(.+?)\}', r'#### \2', line)
        line = re.sub(r'\\(textbf|textbf)\{(.+?)\}', r'**\2**', line)
        line = re.sub(r'\\(textit|emph)\{(.+?)\}', r'*\2*', line)
        line = re.sub(r'\\(texttt)\{(.+?)\}', r'`\2`', line)

        # Inline math: \(...\) or $...$
        line = re.sub(r'\\\((.*?)\\\)', r'$\1$', line)
        line = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', r'$\1$', line)

        # \cite, \ref, \label
        line = re.sub(r'\\(cite|ref|label)\[.*?\]?\{.*?\}', '', line)

        # Itemize/enumerate
        if stripped.startswith("\\item"):
            indent = "  " * (len(line) - len(line.lstrip()))
            line = indent + "- " + stripped[5:].strip()

        # Abstract
        if stripped.startswith("\\begin{abstract}"):
            output_lines.append("<!-- BLOCK: abstract | type: abstract -->")
            continue
        if stripped.startswith("\\end{abstract}"):
            output_lines.append("<!-- BLOCK_END: abstract -->")
            continue

        # Table
        if stripped.startswith("\\begin{tabular") or stripped.startswith("\\begin{table"):
            output_lines.append("<!-- BLOCK: table | type: table -->")
            inside_table = True
            continue
        if stripped.startswith("\\end{tabular") or stripped.startswith("\\end{table"):
            output_lines.append(line)
            output_lines.append("<!-- BLOCK_END: table -->")
            inside_table = False
            continue

        # Figure
        if stripped.startswith("\\begin{figure"):
            output_lines.append("<!-- BLOCK: figure | type: figure_caption -->")
            continue
        if stripped.startswith("\\end{figure}"):
            output_lines.append("<!-- BLOCK_END: figure -->")
            continue

        output_lines.append(line)

    result = "\n".join(output_lines)
    dst = workspace / "normalized.md"
    dst.write_text(result, encoding="utf-8")

    return str(dst), ""


def main():
    parser = argparse.ArgumentParser(description="Detect and normalize input for literature translation")
    parser.add_argument("--source", required=True, help="Source file or directory path")
    parser.add_argument("--workspace", required=True, help="Workspace directory path")
    args = parser.parse_args()

    source_path = Path(args.source)
    workspace_path = Path(args.workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)

    meta = classify_input(source_path)
    error = meta.get("error", "")

    if error:
        meta_json = {
            "source_path": str(source_path.resolve()),
            "status": "error",
            "error": error,
        }
        (workspace_path / "source_meta.json").write_text(
            json.dumps(meta_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(meta_json, ensure_ascii=False))
        sys.exit(1)

    md_path, norm_error = normalize_markdown(meta, workspace_path)
    if norm_error:
        meta_json = {
            "source_path": str(source_path.resolve()),
            "status": "error",
            "error": norm_error,
        }
        (workspace_path / "source_meta.json").write_text(
            json.dumps(meta_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(meta_json, ensure_ascii=False))
        sys.exit(1)

    # Detect language from content (simple heuristic)
    lang_detect = ""
    md_content = (workspace_path / "normalized.md").read_text(encoding="utf-8", errors="replace")[:5000]
    cjk_count = sum(1 for c in md_content if unicodedata.name(c, "").startswith("CJK"))
    if cjk_count > 20:
        lang_detect = "zh"
    else:
        lang_detect = "en"

    meta_json = {
        "source_path": str(source_path.resolve()),
        "type": meta.get("type", "unknown"),
        "normalized_path": md_path,
        "status": "ok",
        "detected_language_hint": lang_detect,
    }

    if "note" in meta:
        meta_json["note"] = meta["note"]

    (workspace_path / "source_meta.json").write_text(
        json.dumps(meta_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta_json, ensure_ascii=False))


if __name__ == "__main__":
    main()
