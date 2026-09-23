from dataclasses import dataclass, field
import json
from pathlib import Path
import numpy as np

from .documents import Chunk

# Автовизначення або імпорт Hit та SearchIndex
try:
    from .models import Hit, SearchIndex
except ImportError:
    try:
        from models import Hit, SearchIndex
    except ImportError:
        @dataclass
        class Hit:
            chunk: Chunk
            score: float

        @dataclass
        class SearchIndex:
            chunks: list[Chunk]
            vectors: np.ndarray
            model_name: str
            extra: dict = field(default_factory=dict)

            def __len__(self):
                return len(self.chunks)

# Безпечний імпорт налаштувань індексу
try:
    import config
    INDEX_DIR = Path(getattr(config, "INDEX_DIR", "index"))
    DEFAULT_TOP_K = getattr(config, "SEARCH_TOP_K", getattr(config, "DEFAULT_TOP_K", 5))
    SIMILARITY_THRESHOLD = getattr(config, "SIMILARITY_THRESHOLD", 0.3)
except ImportError:
    INDEX_DIR = Path("index")
    DEFAULT_TOP_K = 5
    SIMILARITY_THRESHOLD = 0.3


def build(chunks: list[Chunk], vectors: np.ndarray, model_name: str) -> SearchIndex:
    if len(chunks) != len(vectors):
        raise ValueError("Кількість векторів не збігається з кількістю фрагментів")

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized_vectors = vectors / norms

    return SearchIndex(
        chunks=chunks, vectors=normalized_vectors, model_name=model_name
    )


def save(index: SearchIndex, path: Path = INDEX_DIR) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    np.save(path / "vectors.npy", index.vectors)

    chunks_data = [
        {
            "text": chunk.text,
            "source": chunk.source,
            "metadata": chunk.metadata,
        }
        for chunk in index.chunks
    ]
    meta = {"model_name": index.model_name, "extra": index.extra}

    (path / "chunks.json").write_text(
        json.dumps(chunks_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (path / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load(path: Path = INDEX_DIR) -> SearchIndex:
    path = Path(path)
    vectors_path = path / "vectors.npy"
    chunks_path = path / "chunks.json"
    meta_path = path / "meta.json"

    if not vectors_path.exists() or not chunks_path.exists():
        raise FileNotFoundError(
            "Векторний індекс не знайдено. Спочатку виконайте ingest.py."
        )

    vectors = np.load(vectors_path)
    chunks_raw = json.loads(chunks_path.read_text(encoding="utf-8"))
    meta = (
        json.loads(meta_path.read_text(encoding="utf-8"))
        if meta_path.exists()
        else {}
    )

    chunks = [
        Chunk(
            text=c["text"], source=c["source"], metadata=c.get("metadata", {})
        )
        for c in chunks_raw
    ]
    model_name = meta.get("model_name", "unknown")

    return SearchIndex(
        chunks=chunks,
        vectors=vectors,
        model_name=model_name,
        extra=meta.get("extra", {}),
    )


def search(
    index: SearchIndex,
    query_vector: np.ndarray,
    top_k: int = DEFAULT_TOP_K,
    filters: dict | None = None,
    threshold: float | None = SIMILARITY_THRESHOLD,
) -> list[Hit]:
    if len(index) == 0:
        return []

    valid_indices = []
    for i, chunk in enumerate(index.chunks):
        match = True
        if filters:
            for k, v in filters.items():
                if v and chunk.metadata.get(k) != v:
                    match = False
                    break
        if match:
            valid_indices.append(i)

    if not valid_indices:
        return []

    filtered_vectors = index.vectors[valid_indices]

    q_norm = query_vector / (np.linalg.norm(query_vector) or 1.0)
    scores = filtered_vectors @ q_norm

    hits = []
    for idx_in_valid, score in enumerate(scores):
        score_val = float(score)
        if threshold is not None and score_val < threshold:
            continue
        original_idx = valid_indices[idx_in_valid]
        hits.append(Hit(chunk=index.chunks[original_idx], score=score_val))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]