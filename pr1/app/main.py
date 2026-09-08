from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse

from . import weather

app = FastAPI(title="Погода — ПР1")

INDEX_PAGE = Path(__file__).parent / "templates" / "index.html"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_PAGE.read_text(encoding="utf-8")


@app.get("/api/weather")
def api_weather(city: str):
    try:
        return weather.get_current_weather(city)
    except weather.CityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except weather.ApiServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except weather.WeatherError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутрішня помилка сервера",
        )