import random
import re
from html import escape, unescape
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from geoalchemy2.shape import to_shape
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Article, Category, Checkpoint, Trail
from site_app.content import (
    ACCESS_LABELS,
    DIFFICULTY_LABELS,
    DISTRICTS,
    POPULARITY_WEIGHT,
    SEASON_LABELS,
)

router = APIRouter()
templates = Jinja2Templates(directory="site_app/templates")

_POPULARITY_ORDER = case((Checkpoint.popularity == "top", 0), (Checkpoint.popularity == "popular", 1), else_=2)
_POPULARITY_ORDER_TRAIL = case((Trail.popularity == "top", 0), (Trail.popularity == "popular", 1), else_=2)


# ─────────────────────────────────────────────
#  Мелкие помощники форматирования
# ─────────────────────────────────────────────

def _excerpt(text: Optional[str], length: int = 140) -> str:
    if not text:
        return ""
    stripped = re.sub(r"<[^>]+>", " ", text)
    flat = " ".join(stripped.split())
    if len(flat) <= length:
        return flat
    return flat[:length].rsplit(" ", 1)[0] + "…"


def _duration_label(minutes: Optional[int]) -> Optional[str]:
    if not minutes:
        return None
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} ч {m} мин"
    if h:
        return f"{h} ч"
    return f"{m} мин"


def _rich_text_html(text: Optional[str]) -> str:
    """Текст из Quill-редактора (статьи, описания мест/маршрутов) уже HTML —
    отдаём как есть (авторизуется только через админку). Записи, заведённые
    до редактора, хранят обычный текст с пустой строкой между абзацами —
    оборачиваем их в <p> на лету."""
    if not text:
        return ""
    if "<" in text:
        return text
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "".join(f"<p>{escape(p)}</p>" for p in paragraphs)


_GALLERY_PARAGRAPH_RE = re.compile(r"<p>((?:\s*<img\b[^>]*>|\s*&nbsp;)+)\s*</p>", re.IGNORECASE)
_IMG_TAG_RE = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
_IMG_ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')


def _render_article_gallery(html: str) -> str:
    """Редактор статей (Quill) вставляет коллаж как несколько <img> подряд в
    одном <p>, с подписью в alt каждой картинки. Здесь на рендере страницы
    группируем такой параграф в галерею-коллаж со счётчиком "N/M" и подписью
    под каждым фото (визуально — как в Т—Ж). Параграфы с одной картинкой не
    трогаем — они остаются обычной вставкой на всю ширину."""

    def repl(match: "re.Match[str]") -> str:
        img_tags = _IMG_TAG_RE.findall(match.group(1))
        if len(img_tags) < 2:
            return match.group(0)
        total = len(img_tags)
        items = []
        for i, attrs_str in enumerate(img_tags, start=1):
            attrs = dict(_IMG_ATTR_RE.findall(attrs_str))
            src = unescape(attrs.get("src", ""))
            caption = unescape(attrs.get("alt", "")).strip()
            caption_html = ""
            if caption:
                caption_html = (
                    '<figcaption class="article-gallery-caption">'
                    f'<span class="article-gallery-counter">{i}/{total}</span>'
                    f'<span class="article-gallery-text">{escape(caption)}</span>'
                    '</figcaption>'
                )
            items.append(
                '<figure class="article-gallery-item">'
                f'<img src="{escape(src, quote=True)}" alt="{escape(caption, quote=True)}" loading="lazy">'
                f'{caption_html}'
                '</figure>'
            )
        return '<div class="article-gallery"><div class="article-gallery-track">' + "".join(items) + '</div></div>'

    return _GALLERY_PARAGRAPH_RE.sub(repl, html)


def _cover_of(photos) -> Optional[str]:
    return photos[0].url if photos else None


def _category_lite(cat) -> Optional[dict]:
    if not cat:
        return None
    return {"id": cat.id, "name": cat.name, "icon": cat.icon}


def _price_label(is_paid: bool, price_note: Optional[str]) -> str:
    if not is_paid:
        return "Бесплатно"
    return price_note or "Платно"


def _yandex_point_url(cp: Checkpoint) -> str:
    shp = to_shape(cp.geom)
    return f"https://yandex.ru/maps/?rtext=~{shp.y:.6f},{shp.x:.6f}&rtt=auto"


