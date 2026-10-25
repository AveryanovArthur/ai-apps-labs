import os
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
EMBEDDING_MODEL = MODEL_NAME

_model = None


def get_model() -> SentenceTransformer:
    """Завантажити або повернути вже кешовану модель векторних ембедингів."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_query(query: str) -> np.ndarray:
    """Згенерувати векторний ембединг для пошукового запиту."""
    model = get_model()
    is_e5 = "e5" in MODEL_NAME.lower()
    text = f"query: {query}" if is_e5 else query
    vector = model.encode(text, normalize_embeddings=True)
    return np.array(vector, dtype=np.float32)


def embed_passages(texts: list[str]) -> np.ndarray:
    """Згенерувати векторні ембединги для списку фрагментів документів."""
    model = get_model()
    is_e5 = "e5" in MODEL_NAME.lower()
    formatted_texts = [f"passage: {t}" if is_e5 else t for t in texts]
    vectors = model.encode(
        formatted_texts,
        normalize_embeddings=True,
        show_progress_bar=True
    )
    return np.array(vectors, dtype=np.float32)