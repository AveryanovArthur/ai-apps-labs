import math
import re
from collections import Counter
from dataclasses import dataclass

from .documents import Chunk
from .index import DEFAULT_TOP_K, Hit


def tokenize(text: str) -> list[str]:
    """Токенізація тексту (переведення в нижній регістр та виділення слів)."""
    return re.findall(r"\w+", text.lower())


class KeywordIndex:
    """Індекс ключових слів на основі алгоритму BM25."""

    def __init__(
        self,
        chunks: list[Chunk] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.chunks: list[Chunk] = chunks or []
        self.k1 = k1
        self.b = b
        self.doc_len: list[int] = []
        self.avgdl: float = 0.0
        self.doc_freqs: list[Counter] = []
        self.idf: dict[str, float] = {}

        if self.chunks:
            self._build_index()

    def _build_index(self) -> None:
        corpus = [tokenize(c.text) for c in self.chunks]
        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0.0

        self.doc_freqs = [Counter(doc) for doc in corpus]

        df: Counter = Counter()
        for doc in corpus:
            df.update(set(doc))

        num_docs = len(self.chunks)
        for word, freq in df.items():
            self.idf[word] = math.log((num_docs - freq + 0.5) / (freq + 0.5) + 1.0)

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        filters: dict | None = None,
    ) -> list[Hit]:
        """Шукати фрагменти за ключовими словами."""
        if not self.chunks:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = [0.0] * len(self.chunks)

        for token in query_tokens:
            if token not in self.idf:
                continue
            idf_val = self.idf[token]
            for i, doc_freq in enumerate(self.doc_freqs):
                if token not in doc_freq:
                    continue
                tf = doc_freq[token]
                len_norm = (
                    1.0 - self.b + self.b * (self.doc_len[i] / self.avgdl if self.avgdl > 0 else 0)
                )
                score = idf_val * (tf * (self.k1 + 1.0)) / (tf + self.k1 * len_norm)
                scores[i] += score

        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        hits: list[Hit] = []
        for idx in ranked_indices:
            if scores[idx] <= 0:
                continue

            chunk = self.chunks[idx]

            if filters:
                skip = False
                for k, v in filters.items():
                    if chunk.metadata.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue

            hits.append(Hit(chunk=chunk, score=float(scores[idx])))
            if len(hits) >= top_k:
                break

        return hits


def build(chunks: list[Chunk]) -> KeywordIndex:
    """Побудувати індекс ключових слів з наданих фрагментів."""
    return KeywordIndex(chunks)