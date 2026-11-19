"""Локальный сервер превью блока «Коротко для поездки». База не нужна."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from site_app.trip_brief_preview import router
app = FastAPI()
app.mount("/assets", StaticFiles(directory=str(ROOT / "site_app" / "static")), name="assets")
app.include_router(router)
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8013")), log_level="warning")
