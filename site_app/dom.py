"""Пилот лендинга домика для QR/NFC-табличек — адрес /dom/<код>.

Страницы нет в меню, подвале, перелинковке и sitemap.xml. В robots.txt путь
не закрыт: иначе робот не увидит noindex. Запрет индекса — meta robots и
заголовок X-Robots-Tag.

Каталог домов пока живёт в коде (site_app/data/dom_houses.py), без базы:
так макет можно открыть и проверить без Postgres. Настоящие объекты можно
будет перенести в таблицу, когда появятся проверенные тексты.
"""
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from site_app.data.dom_houses import BOT_MAX, BOT_TG, HOUSES, VARIANTS, get_house

router = APIRouter()

_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")
CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")


def _asset_rev() -> str:
    stamp = 0
    for path in (
        _DIR / "static" / "dom.css",
        _DIR / "static" / "site.css",
        _DIR / "data" / "dom_houses.py",
        _DIR / "templates" / "dom.html",
        _DIR / "templates" / "dom_index.html",
    ):
        if path.is_file():
            stamp = max(stamp, int(path.stat().st_mtime))
    return str(stamp or 1)


REV = _asset_rev()


def bot_links(code: str) -> dict:
    payload = f"dom_{code}"
    return {"max": f"{BOT_MAX}?start={payload}", "telegram": f"{BOT_TG}?start={payload}"}


def _base_ctx(request: Request) -> dict:
    return {
        "request": request,
        "rev": REV,
        "site_url": SITE_URL,
        "bot_max": BOT_MAX,
        "bot_tg": BOT_TG,
    }


@router.get("/dom", include_in_schema=False)
def dom_index(request: Request):
    ctx = _base_ctx(request)
    ctx.update(
        {
            "canonical_url": SITE_URL + "/dom",
            "variants": VARIANTS,
            "houses": HOUSES,
        }
    )
    response = templates.TemplateResponse("dom_index.html", ctx)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/dom/", include_in_schema=False)
def dom_index_slash():
    return RedirectResponse("/dom", status_code=307)


@router.get("/dom/{code}", include_in_schema=False)
def dom_house(code: str, request: Request):
    if not CODE_RE.match(code) or get_house(code) is None:
        raise HTTPException(status_code=404, detail="Дом с таким кодом не найден")
    house = get_house(code)
    ctx = _base_ctx(request)
    ctx.update(
        {
            "house": house,
            "bots": bot_links(code),
            "canonical_url": f"{SITE_URL}/dom/{code}",
        }
    )
    response = templates.TemplateResponse("dom.html", ctx)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/dom/{code}/", include_in_schema=False)
def dom_house_slash(code: str):
    if not CODE_RE.match(code) or get_house(code) is None:
        raise HTTPException(status_code=404, detail="Дом с таким кодом не найден")
    return RedirectResponse(f"/dom/{code}", status_code=307)
