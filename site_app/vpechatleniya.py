"""Скрытая тестовая страница «Впечатления» — прямой адрес /v.

Публикация разрешена как живой тест, не как раздел сайта. Страницы нет в меню,
подвале, перелинковке и sitemap.xml. В robots.txt путь не закрыт: иначе робот
не увидит noindex. Запрет индекса — meta robots и заголовок X-Robots-Tag.

Каталог — утверждённый макет V7: вымышленные предложения, ориентировочные цены,
иллюстративные фото. Заявка никуда не уходит, оплаты и записи в базу нет.
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()

_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
_CREDITS = json.loads((_DIR / "data" / "vpechatleniya_credits.json").read_text(encoding="utf-8"))
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")


def _asset_rev() -> str:
    stamp = 0
    root = _DIR / "static" / "vpechatleniya"
    for path in root.rglob("*"):
        if path.is_file():
            stamp = max(stamp, int(path.stat().st_mtime))
    return str(stamp or 1)


REV = _asset_rev()


def _context(request: Request) -> dict:
    return {
        "request": request,
        "rev": REV,
        "notice": _CREDITS["notice"],
        "gaps": _CREDITS["gaps"],
        "credits": _CREDITS["photos"],
        "canonical_url": SITE_URL + "/v",
    }


@router.get("/v", include_in_schema=False)
@router.get("/v/", include_in_schema=False)
def vpechatleniya_preview(request: Request):
    response = templates.TemplateResponse("vpechatleniya.html", _context(request))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
