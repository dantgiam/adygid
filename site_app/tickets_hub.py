"""Черновик хаба «Входные и наличные 2026».

Адрес /chernovik/vhodnye-2026. Нет в меню, подвале и sitemap.
Запрет индекса — meta robots и X-Robots-Tag. База не нужна.
Два варианта вёрстки одного черновика: таблица и статьи.
"""
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from site_app.data.tickets_hub import CHECKLIST, ROWS, SOURCES

router = APIRouter()
_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")


def _rev() -> str:
    stamp = 0
    for path in (
        _DIR / "static" / "tickets-hub.css",
        _DIR / "templates" / "tickets_hub.html",
        _DIR / "data" / "tickets_hub.py",
    ):
        if path.is_file():
            stamp = max(stamp, int(path.stat().st_mtime))
    return str(stamp or 1)


def _ctx(request: Request, variant: str) -> dict:
    return {
        "request": request,
        "rev": _rev(),
        "site_url": SITE_URL,
        "canonical_url": SITE_URL + "/chernovik/vhodnye-2026",
        "variant": variant,
        "rows": ROWS,
        "sources": SOURCES,
        "checklist": CHECKLIST,
    }


@router.get("/chernovik/vhodnye-2026", include_in_schema=False)
def tickets_hub(request: Request, v: str = "tablitsa"):
    variant = "statyi" if v == "statyi" else "tablitsa"
    response = templates.TemplateResponse("tickets_hub.html", _ctx(request, variant))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/chernovik/vhodnye-2026/", include_in_schema=False)
def tickets_hub_slash(v: str = "tablitsa"):
    q = "?v=statyi" if v == "statyi" else ""
    return RedirectResponse("/chernovik/vhodnye-2026" + q, status_code=307)
