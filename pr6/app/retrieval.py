import os
from collections import defaultdict
from dataclasses import dataclass

from dotenv import load_dotenv

from .documents import Chunk
from .index import Hit, SearchIndex
from .keyword import KeywordIndex

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


SEARCH_TOP_K = _env_int("SEARCH_TOP_K", 8)
CONTEXT_CHUNKS = _env_int("RAG_CONTEXT_CHUNKS", 4)
CONTEXT_BUDGET = _env_int("RAG_CONTEXT_BUDGET", 1500)
SIMILARITY_THRESHOLD = _env_float("SIMILARITY_THRESHOLD", 0.80)
BEST_POSITION = os.getenv("RAG_BEST_POSITION", "first").lower()
FUSION = os.getenv("RAG_FUSION", "rrf").lower()
RRF_K = 60


@dataclass
class Source:
    ref: int
    chunk: Chunk
    score: float


def _chunk_key(chunk: Chunk) -> tuple[str, str]:
    return chunk.source, chunk.text


def _passes_code_filters(chunk: Chunk) -> bool:
    meta = chunk.metadata
    if meta.get("audience") == "персонал":
        return False
    if meta.get("status") == "архів":
        return False
    body = "\n".join(l for l in chunk.text.splitlines() if not l.lstrip().startswith("#"))
    if len(body.strip()) < 40:
        return False
    return True


def _merge_rrf(semantic: list[Hit], keyword: list[Hit]) -> list[Hit]:
    scores: dict[tuple[str, str], float] = defaultdict(float)
    hits_map: dict[tuple[str, str], Hit] = {}

    for hits in (semantic, keyword):
        for rank, hit in enumerate(hits):
            key = _chunk_key(hit.chunk)
            scores[key] += 1.0 / (RRF_K + rank + 1)
            if key not in hits_map:
                hits_map[key] = hit

    ordered = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    return [hits_map[k] for k in ordered]


def retrieve(
    query: str,
    index: SearchIndex,
    keyword_index: KeywordIndex | None,
    filters: dict | None = None,
) -> list[Hit]:
    user_filters = {k: v for k, v in (filters or {}).items() if v}

    semantic = index.search(query, top_k=SEARCH_TOP_K * 3, filters=user_filters or None)
    semantic = [h for h in semantic if _passes_code_filters(h.chunk)]
    strong = [h for h in semantic if h.score >= SIMILARITY_THRESHOLD]
    if not strong:
        return []

    sem_score = {_chunk_key(h.chunk): h.score for h in strong}

    keyword: list[Hit] = []
    if keyword_index is not None:
        keyword = keyword_index.search(query, top_k=SEARCH_TOP_K * 3, filters=user_filters or None)
        keyword = [h for h in keyword if _passes_code_filters(h.chunk)]

    merged = _merge_rrf(strong, keyword) if (keyword and FUSION == "rrf") else strong
    result = [
        Hit(chunk=h.chunk, score=sem_score[_chunk_key(h.chunk)])
        for h in merged
        if _chunk_key(h.chunk) in sem_score
    ]
    return result[:CONTEXT_CHUNKS]


def _format_label(ref: int, chunk: Chunk) -> str:
    meta = chunk.metadata
    title = meta.get("title", chunk.source)
    heading = meta.get("heading", "")
    updated = meta.get("updated", "")
    path = f"{title} › {heading}" if heading else title
    if updated:
        path = f"{path} ({updated})"
    return f"[{ref}] {path}"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def build_context(hits: list[Hit], budget: int = CONTEXT_BUDGET) -> tuple[str, list[Source]]:
    if not hits:
        return "", []

    ordered = list(hits)
    if BEST_POSITION == "last" and len(ordered) > 1:
        ordered = ordered[1:] + ordered[:1]

    context_parts: list[str] = []
    sources: list[Source] = []
    current_tokens = 0

    for i, hit in enumerate(ordered, start=1):
        part = f"{_format_label(i, hit.chunk)}:\n{hit.chunk.text}\n"
        est = _estimate_tokens(part)
        if current_tokens + est > budget:
            print(f"[context] відкинуто за бюджетом: {hit.chunk.source}")
            continue
        context_parts.append(part)
        sources.append(Source(ref=i, chunk=hit.chunk, score=hit.score))
        current_tokens += est

    return "\n".join(context_parts), sources