from dataclasses import dataclass, field
import re
from rank_bm25 import BM25Okapi

from .documents import Chunk
from .index import Hit

# Автовизначення KeywordIndex
try:
    from .models import KeywordIndex
except ImportError:
    try:
        from models import KeywordIndex
    except ImportError:
        @dataclass
        class KeywordIndex:
            chunks: list[Chunk]
            extra: dict = field(default_factory=dict)

# Безпечний імпорт top_k
try:
    import config
    DEFAULT_TOP_K = getattr(config, "SEARCH_TOP_K", getattr(config, "DEFAULT_TOP_K", 5))
except ImportError:
    DEFAULT_TOP_K = 5


def tokenize(text: str) -> list[str]:
    """Токенізація тексту з підтримкою українських апострофів та артикулів."""
    text = text.lower()
    tokens = re.findall(r"[\w'\-]+", text)
    return [t for t in tokens if len(t) > 1]


def build(chunks: list[Chunk]) -> KeywordIndex:
    tokenized_corpus = [tokenize(c.text) for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    return KeywordIndex(chunks=chunks, extra={"bm25": bm25})


def search(
    index: KeywordIndex,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    filters: dict | None = None,
) -> list[Hit]:
    if not index.chunks or "bm25" not in index.extra:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    bm25: BM25Okapi = index.extra["bm25"]
    scores = bm25.get_scores(query_tokens)

    hits = []
    for i, chunk in enumerate(index.chunks):
        if filters:
            skip = False
            for k, v in filters.items():
                if v and chunk.metadata.get(k) != v:
                    skip = True
                    break
            if skip:
                continue

        score = float(scores[i])
        if score > 0:
            hits.append(Hit(chunk=chunk, score=score))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]