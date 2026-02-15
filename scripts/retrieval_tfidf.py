from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


@dataclass(frozen=True)
class TfidfRetrievalIndex:
    citekeys: list[str]
    titles: list[str]
    vectorizer: TfidfVectorizer
    matrix: Any


def build_tfidf_index(records: dict[str, dict[str, Any]]) -> TfidfRetrievalIndex:
    citekeys = list(records.keys())
    titles = [str(records[c].get("title") or "") for c in citekeys]

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(titles) if titles else None
    return TfidfRetrievalIndex(citekeys=citekeys, titles=titles, vectorizer=vectorizer, matrix=matrix)


def retrieve_top_k(index: TfidfRetrievalIndex, query: str, top_k: int) -> list[tuple[str, float]]:
    query_text = (query or "").strip()
    if not query_text or not index.citekeys or index.matrix is None:
        return []

    query_vec = index.vectorizer.transform([query_text])
    scores = linear_kernel(query_vec, index.matrix).flatten()

    scored = list(zip(index.citekeys, (float(s) for s in scores)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[: max(0, int(top_k))]
