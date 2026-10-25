import os
import pickle
from dataclasses import dataclass
from pathlib import Path
import numpy as np

from .documents import Chunk
from .embeddings import embed_query

INDEX_DIR = Path(__file__).parent.parent / "data"
INDEX_FILE = INDEX_DIR / "index.pkl"
DEFAULT_TOP_K = 5


@dataclass
class Hit:
    """Результат пошуку з фрагментом та оцінкою релевантності."""

    chunk: Chunk
    score: float


class SearchIndex:
    """Векторний індекс для пошуку фрагментів за косинусною схожістю."""

    def __init__(
        self,
        chunks: list[Chunk] | None = None,
        vectors: np.ndarray | None = None,
        model_name: str = "",
    ):
        self.chunks: list[Chunk] = chunks or []
        self.vectors: np.ndarray | None = vectors
        self.model_name: str = model_name

    def build(self, chunks: list[Chunk], vectors: np.ndarray, model_name: str) -> "SearchIndex":
        """Побудувати індекс із фрагментів та векторів."""
        self.chunks = chunks
        self.vectors = vectors
        self.model_name = model_name
        return self

    def save(self, filepath: Path = INDEX_FILE) -> None:
        """Зберегти стан індексу у pickle-файл."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            pickle.dump(
                {
                    "chunks": self.chunks,
                    "vectors": self.vectors,
                    "model_name": self.model_name,
                },
                f,
            )

    def load(self, filepath: Path = INDEX_FILE) -> "SearchIndex":
        """Завантажити збережений індекс з диска."""
        if not filepath.exists():
            raise FileNotFoundError(f"Файл індексу не знайдено за шляхом: {filepath}")
        with open(filepath, "rb") as f:
            data = pickle.load(f)
            self.chunks = data["chunks"]
            self.vectors = data["vectors"]
            self.model_name = data["model_name"]
        return self

    def search(self, query: str, top_k: int = DEFAULT_TOP_K, filters: dict | None = None) -> list[Hit]:
        """Шукати найближчі за релевантністю фрагменти для запиту."""
        if self.vectors is None or len(self.chunks) == 0:
            return []

        query_vector = embed_query(query)

        # Косинусна схожість (скалярний добуток для нормалізованих векторів)
        scores = np.dot(self.vectors, query_vector)
        top_indices = np.argsort(scores)[::-1]

        hits: list[Hit] = []
        for idx in top_indices:
            score = float(scores[idx])
            chunk = self.chunks[idx]

            # Фільтрація за метаданими
            if filters:
                skip = False
                for k, v in filters.items():
                    if chunk.metadata.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue

            hits.append(Hit(chunk=chunk, score=score))
            if len(hits) >= top_k:
                break

        return hits


def build(chunks: list[Chunk], vectors: np.ndarray, model_name: str) -> SearchIndex:
    """Модульна обгортка для створення індексу."""
    index = SearchIndex()
    return index.build(chunks, vectors, model_name)


def save(index_obj: SearchIndex, filepath: Path = INDEX_FILE) -> None:
    """Модульна обгортка для збереження індексу."""
    if isinstance(index_obj, SearchIndex):
        index_obj.save(filepath)
    else:
        raise ValueError("Очікувався об'єкт SearchIndex")


def load(filepath: Path = INDEX_FILE) -> SearchIndex:
    """Модульна обгортка для завантаження індексу."""
    index = SearchIndex()
    return index.load(filepath)