from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status
from fastapi.responses import HTMLResponse
from . import detector

app = FastAPI(title="Детекція обʼєктів — ПР2")

INDEX_PAGE = Path(__file__).parent / "templates" / "index.html"

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_PAGE.read_text(encoding="utf-8")

@app.post("/api/detect")
async def api_detect(
    image: UploadFile = File(...),
    confidence: float = Form(detector.DEFAULT_CONFIDENCE)
):
    content = await image.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Порожній файл"
        )
    
    try:
        return detector.detect(content, confidence=confidence)
    except detector.InvalidImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=str(exc)
        )
    except detector.DetectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=str(exc)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Внутрішня помилка сервера"
        )