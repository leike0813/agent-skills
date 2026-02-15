from __future__ import annotations

import argparse
import os
import sys

from apply_llm_decisions import apply_llm_decisions, load_json, write_json
from match_pipeline import MatchParams, build_initial_match_result, write_match_result


def _default_output_path(refs_extracted_path: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(refs_extracted_path))
    return os.path.join(base_dir, "match_result.json")


def cmd_match(args: argparse.Namespace) -> int:
    params = MatchParams(
        top_k=int(args.top_k),
        tfidf_auto_match_threshold=float(args.tfidf_auto_match_threshold),
        tfidf_auto_match_gap=float(args.tfidf_auto_match_gap),
        tfidf_needs_llm_threshold=float(args.tfidf_needs_llm_threshold),
    )

    match_result = build_initial_match_result(
        refs_extracted_path=args.refs_extracted,
        zotero_endpoint=args.zotero_endpoint,
        library_cache_path=args.library_cache,
        params=params,
    )

    output_path = args.output or _default_output_path(args.refs_extracted)
    write_match_result(output_path, match_result)
    print(output_path)
    return 0


def cmd_apply_decisions(args: argparse.Namespace) -> int:
    match_result = load_json(args.match_result)
    decisions = load_json(args.llm_decisions)

    result = apply_llm_decisions(match_result, decisions)
    output_path = args.output or os.path.abspath(args.match_result)
    write_json(output_path, result.updated)
    print(output_path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="literature-match")
    sub = parser.add_subparsers(dest="command", required=True)

    p_match = sub.add_parser("match", help="Build initial match_result.json from refs_extracted.json and a Zotero library export")
    p_match.add_argument("--refs-extracted", required=True, help="Path to refs_extracted.json (agent output)")
    p_match.add_argument(
        "--library-cache",
        help="Path to cached library.betterbibtexjson (preferred for tests/dev); if omitted, fetch from zotero-endpoint",
    )
    p_match.add_argument(
        "--zotero-endpoint",
        default="http://127.0.0.1:23119/better-bibtex/export/library?/1/library.betterbibtexjson",
        help="Zotero Better BibTeX export endpoint (only used if --library-cache is omitted)",
    )
    p_match.add_argument("--output", help="Output path for match_result.json (default: next to refs_extracted.json)")
    p_match.add_argument("--top-k", default=10, type=int, help="Top-K candidates per ref (default: 10)")
    p_match.add_argument("--tfidf-auto-match-threshold", default=0.90, type=float)
    p_match.add_argument("--tfidf-auto-match-gap", default=0.10, type=float)
    p_match.add_argument("--tfidf-needs-llm-threshold", default=0.25, type=float)
    p_match.set_defaults(func=cmd_match)

    p_apply = sub.add_parser("apply-decisions", help="Apply llm_decisions.json to an existing match_result.json")
    p_apply.add_argument("--match-result", required=True, help="Path to match_result.json to update")
    p_apply.add_argument("--llm-decisions", required=True, help="Path to llm_decisions.json (agent output)")
    p_apply.add_argument("--output", help="Output path (default: overwrite --match-result)")
    p_apply.set_defaults(func=cmd_apply_decisions)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
