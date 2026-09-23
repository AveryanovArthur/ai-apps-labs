import numpy as np
from sentence_transformers import SentenceTransformer

# Безпечний імпорт назви моделі
try:
    import config
    MODEL_NAME = getattr(config, "EMBEDDING_MODEL", getattr(config, "MODEL_NAME", "intfloat/multilingual-e5-small"))
except ImportError:
    MODEL_NAME = "intfloat/multilingual-e5-small"

_model = None


def get_model() -> SentenceTransformer:
    """Ліниве завантаження singleton-моделі з Hugging Face."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_passages(texts: list[str]) -> np.ndarray:
    """Генерація векторів для чанків (із префіксом 'passage:' для моделей E5)."""
    model = get_model()
    prefixed = [f"passage: {t}" for t in texts]
    embeddings = model.encode(
        prefixed, normalize_embeddings=True, show_progress_bar=True
    )
    return np.array(embeddings, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    """Генерація вектора для пошукового запиту (із префіксом 'query:' для E5)."""
    model = get_model()
    prefixed = f"query: {text}"
    embedding = model.encode(prefixed, normalize_embeddings=True)
    return np.array(embedding, dtype=np.float32)