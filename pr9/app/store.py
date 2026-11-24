"""Сховище стану звернень: JSON-файл на звернення, атомарний запис."""

import json
import os
import re
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .state import Run, Step

load_dotenv()

RUNS_DIR = Path(os.getenv("RUNS_DIR") or "runs")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def save(run: Run) -> None:
    """Тимчасовий файл у тому ж каталозі + fsync + os.replace: файл або
    старий, або новий, ніколи напівзаписаний."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run.updated_at = datetime.now(timezone.utc).isoformat()
    data = json.dumps(asdict(run), ensure_ascii=False, indent=1, default=str)
    fd, tmp = tempfile.mkstemp(dir=RUNS_DIR, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(5):          # Windows: файл може бути на мить зайнятий читачем
            try:
                os.replace(tmp, _path(run.run_id))
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load(run_id: str) -> Run | None:
    if not _ID.match(run_id or ""):
        return None
    try:
        d = json.loads(_path(run_id).read_text(encoding="utf-8"))
        d["steps"] = [Step(**s) for s in d.get("steps", [])]
        return Run(**d)
    except (OSError, ValueError, TypeError):
        return None


def list_runs(status: str | None = None) -> list[Run]:
    runs = []
    if RUNS_DIR.exists():
        for p in RUNS_DIR.glob("*.json"):
            run = load(p.stem)
            if run and (status is None or run.status == status):
                runs.append(run)
    runs.sort(key=lambda r: r.created_at or "", reverse=True)
    return runs