def _yandex_route_url(trail: Trail) -> Optional[str]:
    ordered = sorted(trail.checkpoints, key=lambda c: c.order_index)
    pts = []
    for cp in ordered:
        shp = to_shape(cp.geom)
        pts.append(f"{shp.y:.6f},{shp.x:.6f}")
    if not pts:
        return None
    return f"https://yandex.ru/maps/?rtext=~{'~'.join(pts)}&rtt=auto"


# ─────────────────────────────────────────────
#  Сериализация в карточки / детальные страницы
# ─────────────────────────────────────────────

def _place_card_dict(cp: Checkpoint) -> dict:
    return {
        "id": cp.id,
        "url": f"/mesta/{cp.id}",
        "name": cp.name,
        "excerpt": _excerpt(cp.description),
        "cover": _cover_of(cp.photos),
        "popularity": cp.popularity,
        "district_label": DISTRICTS.get(cp.district),
        "category": _category_lite(cp.category),
        "is_paid": cp.is_paid,
        "kid_friendly": cp.kid_friendly,
    }


def _route_card_dict(t: Trail) -> dict:
    return {
        "id": t.id,
        "url": f"/marshruty/{t.id}",
        "name": t.name,
        "excerpt": _excerpt(t.description),
        "cover": _cover_of(t.photos),
        "popularity": t.popularity,
        "district_label": DISTRICTS.get(t.district),
        "category": _category_lite(t.category),
        "difficulty_label": DIFFICULTY_LABELS.get(t.difficulty, t.difficulty),
        "duration_label": _duration_label(t.duration_minutes),
    }


def _article_card_dict(a: Article) -> dict:
    return {
        "id": a.id,
        "url": f"/stati/{a.slug}",
        "title": a.title,
        "excerpt": a.excerpt,
        "cover": a.cover_url,
        "district_label": DISTRICTS.get(a.district),
    }


def _place_detail_dict(cp: Checkpoint) -> dict:
    return {
        "id": cp.id,
        "name": cp.name,
        "description_html": _rich_text_html(cp.description),
        "cover": _cover_of(cp.photos),
        "photos": [p.url for p in cp.photos],
        "district_label": DISTRICTS.get(cp.district),
        "category": _category_lite(cp.category),
        "difficulty_label": DIFFICULTY_LABELS.get(cp.difficulty, cp.difficulty),
        "season_label": SEASON_LABELS.get(cp.seasonality, cp.seasonality),
        "access_label": ACCESS_LABELS.get(cp.access_type, cp.access_type),
        "price_label": _price_label(cp.is_paid, cp.price_note),
        "kid_friendly": cp.kid_friendly,
        "equipment_tags": cp.equipment_tags or [],
        "yandex_url": _yandex_point_url(cp),
        "trail": {"name": cp.trail.name, "url": f"/marshruty/{cp.trail.id}"} if cp.trail else None,
    }


def _route_detail_dict(t: Trail) -> dict:
    ordered_cps = sorted(t.checkpoints, key=lambda c: c.order_index)
    return {
        "id": t.id,
        "name": t.name,
        "description_html": _rich_text_html(t.description),
        "cover": _cover_of(t.photos),
        "district_label": DISTRICTS.get(t.district),
        "category": _category_lite(t.category),
        "difficulty_label": DIFFICULTY_LABELS.get(t.difficulty, t.difficulty),
        "duration_label": _duration_label(t.duration_minutes),
        "season_label": SEASON_LABELS.get(t.seasonality, t.seasonality),
        "access_label": ACCESS_LABELS.get(t.access_type, t.access_type),
        "price_label": _price_label(t.is_paid, t.price_note),
        "kid_friendly": t.kid_friendly,
        "equipment_tags": t.equipment_tags or [],
        "yandex_url": _yandex_route_url(t),
        "checkpoints": [
            {
                "name": cp.name,
                "url": f"/mesta/{cp.id}",
                "category_name": cp.category.name if cp.category else None,
            }
            for cp in ordered_cps
        ],
    }


# ─────────────────────────────────────────────
#  Общий контекст рендера
# ─────────────────────────────────────────────

