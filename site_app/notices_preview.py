"""Скрытый разбор вариантов плашки «праздники и очереди».

Адрес /chernovik/preduprezhdeniya. Нет в меню, подвале и sitemap.
Запрет индекса — meta robots и X-Robots-Tag. База не нужна.
"""
import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from site_app.travel_notices import GENERIC_TIPS, SOURCES, holiday_notice

router = APIRouter()
_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")


def _rev() -> str:
    stamp = 0
    for path in (
        _DIR / "static" / "notices.css",
        _DIR / "templates" / "notices_preview.html",
        _DIR / "travel_notices.py",
    ):
        if path.is_file():
            stamp = max(stamp, int(path.stat().st_mtime))
    return str(stamp or 1)


@router.get("/chernovik/preduprezhdeniya", include_in_schema=False)
def notices_preview(request: Request):
    today = date.today()
    ctx = {
        "request": request,
        "rev": _rev(),
        "site_url": SITE_URL,
        "canonical_url": SITE_URL + "/chernovik/preduprezhdeniya",
        "today": today.strftime("%d.%m.%Y"),
        "demo_notice": holiday_notice(today, season="winter"),
        "tips": GENERIC_TIPS,
        "sources": SOURCES,
    }
    response = templates.TemplateResponse("notices_preview.html", ctx)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/chernovik/preduprezhdeniya/", include_in_schema=False)
def notices_preview_slash():
    return RedirectResponse("/chernovik/preduprezhdeniya", status_code=307)
