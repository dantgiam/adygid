"""Страница домика для таблички QR/NFC: /dom/<код>.

Страницы нет в меню, подвале, перелинковке и sitemap.xml. В robots.txt путь
не закрыт: иначе робот не увидит noindex. Запрет индекса — meta robots и
заголовок X-Robots-Tag.

Каталог домов живёт в site_app/data/dom_houses.py. Места и маршруты рядом
читаются из базы сайта и при недоступной базе просто не показываются.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.database import SessionLocal
from site_app.data.dom_houses import HOUSES, get_house
from site_app.dom_nearby import load_catalog
from site_app.router import REVIEW_BOT, REVIEW_BOT_TG, YANDEX_METRIKA_ID, _footer_stats, templates

router = APIRouter()

_DIR = Path(__file__).resolve().parent
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")
CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")


def _asset_rev() -> str:
    stamp = 0
    files = [
        _DIR / "static" / "dom.css",
        _DIR / "static" / "dom.js",
        _DIR / "static" / "site.css",
        _DIR / "data" / "dom_houses.py",
        _DIR / "templates" / "dom.html",
        _DIR / "templates" / "dom_index.html",
        _DIR / "static" / "dom" / "rules-key.webp",
    ]
    for folder in ("demo", "places"):
        photo_dir = _DIR / "static" / "dom" / folder
        if photo_dir.is_dir():
            files.extend(photo_dir.glob("*.webp"))
    for path in files:
        if path.is_file():
            stamp = max(stamp, int(path.stat().st_mtime))
    return str(stamp or 1)


REV = _asset_rev()


def bot_links(code: str) -> dict:
    guest = f"dom_{code}"
    return {
        "telegram": f"{REVIEW_BOT_TG}?start={guest}",
        "max": f"{REVIEW_BOT}?start={guest}",
        "host_telegram": f"{REVIEW_BOT_TG}?start=dom_host",
        "host_max": f"{REVIEW_BOT}?start=dom_host",
    }


def _footer() -> dict:
    """Подвал сайта. Если базы нет, страница дома всё равно открывается."""
    try:
        db = SessionLocal()
    except Exception:
        return {"places": 0, "trails": 0}
    try:
        return _footer_stats(db)
    except Exception:
        return {"places": 0, "trails": 0}
    finally:
        db.close()


def _base(request: Request) -> dict:
    return {
        "request": request,
        "rev": REV,
        "asset_version": REV,
        "site_url": SITE_URL,
        "footer_stats": _footer(),
        "yandex_metrika_id": YANDEX_METRIKA_ID,
        "media_origin": "",
    }


def _known(code: str) -> dict:
    if not CODE_RE.match(code):
        raise HTTPException(status_code=404, detail="Дом с таким кодом не найден")
    house = get_house(code)
    if house is None:
        raise HTTPException(status_code=404, detail="Дом с таким кодом не найден")
    return house


@router.get("/dom", include_in_schema=False)
def dom_index(request: Request):
    ctx = _base(request)
    ctx.update({"canonical_url": SITE_URL + "/dom", "houses": HOUSES})
    response = templates.TemplateResponse(request, "dom_index.html", ctx)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/dom/", include_in_schema=False)
def dom_index_slash():
    return RedirectResponse("/dom", status_code=307)


@router.get("/dom/{code}", include_in_schema=False)
def dom_house(code: str, request: Request):
    house = _known(code)
    origin = house["origin"]
    catalog = load_catalog(origin["lat"], origin["lon"], house["place_limit"], house["route_limit"])
    ctx = _base(request)
    ctx.update({
        "house": house,
        "bots": bot_links(code),
        "catalog": catalog,
        "canonical_url": f"{SITE_URL}/dom/{code}",
        "og_image": SITE_URL + house["gallery"][0]["src"],
    })
    response = templates.TemplateResponse(request, "dom.html", ctx)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/dom/{code}/", include_in_schema=False)
def dom_house_slash(code: str):
    _known(code)
    return RedirectResponse(f"/dom/{code}", status_code=307)
