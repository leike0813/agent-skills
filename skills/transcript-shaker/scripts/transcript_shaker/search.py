"""按内容在单个 harness 内定位 transcript：流式字节扫描，不解析 JSON。"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple

from .locate import Candidate, find_candidates

CHUNK = 1 << 22  # 4 MiB
UNSUPPORTED = ("kilo-code",)  # 一个库文件含多个会话，定位语义不成立
ZSTD_SUFFIXES = (".zst", ".zstd")


def tokenize(query: str) -> List[str]:
    """小写后按空白切词；按出现顺序去重；查询全为空白时返回空列表。"""
    terms: List[str] = []
    for part in query.lower().split():
        if part and part not in terms:
            terms.append(part)
    return terms


def iter_chunks(path: Path, size: int = CHUNK) -> Iterator[bytes]:
    """按 size 字节流式产出文件内容；.zst/.zstd 三选一解压（与 adapters/_support.py 同优先级）。"""
    if not path.name.endswith(ZSTD_SUFFIXES):
        with path.open("rb") as handle:
            while chunk := handle.read(size):
                yield chunk
        return

    try:
        from compression import zstd as zstd_module  # Python 3.14+
    except ImportError:
        zstd_module = None
    if zstd_module is not None:
        with zstd_module.open(path, "rb") as handle:
            while chunk := handle.read(size):
                yield chunk
        return

    try:
        import zstandard as zstandard_module
    except ImportError:
        zstandard_module = None
    if zstandard_module is not None:
        with zstandard_module.open(path, "rb") as handle:
            while chunk := handle.read(size):
                yield chunk
        return

    zstd_bin = shutil.which("zstd")
    if zstd_bin is None:
        raise RuntimeError(
            f"cannot decompress {path}：需要 Python 3.14 compression.zstd、zstandard 包或 zstd 命令行"
        )
    # 必须流式读：整个会话解压后可达数百 MB，capture_output 会全部进内存。
    proc = subprocess.Popen([zstd_bin, "-dc", str(path)], stdout=subprocess.PIPE)
    stream = proc.stdout
    try:
        while chunk := stream.read(size):
            yield chunk
    finally:
        stream.close()
        proc.wait()


def count_terms(path: Path, terms: Sequence[bytes]) -> List[int]:
    """逐块小写后 bytes.count；返回每个词项在整份文件中的出现次数。"""
    counts = [0] * len(terms)
    for chunk in iter_chunks(path):
        lowered = chunk.lower()
        for index, term in enumerate(terms):
            counts[index] += lowered.count(term)
    return counts


@dataclass(frozen=True)
class Match:
    candidate: Candidate
    counts: Tuple[int, ...]
    distinct: int  # 出现次数 > 0 的词项数
    score: int  # 最弱词项的出现次数 = min(counts)


def _sort_key(m: Match) -> Tuple[int, int, float, str]:
    return (-m.distinct, -m.score, -m.candidate.mtime.timestamp(), str(m.candidate.path))


def search(
    harness: str,
    terms: Sequence[bytes],
    since: Optional[date] = None,
    match: Optional[str] = None,
) -> List[Match]:
    """扫描该 harness 的候选文件并按 (词项命中数, 最弱词项次数, 修改时间, 路径) 排序返回。

    先对每个候选统计 counts：distinct > 0 才保留。若存在 distinct == len(terms) 的文件，
    只返回这些（全命中）；否则返回全部 distinct > 0 的文件（部分命中）。
    扫描期间读不动的文件（OSError / RuntimeError）跳过，不中断整个检索。
    """
    matches: List[Match] = []
    for candidate in find_candidates(harnesses=[harness], since=since, match=match):
        try:
            counts = count_terms(candidate.path, terms)
        except (OSError, RuntimeError):
            continue
        distinct = sum(1 for count in counts if count > 0)
        if distinct == 0:
            continue
        matches.append(
            Match(
                candidate=candidate,
                counts=tuple(counts),
                distinct=distinct,
                score=min(counts),
            )
        )
    full = [m for m in matches if m.distinct == len(terms)]
    return sorted(full or matches, key=_sort_key)


def is_ambiguous(matches: Sequence[Match], term_count: int) -> bool:
    """首位部分命中即歧义；仅 1 条全命中不算；否则首位 score 不足第二位两倍即歧义。"""
    if not matches:
        return False
    top = matches[0]
    if top.distinct < term_count:
        return True
    if len(matches) < 2:
        return False
    return top.score < 2 * matches[1].score


def render_matches(matches: Sequence[Match], term_count: int, limit: int) -> str:
    """首行全部命中数，次行歧义标记（用全部命中计算），其后最多 limit 行数据。"""
    lines = [
        f"# matches: {len(matches)}",
        f"# ambiguous: {'yes' if is_ambiguous(matches, term_count) else 'no'}",
    ]
    lines += [
        f"{m.candidate.mtime.strftime('%Y-%m-%dT%H:%M:%S')}\t{m.candidate.harness}"
        f"\tscore={m.score}\tterms={m.distinct}/{term_count}\t{m.candidate.path}"
        for m in matches[:limit]
    ]
    return "\n".join(lines) + "\n"
