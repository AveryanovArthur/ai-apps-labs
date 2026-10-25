from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import index, keyword, llm, rag

INDEX_PATH = Path(__file__).parent.parent / "data" / "index.pkl"
INDEX_PAGE = Path(__file__).parent / "templates" / "index.html"
ALLOWED_FILTERS = {"product"}
VALID_PRODUCTS = {"Оріон X2", "Вега S", "Альтаїр AX3", "Сіріус R10"}


class AskRequest(BaseModel):
    question: str = Field(default="")
    filters: dict = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.index = None
    app.state.keyword_index = None
    try:
        if INDEX_PATH.exists():
            app.state.index = index.load(INDEX_PATH)
            app.state.keyword_index = keyword.build(app.state.index.chunks)
            print(f"Завантажено індекс: {len(app.state.index.chunks)} фрагментів.")
        else:
            print(f"Індекс не знайдено ({INDEX_PATH}). Запустіть: python ingest.py")
    except Exception as exc:
        print(f"Помилка завантаження індексу: {exc}")
        app.state.index = None
        app.state.keyword_index = None
    yield


app = FastAPI(title="RAG Assistant — ПР6", lifespan=lifespan)


def _validate_filters(filters: dict) -> dict:
    unknown = set(filters.keys()) - ALLOWED_FILTERS
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Невідомий фільтр: {', '.join(sorted(unknown))}",
        )
    cleaned = {k: v for k, v in filters.items() if v}
    product = cleaned.get("product")
    if product and product not in VALID_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Невідомий товар у фільтрі: {product}",
        )
    return cleaned


@app.get("/", response_class=HTMLResponse)
async def page() -> str:
    if INDEX_PAGE.exists():
        return INDEX_PAGE.read_text(encoding="utf-8")
    return "<h1>RAG API running</h1>"


@app.get("/api/status")
async def api_status() -> dict:
    idx = app.state.index
    if idx is None or not idx.chunks:
        return {
            "ready": False,
            "hint": "індекс не збудовано — виконайте python ingest.py",
        }
    sources = {chunk.source for chunk in idx.chunks}
    return {
        "ready": True,
        "chunks": len(idx.chunks),
        "documents": len(sources),
        "model": idx.model_name,
    }


@app.post("/api/ask")
def api_ask(payload: AskRequest) -> dict:
    if app.state.index is None:
        raise HTTPException(
            status_code=400,
            detail="Індекс не завантажено. Спочатку виконайте python ingest.py",
        )

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Питання не може бути порожнім.")

    filters = _validate_filters(payload.filters or {})

    try:
        result = rag.answer(
            question=question,
            index=app.state.index,
            keyword_index=app.state.keyword_index,
            filters=filters or None,
        )
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        print(f"Внутрішня помилка: {exc!r}")
        raise HTTPException(status_code=500, detail="Внутрішня помилка сервера.") from exc

    return rag.answer_to_dict(result)