def _footer_stats(db: Session) -> dict:
    places = db.execute(select(func.count()).select_from(Checkpoint)).scalar() or 0
    trails = db.execute(select(func.count()).select_from(Trail)).scalar() or 0
    return {"places": places, "trails": trails}


def _ctx(request: Request, db: Session, **extra) -> dict:
    base = {"request": request, "footer_stats": _footer_stats(db), "districts": DISTRICTS}
    base.update(extra)
    return base


# ─────────────────────────────────────────────
#  Случайное место/маршрут — взвешенный рандом
# ─────────────────────────────────────────────

def _pick_highlight(db: Session) -> dict:
    checkpoints = db.execute(select(Checkpoint)).scalars().all()
    trails = db.execute(select(Trail)).scalars().all()
    pool = [("place", cp) for cp in checkpoints] + [("route", t) for t in trails]

    if not pool:
        return {
            "name": "Пока пусто",
            "excerpt": "Добавьте места или маршруты в админке — здесь появится случайная подборка.",
            "cover": None,
            "tag_label": "Скоро",
            "url": "/",
        }

    weights = [POPULARITY_WEIGHT.get(obj.popularity, 6) for _, obj in pool]
    kind, obj = random.choices(pool, weights=weights, k=1)[0]

    if kind == "place":
        d = _place_card_dict(obj)
        d["tag_label"] = "Случайное место"
    else:
        d = _route_card_dict(obj)
        d["tag_label"] = "Случайный маршрут"
    return d


@router.get("/api/site/random")
def api_random(db: Session = Depends(get_db)):
    return _pick_highlight(db)


# ─────────────────────────────────────────────
#  Главная
# ─────────────────────────────────────────────

@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    highlight = _pick_highlight(db)
    articles = [
        _article_card_dict(a)
        for a in db.execute(
            select(Article).where(Article.is_published == True).order_by(Article.created_at.desc()).limit(6)
        ).scalars().all()
    ]
    places = [
        _place_card_dict(cp)
        for cp in db.execute(
            select(Checkpoint).order_by(_POPULARITY_ORDER, Checkpoint.created_at.desc()).limit(6)
        ).scalars().all()
    ]
    routes = [
        _route_card_dict(t)
        for t in db.execute(
            select(Trail).order_by(_POPULARITY_ORDER_TRAIL, Trail.created_at.desc()).limit(6)
        ).scalars().all()
    ]
    return templates.TemplateResponse(
        "home.html",
        _ctx(request, db, active_nav="home", highlight=highlight, articles=articles, places=places, routes=routes),
    )


# ─────────────────────────────────────────────
#  Места
# ─────────────────────────────────────────────

