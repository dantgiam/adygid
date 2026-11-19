"""Скрытые черновики летних статей. База не нужна."""
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from site_app.data.summer_drafts import ARTICLES, CHECKED, SOURCES

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
router = APIRouter()
PHOTO_RE = re.compile(r"\[\[PHOTO\s+(.+?)\]\]")
BY_SLUG = {a["slug"]: a for a in ARTICLES}


def render_body(html: str) -> str:
    def repl(m):
        cap = m.group(1).strip()
        return (
            f'<figure class="sd-photo"><span class="sd-photo-mark">[[PHOTO]]</span>'
            f"<figcaption>{cap}</figcaption></figure>"
        )
    return PHOTO_RE.sub(repl, html)


def article_ctx(art: dict, request: Request) -> dict:
    src = [SOURCES[k] for k in art["source_keys"] if k in SOURCES]
    return {
        "request": request,
        "article": art,
        "body": render_body(art["body"]),
        "sources": src,
        "checked": CHECKED,
        "rev": int(datetime.now().timestamp()),
        "canonical_url": str(request.base_url).rstrip("/") + f"/chernovik/leto/{art['slug']}",
    }


@router.get("/chernovik/leto/", include_in_schema=False)
def index_slash():
    return RedirectResponse("/chernovik/leto", status_code=307)


@router.get("/chernovik/leto", include_in_schema=False)
def index(request: Request):
    response = templates.TemplateResponse(
        "summer_drafts_index.html",
        {
            "request": request,
            "articles": ARTICLES,
            "checked": CHECKED,
            "rev": int(datetime.now().timestamp()),
            "canonical_url": str(request.base_url).rstrip("/") + "/chernovik/leto",
        },
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/chernovik/leto/{slug}/", include_in_schema=False)
def article_slash(slug: str):
    return RedirectResponse(f"/chernovik/leto/{slug}", status_code=307)


@router.get("/chernovik/leto/{slug}", include_in_schema=False)
def article(request: Request, slug: str):
    art = BY_SLUG.get(slug)
    if not art:
        return HTMLResponse("Черновик не найден", status_code=404)
    response = templates.TemplateResponse("summer_draft.html", article_ctx(art, request))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
