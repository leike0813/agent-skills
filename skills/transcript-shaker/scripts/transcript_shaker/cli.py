"""命令行入口：转写单个 transcript，或用 --list / --search 定位候选。"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from .adapters import UnsupportedTranscript, detect_adapter, supported_harnesses
from .locate import HARNESS_SOURCES, find_candidates, render_candidates
from .render import DEFAULT_MAX_CHARS, prepare_compact, render_markdown, render_yaml
from .search import UNSUPPORTED, render_matches, search, tokenize

PROFILES = ("default", "full", "compact")
FORMATS = ("markdown", "yaml")


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number <= 0:
        raise argparse.ArgumentTypeError("expected positive integer")
    return number


def _date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcript_shaker",
        description="把 Agent Harness 的本地 transcript 裁剪转写为 Markdown 日志，或列出本机候选 transcript。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  transcript_shaker --list\n"
            "  transcript_shaker --list --harness codex --limit 5 --since 2026-10-20\n"
            "  transcript_shaker --search 'embedding cache' --harness omp --limit 5\n"
            "  transcript_shaker ~/.omp/agent/sessions/-proj/2026-10-21T09-00-00-000Z_<id>.jsonl --out session.md\n"
            "  transcript_shaker ~/.omp/agent/sessions/-proj/x.jsonl --profile compact --format yaml"
        ),
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        help="transcript 文件路径（如 Codex rollout JSONL / .jsonl.zst）",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出本机候选 transcript（只看路径与修改时间，不解析内容）",
    )
    parser.add_argument(
        "--search",
        help="配合 --harness：按内容在单个 harness 内定位 transcript（不跨 harness）",
    )
    parser.add_argument(
        "--harness",
        choices=sorted(HARNESS_SOURCES),
        help="配合 --list / --search：只看某个 harness 的候选",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=None,
        help="配合 --list / --search：最多输出多少条（--list 默认 20，--search 默认 10）",
    )
    parser.add_argument(
        "--since",
        type=_date_arg,
        metavar="YYYY-MM-DD",
        help="配合 --list / --search：只看修改时间不早于该本地日期的候选",
    )
    parser.add_argument(
        "--match",
        help="配合 --list / --search：只看路径包含该子串（不区分大小写）的候选",
    )
    parser.add_argument(
        "--format",
        choices=FORMATS,
        default=None,
        help="输出格式：markdown（默认）或 yaml",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default=None,
        help="输出档位：default（默认）、full（不截断）、compact（按角色压缩消息、工具只留名字与命令片段）",
    )
    parser.add_argument(
        "--max-chars",
        type=_positive_int,
        default=None,
        help=f"配合 --profile default：工具结果与 system 消息的截断上限（默认 {DEFAULT_MAX_CHARS}）",
    )
    parser.add_argument("--out", help="输出文件路径；缺省写到 stdout")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list:
        if (
            args.transcript is not None
            or args.search is not None
            or args.max_chars is not None
            or args.out
            or args.format
            or args.profile
        ):
            parser.error(
                "--list 不能与 transcript / --search / --max-chars / --out / --format / --profile 同用"
            )
        limit = args.limit if args.limit is not None else 20
        candidates = find_candidates(
            harnesses=[args.harness] if args.harness else None,
            since=args.since,
            match=args.match,
        )
        sys.stdout.write(render_candidates(candidates[:limit]))
        return 0
    if args.search is not None:
        if (
            args.transcript is not None
            or args.max_chars is not None
            or args.out
            or args.format
            or args.profile
        ):
            parser.error(
                "--search 不能与 transcript / --list / --max-chars / --out / --format / --profile 同用"
            )
        if not args.harness:
            parser.error("--search 必须指定 --harness（内容检索暂不跨 harness）")
        if args.harness in UNSUPPORTED:
            parser.error("--search 不支持 kilo-code：kilo.db 含多个会话")
        terms = tokenize(args.search)
        if not terms:
            parser.error("--search 需要至少一个词项")
        limit = args.limit if args.limit is not None else 10
        sys.stdout.write(
            render_matches(
                search(args.harness, [t.encode() for t in terms], args.since, args.match),
                len(terms),
                limit,
            )
        )
        return 0
    if args.transcript is None:
        parser.error("缺少 transcript 参数（或使用 --list 列出候选）")
    if args.harness or args.since or args.limit is not None or args.match:
        parser.error("--harness / --since / --limit / --match 仅用于 --list")
    fmt = args.format or "markdown"
    profile = args.profile or "default"
    if args.max_chars is not None and profile != "default":
        parser.error("--max-chars 只能用于 --profile default")
    # full 完全不截断；compact 的截断在 prepare_compact 里按角色分档
    max_chars = (args.max_chars if args.max_chars is not None else DEFAULT_MAX_CHARS) if profile == "default" else 0

    path = Path(args.transcript).expanduser()
    if not path.exists():
        print(f"transcript_shaker: file not found: {path}", file=sys.stderr)
        return 1
    if not path.is_file():
        print(f"transcript_shaker: not a file: {path}", file=sys.stderr)
        return 1

    try:
        adapter = detect_adapter(path)
    except UnsupportedTranscript:
        print(
            f"transcript_shaker: unsupported transcript format: {path}（已支持：{supported_harnesses()}）",
            file=sys.stderr,
        )
        return 1
    except (OSError, RuntimeError) as exc:
        print(f"transcript_shaker: {exc}", file=sys.stderr)
        return 1

    try:
        session, events = adapter.parse(path)
    except (OSError, RuntimeError) as exc:
        print(f"transcript_shaker: {exc}", file=sys.stderr)
        return 1

    live = prepare_compact(events) if profile == "compact" else events
    if fmt == "yaml":
        document = render_yaml(session, live, max_chars=max_chars, profile=profile)
    else:
        document = render_markdown(session, live, max_chars=max_chars, profile=profile)
    # 某些 transcript 的 JSON 里带孤立代理项（\ud83e 之类），直接写会抛 UnicodeEncodeError。
    document = document.encode("utf-8", "replace").decode("utf-8")
    if args.out:
        out_path = Path(args.out).expanduser()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(document, encoding="utf-8")
        except OSError as exc:
            print(f"transcript_shaker: cannot write output: {exc}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(document)
    return 0