@router.get("/mesta")
def places_list(
    request: Request,
    type: Optional[str] = None,
    district: Optional[str] = None,
    paid: Optional[str] = None,
    kid: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = select(Checkpoint)
    if type and type.isdigit():
        q = q.where(Checkpoint.category_id == int(type))
    if district:
        q = q.where(Checkpoint.district == district)
    if paid == "0":
        q = q.where(Checkpoint.is_paid == False)
    elif paid == "1":
        q = q.where(Checkpoint.is_paid == True)
    if kid == "1":
        q = q.where(Checkpoint.kid_friendly == True)
    q = q.order_by(_POPULARITY_ORDER, Checkpoint.created_at.desc())

    places = [_place_card_dict(cp) for cp in db.execute(q).scalars().all()]
    categories = db.execute(
        select(Category).where(Category.is_public == True, Category.type.in_(["checkpoint", "both"]))
    ).scalars().all()

    selected = {"type": type or "", "district": district or "", "paid": paid or "", "kid": kid or ""}
    return templates.TemplateResponse(
        "places_list.html",
        _ctx(request, db, active_nav="places", places=places, categories=categories, selected=selected),
    )


@router.get("/mesta/{place_id}")
def place_detail(request: Request, place_id: int, db: Session = Depends(get_db)):
    cp = db.get(Checkpoint, place_id)
    if not cp:
        raise HTTPException(404, "Место не найдено")

    place = _place_detail_dict(cp)
    conditions = [c for c in [
        Checkpoint.district == cp.district if cp.district else None,
        Checkpoint.category_id == cp.category_id if cp.category_id else None,
    ] if c is not None]
    similar = []
    if conditions:
        rows = db.execute(
            select(Checkpoint).where(Checkpoint.id != cp.id, or_(*conditions)).limit(4)
        ).scalars().all()
        similar = [_place_card_dict(r) for r in rows]

    return templates.TemplateResponse(
        "place_detail.html", _ctx(request, db, active_nav="places", place=place, similar=similar)
    )


# ─────────────────────────────────────────────
#  Маршруты
# ─────────────────────────────────────────────

@router.get("/marshruty")
def routes_list(
    request: Request,
    type: Optional[str] = None,
    district: Optional[str] = None,
    difficulty: Optional[str] = None,
    kid: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = select(Trail)
    if type and type.isdigit():
        q = q.where(Trail.category_id == int(type))
    if district:
        q = q.where(Trail.district == district)
    if difficulty:
        q = q.where(Trail.difficulty == difficulty)
    if kid == "1":
        q = q.where(Trail.kid_friendly == True)
    q = q.order_by(_POPULARITY_ORDER_TRAIL, Trail.created_at.desc())

    routes = [_route_card_dict(t) for t in db.execute(q).scalars().all()]
    categories = db.execute(
        select(Category).where(Category.is_public == True, Category.type.in_(["trail", "both"]))
    ).scalars().all()

    selected = {"type": type or "", "district": district or "", "difficulty": difficulty or "", "kid": kid or ""}
    return templates.TemplateResponse(
        "routes_list.html",
        _ctx(request, db, active_nav="routes", routes=routes, categories=categories, selected=selected),
    )


@router.get("/marshruty/{route_id}")
def route_detail(request: Request, route_id: int, db: Session = Depends(get_db)):
    t = db.get(Trail, route_id)
    if not t:
        raise HTTPException(404, "Маршрут не найден")

    route = _route_detail_dict(t)
    conditions = [c for c in [
        Trail.district == t.district if t.district else None,
        Trail.category_id == t.category_id if t.category_id else None,
    ] if c is not None]
    similar = []
    if conditions:
        rows = db.execute(
            select(Trail).where(Trail.id != t.id, or_(*conditions)).limit(4)
        ).scalars().all()
        similar = [_route_card_dict(r) for r in rows]

    return templates.TemplateResponse(
        "route_detail.html", _ctx(request, db, active_nav="routes", route=route, similar=similar)
    )


# ─────────────────────────────────────────────
#  Статьи
# ─────────────────────────────────────────────

@router.get("/stati")
def articles_list(request: Request, db: Session = Depends(get_db)):
    arts = db.execute(
        select(Article).where(Article.is_published == True).order_by(Article.created_at.desc())
    ).scalars().all()
    return templates.TemplateResponse(
        "articles_list.html",
        _ctx(request, db, active_nav="articles", articles=[_article_card_dict(a) for a in arts]),
    )


@router.get("/stati/{slug}")
def article_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    a = db.execute(select(Article).where(Article.slug == slug)).scalars().first()
    if not a:
        raise HTTPException(404, "Статья не найдена")

    featured_places = []
    for cid in a.featured_checkpoint_ids or []:
        cp = db.get(Checkpoint, cid)
        if cp:
            featured_places.append(_place_card_dict(cp))

    featured_routes = []
    for tid in a.featured_trail_ids or []:
        t = db.get(Trail, tid)
        if t:
            featured_routes.append(_route_card_dict(t))

    article = {
        "title": a.title,
        "district_label": DISTRICTS.get(a.district),
        "cover_url": a.cover_url,
        "body_html": _render_article_gallery(_rich_text_html(a.body)),
        "featured_places": featured_places,
        "featured_routes": featured_routes,
    }

    similar_places = []
    if a.district:
        exclude_ids = set(a.featured_checkpoint_ids or [])
        rows = db.execute(
            select(Checkpoint).where(Checkpoint.district == a.district, Checkpoint.id.notin_(exclude_ids)).limit(4)
        ).scalars().all()
        similar_places = [_place_card_dict(r) for r in rows]

    return templates.TemplateResponse(
        "article_detail.html",
        _ctx(request, db, active_nav="articles", article=article, similar_places=similar_places),
    )


# ─────────────────────────────────────────────
#  Клуб (заглушка)
# ─────────────────────────────────────────────

@router.get("/klub")
def club(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("club.html", _ctx(request, db, active_nav="club"))
