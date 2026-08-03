import json
import os
import random
import re
import time
import uuid
from html import escape, unescape
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from geoalchemy2.shape import to_shape
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.models import Article, Category, Checkpoint, FaqSet, Like, Magnet, Scenario, SitePage, Trail
from site_app.content import (
    ACCESS_LABELS,
    CLUB_URL,
    DIFFICULTY_INFO,
    DIFFICULTY_LABELS,
    DISTRICT_PAGES,
    DISTRICTS,
    POPULARITY_WEIGHT,
    SEASON_LABELS,
)

router = APIRouter()
templates = Jinja2Templates(directory="site_app/templates")

# Канонический адрес сайта — нужен для canonical/og:url и sitemap.xml.
# На Railway задаётся переменной SITE_URL, локально падает на localhost.
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")
# Номер счётчика Яндекс.Метрики. Пусто — счётчик не подключается (локальная
# разработка не должна плодить визиты в статистике).
YANDEX_METRIKA_ID = os.getenv("YANDEX_METRIKA_ID", "").strip()


def _asset_version() -> str:
    """Стили, скрипты и картинки лид-магнита отдаются с недельным кэшем,
    поэтому в ссылку добавляем метку версии: после правки файла адрес
    меняется, и браузер забирает новую версию сразу, а не через неделю."""
    stamp = 0
    names = ["site.css", "site.js", "magnet-gift.png", "magnet-tg.png", "magnet-max.png"]
    for name in names:
        try:
            stamp = max(stamp, int(os.path.getmtime(os.path.join("site_app", "static", name))))
        except OSError:
            pass
    return str(stamp or 1)


ASSET_VERSION = _asset_version()

_POPULARITY_ORDER = case((Checkpoint.popularity == "top", 0), (Checkpoint.popularity == "popular", 1), else_=2)
_POPULARITY_ORDER_TRAIL = case((Trail.popularity == "top", 0), (Trail.popularity == "popular", 1), else_=2)


# Карточка каждого места/маршрута читает фото и категорию. Без явной подгрузки
# SQLAlchemy делает это отдельным запросом на каждую карточку — на списке из
# десятка объектов набегали десятки обращений к удалённой базе, и страница
# ждала их последовательно. Догружаем всё пачкой вместе с основной выборкой.
def _with_place_relations(stmt):
    # is_published фильтруется прямо здесь: этим select() пользуются и списки,
    # и страница самого места — скрытая точка не должна открываться и по
    # прямой ссылке, иначе переключатель в админке ничего не скрывает.
    return stmt.options(selectinload(Checkpoint.photos), joinedload(Checkpoint.category)) \
        .where(Checkpoint.is_published == True)


def _with_route_relations(stmt):
    return stmt.options(selectinload(Trail.photos), joinedload(Trail.category)) \
        .where(Trail.is_published == True)


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


_MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _updated_label(dt) -> Optional[str]:
    """«Актуально на 26 июля 2026» — для описаний с ценами и состоянием троп
    свежесть важнее, чем дата первой публикации."""
    if not dt:
        return None
    return f"Актуально на {dt.day} {_MONTHS_RU[dt.month - 1]} {dt.year}"


def _site_page(db: Session, slug: str) -> dict:
    """Текст шапки главной / страницы клуба — правится в админке (SitePage),
    засеян дефолтом при первом старте, поэтому строка есть всегда."""
    p = db.execute(select(SitePage).where(SitePage.slug == slug)).scalars().first()
    if not p:
        return {"eyebrow": "", "title": "", "lead": "", "lead_extra": "", "button_text": ""}
    return {
        "eyebrow": p.eyebrow or "", "title": p.title or "", "lead": p.lead or "",
        "lead_extra": p.lead_extra or "", "button_text": p.button_text or "",
    }


def _likes_label(count: int) -> str:
    n = abs(count) % 100
    n1 = n % 10
    word = "человек" if (11 <= n <= 14 or n1 in (0, 1) or n1 >= 5) else "человека"
    return f"Оценили: {count} {word}"


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


_H2_RE = re.compile(r"<h2(?![^>]*\bid=)([^>]*)>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _add_toc_anchors(html: str) -> tuple[str, list[dict]]:
    """Проставляет id каждому <h2> без собственного id и параллельно
    собирает список якорей для бокового оглавления длинной статьи."""
    toc: list[dict] = []

    def repl(match: "re.Match[str]") -> str:
        attrs, inner = match.group(1), match.group(2)
        anchor = f"section-{len(toc) + 1}"
        title = _TAG_STRIP_RE.sub("", inner).strip()
        toc.append({"id": anchor, "title": title})
        return f'<h2{attrs} id="{anchor}">{inner}</h2>'

    return _H2_RE.sub(repl, html), toc


_GALLERY_PARAGRAPH_RE = re.compile(r"<p>((?:\s*<img\b[^>]*>|\s*&nbsp;)+)\s*</p>", re.IGNORECASE)
_IMG_TAG_RE = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
_IMG_ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')


def _render_article_gallery(html: str) -> str:
    """Редактор статей (Quill) вставляет фото как <img> внутри <p>, с подписью
    в alt каждой картинки. Здесь на рендере страницы несколько картинок подряд
    группируем в галерею-коллаж со счётчиком "N/M", а одиночное фото с подписью
    оборачиваем в <figure> с подписью под ним (визуально — как в Т—Ж).
    Фото без подписи остаётся обычной вставкой на всю ширину."""

    def repl(match: "re.Match[str]") -> str:
        img_tags = _IMG_TAG_RE.findall(match.group(1))
        if len(img_tags) < 2:
            if not img_tags:
                return match.group(0)
            attrs = dict(_IMG_ATTR_RE.findall(img_tags[0]))
            caption = unescape(attrs.get("alt", "")).strip()
            if not caption:
                return match.group(0)
            src = unescape(attrs.get("src", ""))
            return (
                '<figure class="article-figure">'
                f'<img src="{escape(src, quote=True)}" alt="{escape(caption, quote=True)}" loading="lazy">'
                f'<figcaption>{escape(caption)}</figcaption>'
                '</figure>'
            )
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


_MAGNET_EMBED_RE = re.compile(r'<div[^>]*data-magnet-id="(\d+)"[^>]*>\s*</div>', re.IGNORECASE)
_FAQ_EMBED_RE = re.compile(r'<div[^>]*data-faq-id="(\d+)"[^>]*>\s*</div>', re.IGNORECASE)
_CONSIDER_EMBED_RE = re.compile(r'<div[^>]*data-tips="([^"]*)"[^>]*>\s*</div>', re.IGNORECASE)


def _magnet_html(m) -> str:
    """Блок лид-магнита — двухъярусная карточка: сверху приманка (иконка
    подарка, заголовок, текст), снизу яркая CTA-полоса с кнопками мессенджеров.
    Обе ссылки, если заданы обе, показаны сразу — это один клик до перехода,
    а не скрытый выбор за <details>, как было раньше. Иконки — настоящие
    картинки из site_app/static (magnet-gift/tg/max), не эмодзи и не SVG."""
    links = [(u, label, cls, src) for u, label, cls, src in (
        (m.telegram_url, "Telegram", "magnet-pill-tg", f"/assets/magnet-tg.png?v={ASSET_VERSION}"),
        (m.max_url, "MAX", "magnet-pill-max", f"/assets/magnet-max.png?v={ASSET_VERSION}"),
    ) if u]
    if not links:
        return ""   # кнопка в никуда — лучше не показывать блок вовсе

    text_html = f'<p class="magnet-text">{escape(m.text)}</p>' if m.text else ""
    note_html = f'<p class="magnet-note">{escape(m.note)}</p>' if m.note else ""
    pills = "".join(
        f'<a class="magnet-pill {cls}" href="{escape(u, quote=True)}" target="_blank" rel="noopener">'
        f'<img src="{src}" alt="" loading="lazy"><span>{label}</span></a>'
        for u, label, cls, src in links
    )

    return (
        '<aside class="magnet">'
        '<div class="magnet-top">'
        f'<img class="magnet-gift" src="/assets/magnet-gift.png?v={ASSET_VERSION}" alt="" loading="lazy">'
        f'<div class="magnet-copy"><p class="magnet-title">{escape(m.title)}</p>{text_html}</div>'
        '</div>'
        '<div class="magnet-cta">'
        '<div class="magnet-cta-copy"><span class="magnet-cta-kicker">Забирайте</span>'
        f'<span class="magnet-cta-text">Бесплатно</span>{note_html}</div>'
        f'<div class="magnet-actions">{pills}</div>'
        '</div>'
        '</aside>'
    )


def _faq_html(f) -> str:
    items = f.items or []
    if not items:
        return ""
    rows = "".join(
        '<details class="faq-item">'
        f'<summary>{escape(item.get("question", ""))}</summary>'
        f'<div class="faq-answer">{_rich_text_html(item.get("answer", ""))}</div>'
        '</details>'
        for item in items
    )
    title = f'<h4>{escape(f.title)}</h4>' if f.title else '<h4>Частые вопросы</h4>'
    return f'<div class="faq-block">{title}{rows}</div>'


def _consider_html(tips_json: str) -> str:
    try:
        tips = json.loads(unescape(tips_json))
    except (ValueError, TypeError):
        return ""
    tips = [t for t in tips if isinstance(t, str) and t.strip()]
    if not tips:
        return ""
    items = "".join(f"<li>{escape(t)}</li>" for t in tips)
    return f'<div class="facts"><h4>Что учесть</h4><ul>{items}</ul></div>'


def _render_consider_blocks(html: str) -> str:
    """Разворачивает локальные вставки блока «Что учесть» — в отличие от
    лид-магнитов и наборов вопросов, советы не хранятся отдельной таблицей,
    их список лежит прямо в data-tips вставки (см. site_app/content.py)."""
    if not html or "data-tips" not in html:
        return html
    return _CONSIDER_EMBED_RE.sub(lambda mt: _consider_html(mt.group(1)), html)


def _render_embeds(db: Session, html: str) -> tuple[str, list]:
    """Подставляет в текст статьи содержимое вставленных блоков — лид-магнитов
    и наборов вопросов. В самой статье хранится только ссылка на id, поэтому
    правка блока в админке обновляет все статьи, где он вставлен.
    Возвращает готовый HTML и список вопросов для общей JSON-LD разметки."""
    collected_faq: list = []
    html = _render_consider_blocks(html)

    magnet_ids = [int(i) for i in set(_MAGNET_EMBED_RE.findall(html))]
    if magnet_ids:
        magnets = {
            m.id: m for m in db.execute(
                select(Magnet).where(Magnet.id.in_(magnet_ids), Magnet.is_published == True)
            ).scalars().all()
        }
        html = _MAGNET_EMBED_RE.sub(
            lambda mt: _magnet_html(magnets[int(mt.group(1))]) if int(mt.group(1)) in magnets else "",
            html,
        )

    faq_ids = [int(i) for i in set(_FAQ_EMBED_RE.findall(html))]
    if faq_ids:
        sets = {
            f.id: f for f in db.execute(
                select(FaqSet).where(FaqSet.id.in_(faq_ids), FaqSet.is_published == True)
            ).scalars().all()
        }
        for fid in faq_ids:
            if fid in sets:
                collected_faq.extend(sets[fid].items or [])
        html = _FAQ_EMBED_RE.sub(
            lambda mt: _faq_html(sets[int(mt.group(1))]) if int(mt.group(1)) in sets else "",
            html,
        )

    return html, collected_faq


def _cover_of(photos) -> Optional[str]:
    """Полноразмерное фото — для крупной обложки на детальной странице."""
    return photos[0].url if photos else None


def _thumb_of(photos) -> Optional[str]:
    """Для карточек берём миниатюру: оригиналы весят мегабайты, а показываются
    полоской в 150px. Миниатюры создаются при загрузке — просто используем их."""
    if not photos:
        return None
    return photos[0].thumb_url or photos[0].url


def _gallery_of(photos) -> list:
    """Данные для карусели на странице места/маршрута: полный размер (не
    миниатюра — карусель на весь экран, мылить незачем) плюс подпись."""
    return [{"url": p.url, "caption": p.caption or ""} for p in photos]


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


def _weather_url(lat: float, lon: float) -> str:
    return f"https://yandex.ru/pogoda/?lat={lat:.6f}&lon={lon:.6f}"


def _difficulty_info(code: Optional[str]) -> dict:
    """Точки-индикатор + текст подсказки для текущего уровня сложности —
    вся шкала уходит в шаблон отдельно (DIFFICULTY_INFO), чтобы попап
    показывал все 4 уровня сразу, а не только выбранный."""
    info = DIFFICULTY_INFO.get(code, {})
    return {
        "code": code,
        "label": DIFFICULTY_LABELS.get(code, code),
        "dots": info.get("dots", 0),
    }


def _nearby_places(db: Session, lat: float, lon: float, exclude_id: Optional[int] = None, limit: int = 4) -> list:
    """Места поблизости по прямой — используем ту же геопривязку, что и
    /api/checkpoints/nearby в админке, только отдаём в публичном формате
    карточки с добавленным расстоянием."""
    point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    dist = func.ST_DistanceSphere(Checkpoint.geom, point).label("distance_m")
    q = _with_place_relations(select(Checkpoint, dist)).where(Checkpoint.show_as_place == True)
    if exclude_id is not None:
        q = q.where(Checkpoint.id != exclude_id)
    q = q.order_by(dist).limit(limit)
    result = []
    for cp, distance_m in db.execute(q).all():
        card = _place_card_dict(cp)
        card["distance_label"] = f"{distance_m / 1000:.1f} км"
        result.append(card)
    return result


def _routes_for_place(db: Session, cp: Checkpoint, radius_km: float = 12.0, limit: int = 4) -> list:
    """Обратная связь точка → маршрут. Сначала маршрут, частью которого точка
    является, затем маршруты, чьи точки проходят поблизости — чтобы у
    отдельно стоящих мест тоже была связь с маршрутами, а не только наоборот."""
    cards, seen = [], set()

    if cp.trail and cp.trail.is_published:
        card = _route_card_dict(cp.trail)
        card["relation"] = "Место на этом маршруте"
        cards.append(card)
        seen.add(cp.trail.id)

    shp = to_shape(cp.geom)
    point = func.ST_SetSRID(func.ST_MakePoint(shp.x, shp.y), 4326)
    # selectinload, а не joinedload: запрос уже с GROUP BY, и дополнительные
    # колонки из JOIN-а его сломают.
    rows = db.execute(
        select(Trail, func.min(func.ST_DistanceSphere(Checkpoint.geom, point)).label("d"))
        .options(selectinload(Trail.photos), selectinload(Trail.category))
        .join(Checkpoint, Checkpoint.trail_id == Trail.id)
        .where(Checkpoint.id != cp.id, Trail.is_published == True)
        .group_by(Trail.id)
        .having(func.min(func.ST_DistanceSphere(Checkpoint.geom, point)) < radius_km * 1000)
        .order_by("d")
        .limit(limit + len(seen))
    ).all()

    for trail, distance_m in rows:
        if trail.id in seen:
            continue
        card = _route_card_dict(trail)
        card["relation"] = f"Проходит в {distance_m / 1000:.1f} км отсюда"
        cards.append(card)
        seen.add(trail.id)

    return cards[:limit]


# ─────────────────────────────────────────────
#  Лайк «Пригодилось» — анонимный счётчик без аккаунтов
# ─────────────────────────────────────────────

VISITOR_COOKIE = "vid"
_LIKE_SUBJECT_TYPES = {"checkpoint", "trail", "scenario"}

# Троттлинг по IP в памяти процесса — не рассчитан на несколько инстансов за
# балансировщиком, но для личного гид-сайта с одним воркером этого достаточно
# как страховка от скрипта, а не как криптографическая защита.
_LIKE_RATE_LIMIT: dict[str, list[float]] = {}
_LIKE_RATE_WINDOW_S = 60
_LIKE_RATE_MAX = 20


def _rate_limit_ok(ip: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _LIKE_RATE_LIMIT.get(ip, []) if now - t < _LIKE_RATE_WINDOW_S]
    hits.append(now)
    _LIKE_RATE_LIMIT[ip] = hits
    return len(hits) <= _LIKE_RATE_MAX


def _get_visitor_id(request: Request) -> Optional[str]:
    return request.cookies.get(VISITOR_COOKIE)


def _like_count(db: Session, subject_type: str, subject_id: int) -> int:
    return db.execute(
        select(func.count()).select_from(Like).where(
            Like.subject_type == subject_type, Like.subject_id == subject_id
        )
    ).scalar() or 0


def _like_info(db: Session, request: Request, subject_type: str, subject_id: int) -> dict:
    voter_id = _get_visitor_id(request)
    liked = False
    if voter_id:
        liked = db.execute(
            select(Like.id).where(
                Like.subject_type == subject_type,
                Like.subject_id == subject_id,
                Like.voter_id == voter_id,
            )
        ).first() is not None
    return {"count": _like_count(db, subject_type, subject_id), "liked": liked}


def _like_counts_map(db: Session, subject_type: str, ids: list) -> dict:
    """Батч-версия _like_count — одним запросом для списка карточек (главная),
    вместо запроса на каждую карточку по отдельности."""
    if not ids:
        return {}
    rows = db.execute(
        select(Like.subject_id, func.count()).where(
            Like.subject_type == subject_type, Like.subject_id.in_(ids)
        ).group_by(Like.subject_id)
    ).all()
    return {subject_id: count for subject_id, count in rows}


@router.post("/api/likes/{subject_type}/{subject_id}")
def toggle_like(subject_type: str, subject_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    if subject_type not in _LIKE_SUBJECT_TYPES:
        raise HTTPException(404, "Неизвестный тип")

    ip = request.client.host if request.client else "unknown"
    if not _rate_limit_ok(ip):
        raise HTTPException(429, "Слишком много запросов, попробуйте чуть позже")

    voter_id = _get_visitor_id(request)
    if not voter_id:
        voter_id = uuid.uuid4().hex
        # Год — не сессия браузера: возвращаясь через неделю, тот же лайк не
        # должен засчитаться второй раз.
        response.set_cookie(VISITOR_COOKIE, voter_id, max_age=365 * 24 * 3600, httponly=True, samesite="lax")

    existing = db.execute(
        select(Like).where(
            Like.subject_type == subject_type,
            Like.subject_id == subject_id,
            Like.voter_id == voter_id,
        )
    ).scalars().first()

    if existing:
        db.delete(existing)
        db.commit()
        liked = False
    else:
        db.add(Like(subject_type=subject_type, subject_id=subject_id, voter_id=voter_id))
        db.commit()
        liked = True

    return {"liked": liked, "count": _like_count(db, subject_type, subject_id)}


# ─────────────────────────────────────────────
#  Сериализация в карточки / детальные страницы
# ─────────────────────────────────────────────

def _place_card_dict(cp: Checkpoint) -> dict:
    return {
        "id": cp.id,
        "url": f"/mesta/{cp.id}",
        "name": cp.name,
        "excerpt": _excerpt(cp.description),
        "cover": _thumb_of(cp.photos),
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
        "cover": _thumb_of(t.photos),
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
        "cover": a.cover_thumb_url or a.cover_url,
        "district_label": DISTRICTS.get(a.district),
    }


def _related_articles(db: Session, current: Article, limit: int = 3) -> list:
    """«Читали также» — автоматический подбор без ручных связей: очки за
    совпадение округа и за общие места/маршруты, вынесенные в статью через
    featured_*. При малом числе статей (сейчас) выборка почти всегда полная,
    но правило не завязано на объём контента и останется рабочим, когда
    статей станет намного больше."""
    others = db.execute(
        select(Article).where(Article.is_published == True, Article.id != current.id)
    ).scalars().all()
    if not others:
        return []

    own_places = set(current.featured_checkpoint_ids or [])
    own_trails = set(current.featured_trail_ids or [])

    def score(a: Article) -> tuple:
        s = 0
        if current.district and a.district == current.district:
            s += 2
        s += len(own_places & set(a.featured_checkpoint_ids or []))
        s += len(own_trails & set(a.featured_trail_ids or []))
        return (s, a.created_at or a.id)

    ranked = sorted(others, key=score, reverse=True)
    return [_article_card_dict(a) for a in ranked[:limit]]


def _place_detail_dict(cp: Checkpoint) -> dict:
    return {
        "id": cp.id,
        "name": cp.name,
        "excerpt": _excerpt(cp.description, 200),
        "description_html": _render_consider_blocks(_rich_text_html(cp.description)),
        "cover": _cover_of(cp.photos),
        "photos": [p.url for p in cp.photos],
        "gallery": _gallery_of(cp.photos),
        "district_label": DISTRICTS.get(cp.district),
        "category": _category_lite(cp.category),
        "difficulty_label": DIFFICULTY_LABELS.get(cp.difficulty, cp.difficulty),
        "difficulty_info": _difficulty_info(cp.difficulty),
        "season_label": SEASON_LABELS.get(cp.seasonality, cp.seasonality),
        "access_label": ACCESS_LABELS.get(cp.access_type, cp.access_type),
        "price_label": _price_label(cp.is_paid, cp.price_note),
        "kid_friendly": cp.kid_friendly,
        "equipment_tags": cp.equipment_tags or [],
        "yandex_url": _yandex_point_url(cp),
        "weather_url": _weather_url(to_shape(cp.geom).y, to_shape(cp.geom).x),
        "trail": {"name": cp.trail.name, "url": f"/marshruty/{cp.trail.id}"} if cp.trail else None,
        "district_url": f"/okrugi/{cp.district}" if cp.district in DISTRICT_PAGES else None,
        "updated_label": _updated_label(cp.checked_at),
    }


def _route_detail_dict(t: Trail) -> dict:
    ordered_cps = sorted(t.checkpoints, key=lambda c: c.order_index)
    # Погода привязана к финальной точке маршрута — по ней ориентируются,
    # когда планируют выезд, а не по стартовой (та обычно у посёлка/парковки).
    weather_url = None
    if ordered_cps:
        shp = to_shape(ordered_cps[-1].geom)
        weather_url = _weather_url(shp.y, shp.x)
    return {
        "id": t.id,
        "name": t.name,
        "excerpt": _excerpt(t.description, 200),
        "description_html": _render_consider_blocks(_rich_text_html(t.description)),
        "cover": _cover_of(t.photos),
        "gallery": _gallery_of(t.photos),
        "district_label": DISTRICTS.get(t.district),
        "category": _category_lite(t.category),
        "difficulty_label": DIFFICULTY_LABELS.get(t.difficulty, t.difficulty),
        "difficulty_info": _difficulty_info(t.difficulty),
        "duration_label": _duration_label(t.duration_minutes),
        "season_label": SEASON_LABELS.get(t.seasonality, t.seasonality),
        "access_label": ACCESS_LABELS.get(t.access_type, t.access_type),
        "price_label": _price_label(t.is_paid, t.price_note),
        "kid_friendly": t.kid_friendly,
        "equipment_tags": t.equipment_tags or [],
        "yandex_url": _yandex_route_url(t),
        "weather_url": weather_url,
        "gpx_url": f"/marshruty/{t.id}/track.gpx" if t.segments else None,
        "district_url": f"/okrugi/{t.district}" if t.district in DISTRICT_PAGES else None,
        "updated_label": _updated_label(t.checked_at),
        "checkpoints": [
            {
                "name": cp.name,
                # Ссылка только у точек, выделенных в самостоятельные места —
                # у остальных страницы нет, ведут в 404.
                "url": f"/mesta/{cp.id}" if cp.show_as_place else None,
                "category_name": cp.category.name if cp.category else None,
            }
            for cp in ordered_cps
        ],
    }


# ─────────────────────────────────────────────
#  Общий контекст рендера
# ─────────────────────────────────────────────

_FOOTER_CACHE: dict = {"value": None, "at": 0.0}
_FOOTER_TTL_S = 120


def _footer_stats(db: Session) -> dict:
    """Счётчик в подвале рисуется на каждой странице, а меняется раз в
    несколько дней — держим его в памяти и считаем одним запросом вместо двух."""
    now = time.monotonic()
    if _FOOTER_CACHE["value"] is not None and now - _FOOTER_CACHE["at"] < _FOOTER_TTL_S:
        return _FOOTER_CACHE["value"]

    places_q = select(func.count()).select_from(Checkpoint) \
        .where(Checkpoint.show_as_place == True, Checkpoint.is_published == True).scalar_subquery()
    trails_q = select(func.count()).select_from(Trail).where(Trail.is_published == True).scalar_subquery()
    places, trails = db.execute(select(places_q, trails_q)).one()

    _FOOTER_CACHE["value"] = {"places": places or 0, "trails": trails or 0}
    _FOOTER_CACHE["at"] = now
    return _FOOTER_CACHE["value"]


def _ctx(request: Request, db: Session, **extra) -> dict:
    base = {
        "request": request,
        "footer_stats": _footer_stats(db),
        "districts": DISTRICTS,
        "site_url": SITE_URL,
        "canonical_url": SITE_URL + request.url.path,
        "yandex_metrika_id": YANDEX_METRIKA_ID,
        "club_url": CLUB_URL,
        "difficulty_levels": DIFFICULTY_INFO,
        "asset_version": ASSET_VERSION,
    }
    base.update(extra)
    return base


# ─────────────────────────────────────────────
#  Случайное место/маршрут — взвешенный рандом
# ─────────────────────────────────────────────

def _pick_highlight(db: Session) -> dict:
    """Для жеребьёвки достаточно id и популярности — тянуть все объекты
    целиком (с описаниями и фото) ради одной карточки незачем. Полностью
    читаем только выпавший."""
    place_rows = db.execute(
        select(Checkpoint.id, Checkpoint.popularity)
        .where(Checkpoint.show_as_place == True, Checkpoint.is_published == True)
    ).all()
    trail_rows = db.execute(select(Trail.id, Trail.popularity).where(Trail.is_published == True)).all()
    pool = [("place", r) for r in place_rows] + [("route", r) for r in trail_rows]

    if not pool:
        return {
            "name": "Пока пусто",
            "excerpt": "Добавьте места или маршруты в админке — здесь появится случайная подборка.",
            "cover": None,
            "tag_label": "Скоро",
            "url": "/",
        }

    weights = [POPULARITY_WEIGHT.get(row.popularity, 6) for _, row in pool]
    kind, row = random.choices(pool, weights=weights, k=1)[0]

    if kind == "place":
        cp = db.execute(
            _with_place_relations(select(Checkpoint)).where(Checkpoint.id == row.id)
        ).scalars().first()
        d = _place_card_dict(cp)
        d["tag_label"] = "Случайное место"
    else:
        t = db.execute(
            _with_route_relations(select(Trail)).where(Trail.id == row.id)
        ).scalars().first()
        d = _route_card_dict(t)
        d["tag_label"] = "Случайный маршрут"
    return d


@router.get("/api/site/random")
def api_random(db: Session = Depends(get_db)):
    return _pick_highlight(db)


@router.get("/api/site/favorites")
def api_favorites(items: str = "", db: Session = Depends(get_db)):
    """Избранное живёт только в localStorage браузера — сервер лишь
    досдаёт карточки по списку "place:24,route:8" для рендера на главной."""
    place_ids, route_ids = [], []
    for token in items.split(","):
        kind, _, raw_id = token.strip().partition(":")
        if not raw_id.isdigit():
            continue
        if kind == "place":
            place_ids.append(int(raw_id))
        elif kind == "route":
            route_ids.append(int(raw_id))

    places_by_id = {
        cp.id: cp
        for cp in db.execute(
            _with_place_relations(select(Checkpoint)).where(Checkpoint.id.in_(place_ids), Checkpoint.show_as_place == True)
        ).scalars().all()
    } if place_ids else {}
    routes_by_id = {
        t.id: t for t in db.execute(_with_route_relations(select(Trail)).where(Trail.id.in_(route_ids))).scalars().all()
    } if route_ids else {}

    result = []
    for pid in place_ids:
        if pid in places_by_id:
            card = _place_card_dict(places_by_id[pid])
            card["kind"] = "place"
            result.append(card)
    for tid in route_ids:
        if tid in routes_by_id:
            card = _route_card_dict(routes_by_id[tid])
            card["kind"] = "route"
            result.append(card)
    return result


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
    place_rows = db.execute(
        _with_place_relations(select(Checkpoint)).order_by(_POPULARITY_ORDER, Checkpoint.created_at.desc()).limit(6)
    ).scalars().all()
    places = [_place_card_dict(cp) for cp in place_rows]
    place_likes = _like_counts_map(db, "checkpoint", [cp.id for cp in place_rows])
    for p in places:
        if place_likes.get(p["id"]):
            p["likes_label"] = _likes_label(place_likes[p["id"]])

    route_rows = db.execute(
        _with_route_relations(select(Trail)).order_by(_POPULARITY_ORDER_TRAIL, Trail.created_at.desc()).limit(6)
    ).scalars().all()
    routes = [_route_card_dict(t) for t in route_rows]
    route_likes = _like_counts_map(db, "trail", [t.id for t in route_rows])
    for r in routes:
        if route_likes.get(r["id"]):
            r["likes_label"] = _likes_label(route_likes[r["id"]])

    doors = _scenario_doors(db)
    wizard_categories = db.execute(
        select(Category).where(Category.is_public == True, Category.type.in_(["checkpoint", "both"]))
    ).scalars().all()
    return templates.TemplateResponse(
        "home.html",
        _ctx(
            request, db, active_nav="home", highlight=highlight, articles=articles, places=places, routes=routes,
            wizard_categories=wizard_categories, doors=doors, page=_site_page(db, "home"),
        ),
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
    q = _with_place_relations(select(Checkpoint)).where(Checkpoint.show_as_place == True)
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
    # Забираем место сразу с фото, категорией и маршрутом (вместе с его фото и
    # категорией) — иначе каждое из этих полей уходит отдельным запросом.
    cp = db.execute(
        _with_place_relations(select(Checkpoint))
        .options(
            joinedload(Checkpoint.trail).selectinload(Trail.photos),
            joinedload(Checkpoint.trail).joinedload(Trail.category),
        )
        .where(Checkpoint.id == place_id)
    ).scalars().first()
    # Промежуточная точка маршрута — не самостоятельное место, своей страницы
    # у неё нет (иначе в индекс попадут пустышки вроде «развилка у ручья»).
    if not cp or not cp.show_as_place:
        raise HTTPException(404, "Место не найдено")

    place = _place_detail_dict(cp)
    conditions = [c for c in [
        Checkpoint.district == cp.district if cp.district else None,
        Checkpoint.category_id == cp.category_id if cp.category_id else None,
    ] if c is not None]
    similar = []
    if conditions:
        rows = db.execute(
            _with_place_relations(select(Checkpoint)).where(
                Checkpoint.id != cp.id, Checkpoint.show_as_place == True, or_(*conditions)
            ).limit(4)
        ).scalars().all()
        similar = [_place_card_dict(r) for r in rows]

    shp = to_shape(cp.geom)
    nearby = [p for p in _nearby_places(db, shp.y, shp.x, exclude_id=cp.id, limit=5) if p["id"] != cp.id][:4]
    related_routes = _routes_for_place(db, cp)

    return templates.TemplateResponse(
        "place_detail.html",
        _ctx(
            request, db, active_nav="places", place=place, similar=similar, nearby=nearby,
            related_routes=related_routes,
            like=_like_info(db, request, "checkpoint", cp.id),
        ),
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
    q = _with_route_relations(select(Trail))
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
    # Точки по пути показываются с категориями — тянем их одной пачкой.
    t = db.execute(
        _with_route_relations(select(Trail))
        .options(
            selectinload(Trail.checkpoints).joinedload(Checkpoint.category),
            selectinload(Trail.segments),
        )
        .where(Trail.id == route_id)
    ).scalars().first()
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
            _with_route_relations(select(Trail)).where(Trail.id != t.id, or_(*conditions)).limit(4)
        ).scalars().all()
        similar = [_route_card_dict(r) for r in rows]

    # «Рядом» считаем от стартовой точки маршрута — по ней ориентируются,
    # что ещё посмотреть, добравшись до начала тропы.
    nearby = []
    ordered_cps = sorted(t.checkpoints, key=lambda c: c.order_index)
    if ordered_cps:
        shp = to_shape(ordered_cps[0].geom)
        own_ids = {c.id for c in ordered_cps}
        nearby = [p for p in _nearby_places(db, shp.y, shp.x, limit=4 + len(own_ids)) if p["id"] not in own_ids][:4]

    return templates.TemplateResponse(
        "route_detail.html",
        _ctx(
            request, db, active_nav="routes", route=route, similar=similar, nearby=nearby,
            like=_like_info(db, request, "trail", t.id),
        ),
    )


@router.get("/marshruty/{route_id}/track.gpx")
def route_gpx(route_id: int, db: Session = Depends(get_db)):
    """Трек маршрута в GPX — чтобы залить в навигатор и идти по нему там,
    где нет связи. Ссылки на сайте пока нет: включим, когда тропы будут
    отрисованы, а сейчас файл уже отдаётся по прямому адресу."""
    t = db.get(Trail, route_id)
    if not t:
        raise HTTPException(404, "Маршрут не найден")

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="АдыГид" xmlns="http://www.topografix.com/GPX/1/1">',
        f"<metadata><name>{escape(t.name)}</name><link href=\"{escape(SITE_URL)}/marshruty/{t.id}\"/></metadata>",
    ]

    for cp in sorted(t.checkpoints, key=lambda c: c.order_index):
        shp = to_shape(cp.geom)
        parts.append(
            f'<wpt lat="{shp.y:.6f}" lon="{shp.x:.6f}"><name>{escape(cp.name)}</name></wpt>'
        )

    if t.segments:
        parts.append(f"<trk><name>{escape(t.name)}</name>")
        for seg in sorted(t.segments, key=lambda s: s.order_index):
            parts.append("<trkseg>")
            for lon, lat in to_shape(seg.geom).coords:
                parts.append(f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"></trkpt>')
            parts.append("</trkseg>")
        parts.append("</trk>")

    parts.append("</gpx>")
    filename = f"adygid-route-{t.id}.gpx"
    return Response(
        "\n".join(parts),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────
#  Сценарии — вход по ситуации человека
# ─────────────────────────────────────────────

def _scenario_conditions(model, sc: Scenario) -> list:
    """Переводит правило отбора сценария (поля filter_* в БД, редактируются
    в админке) в условия запроса. Поля у Checkpoint и Trail называются
    одинаково, поэтому одна функция работает и для мест, и для маршрутов.
    Пустой список/None в filter_* — «без ограничения», условие не добавляется."""
    conditions = []
    if sc.filter_kid_friendly is not None:
        conditions.append(model.kid_friendly == sc.filter_kid_friendly)
    if sc.filter_popularity:
        conditions.append(model.popularity.in_(sc.filter_popularity))
    if sc.filter_difficulty:
        conditions.append(model.difficulty.in_(sc.filter_difficulty))
    if sc.filter_seasonality:
        conditions.append(model.seasonality == sc.filter_seasonality)
    if sc.filter_access:
        conditions.append(model.access_type.in_(sc.filter_access))
    return conditions


def _door_dict(sc: Scenario) -> dict:
    return {
        "slug": sc.slug, "url": f"/kuda/{sc.slug}", "door": sc.door, "hint": sc.hint or "",
        "icon": sc.icon or "", "cover": sc.tile_cover_thumb_url or sc.tile_cover_url or "",
    }


def _scenario_doors(db: Session, current: Optional[str] = None) -> list:
    """Двери развилки — один и тот же список на главной и внизу сценария."""
    rows = db.execute(
        select(Scenario).where(Scenario.is_published == True).order_by(Scenario.order_index, Scenario.id)
    ).scalars().all()
    return [_door_dict(sc) for sc in rows if sc.slug != current]


@router.get("/kuda")
def scenarios_index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "scenarios_list.html",
        _ctx(request, db, active_nav="scenarios", doors=_scenario_doors(db)),
    )


@router.get("/kuda/{slug}")
def scenario_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    sc = db.execute(select(Scenario).where(Scenario.slug == slug, Scenario.is_published == True)).scalars().first()
    if not sc:
        raise HTTPException(404, "Сценарий не найден")

    place_conditions = [Checkpoint.show_as_place == True] + _scenario_conditions(Checkpoint, sc)
    places = [
        _place_card_dict(cp)
        for cp in db.execute(
            _with_place_relations(select(Checkpoint))
            .where(*place_conditions)
            .order_by(_POPULARITY_ORDER, Checkpoint.created_at.desc())
        ).scalars().all()
    ]

    route_conditions = _scenario_conditions(Trail, sc)
    routes = [
        _route_card_dict(t)
        for t in db.execute(
            _with_route_relations(select(Trail))
            .where(*route_conditions)
            .order_by(_POPULARITY_ORDER_TRAIL)
        ).scalars().all()
    ]

    article_ids = sc.featured_article_ids or []
    articles = []
    if article_ids:
        by_id = {
            a.id: a
            for a in db.execute(
                select(Article).where(Article.id.in_(article_ids), Article.is_published == True)
            ).scalars().all()
        }
        articles = [_article_card_dict(by_id[i]) for i in article_ids if i in by_id]

    lead_html = _render_article_gallery(_rich_text_html(sc.lead))
    lead_html, toc = _add_toc_anchors(lead_html)
    lead_html, _embedded_faq = _render_embeds(db, lead_html)

    scenario = {
        "id": sc.id,
        "slug": sc.slug,
        "title": sc.title,
        "door": sc.door,
        "cover_url": sc.cover_url,
        "lead": lead_html,
        "toc": toc if len(toc) >= 3 else [],
        "seo_description": sc.seo_description or _excerpt(sc.lead, 200) or sc.title,
        "places": places,
        "routes": routes,
        "articles": articles,
    }
    return templates.TemplateResponse(
        "scenario.html",
        _ctx(
            request, db, active_nav="scenarios", scenario=scenario, doors=_scenario_doors(db, slug),
            like=_like_info(db, request, "scenario", sc.id),
        ),
    )


# ─────────────────────────────────────────────
#  Округа — навигация по географии, а не только фильтр
# ─────────────────────────────────────────────

@router.get("/okrugi")
def districts_index(request: Request, db: Session = Depends(get_db)):
    # Считаем всё двумя групповыми запросами, а не парой на каждый округ.
    place_counts = dict(db.execute(
        select(Checkpoint.district, func.count())
        .where(Checkpoint.show_as_place == True)
        .group_by(Checkpoint.district)
    ).all())
    route_counts = dict(db.execute(
        select(Trail.district, func.count()).group_by(Trail.district)
    ).all())

    items = []
    for slug, label in DISTRICTS.items():
        if slug not in DISTRICT_PAGES:
            continue
        places = place_counts.get(slug, 0)
        routes = route_counts.get(slug, 0)
        items.append({
            "slug": slug,
            "label": label,
            "url": f"/okrugi/{slug}",
            "lead": DISTRICT_PAGES[slug]["lead"],
            "places": places,
            "routes": routes,
        })
    return templates.TemplateResponse(
        "districts_list.html", _ctx(request, db, active_nav="districts", districts_list=items)
    )


@router.get("/okrugi/{slug}")
def district_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    page = DISTRICT_PAGES.get(slug)
    if not page:
        raise HTTPException(404, "Округ не найден")

    places = [
        _place_card_dict(cp)
        for cp in db.execute(
            _with_place_relations(select(Checkpoint))
            .where(Checkpoint.district == slug, Checkpoint.show_as_place == True)
            .order_by(_POPULARITY_ORDER, Checkpoint.created_at.desc())
        ).scalars().all()
    ]
    routes = [
        _route_card_dict(t)
        for t in db.execute(
            _with_route_relations(select(Trail)).where(Trail.district == slug).order_by(_POPULARITY_ORDER_TRAIL)
        ).scalars().all()
    ]
    articles = [
        _article_card_dict(a)
        for a in db.execute(
            select(Article).where(Article.is_published == True, Article.district == slug)
        ).scalars().all()
    ]

    district = {
        "slug": slug,
        "label": DISTRICTS.get(slug, slug),
        "lead": page["lead"],
        "facts": page.get("facts", []),
        "places": places,
        "routes": routes,
        "articles": articles,
    }
    return templates.TemplateResponse(
        "district.html", _ctx(request, db, active_nav="districts", district=district)
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

    # Забираем все привязанные места и маршруты пачкой, сохраняя порядок,
    # выбранный в админке (раньше это был отдельный запрос на каждую карточку).
    place_ids = a.featured_checkpoint_ids or []
    featured_places = []
    if place_ids:
        by_id = {
            cp.id: cp
            for cp in db.execute(
                _with_place_relations(select(Checkpoint))
                .where(Checkpoint.id.in_(place_ids), Checkpoint.show_as_place == True)
            ).scalars().all()
        }
        featured_places = [_place_card_dict(by_id[i]) for i in place_ids if i in by_id]

    trail_ids = a.featured_trail_ids or []
    featured_routes = []
    if trail_ids:
        by_id = {
            t.id: t
            for t in db.execute(
                _with_route_relations(select(Trail)).where(Trail.id.in_(trail_ids))
            ).scalars().all()
        }
        featured_routes = [_route_card_dict(by_id[i]) for i in trail_ids if i in by_id]

    body_html = _render_article_gallery(_rich_text_html(a.body))
    body_html, toc = _add_toc_anchors(body_html)
    # Вставленные в текст блоки подставляем последними: их разметка не должна
    # попасть ни в галереи, ни в оглавление.
    body_html, embedded_faq = _render_embeds(db, body_html)

    # В сниппет поиска отдаём и «хвостовой» FAQ статьи, и все вопросы из
    # вставленных в текст наборов — для поисковика это одна страница.
    faq = a.faq or []
    all_faq = list(faq) + embedded_faq
    faq_ld = None
    if all_faq:
        # Jinja не умеет list comprehension в выражениях — список вопросов
        # для JSON-LD собираем здесь, а не в шаблоне.
        faq_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": item["question"],
                    "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                }
                for item in all_faq
            ],
        }

    article = {
        "title": a.title,
        "excerpt": a.excerpt or _excerpt(a.body, 200),
        "district_label": DISTRICTS.get(a.district),
        "cover_url": a.cover_url,
        "body_html": body_html,
        "toc": toc if len(toc) >= 3 else [],
        "faq": faq,
        "faq_ld": faq_ld,
        "featured_places": featured_places,
        "featured_routes": featured_routes,
    }

    similar_places = []
    if a.district:
        exclude_ids = set(a.featured_checkpoint_ids or [])
        rows = db.execute(
            _with_place_relations(select(Checkpoint)).where(
                Checkpoint.district == a.district,
                Checkpoint.show_as_place == True,
                Checkpoint.id.notin_(exclude_ids),
            ).limit(4)
        ).scalars().all()
        similar_places = [_place_card_dict(r) for r in rows]

    related_articles = _related_articles(db, a)

    return templates.TemplateResponse(
        "article_detail.html",
        _ctx(
            request, db, active_nav="articles", article=article,
            similar_places=similar_places, related_articles=related_articles,
        ),
    )


# ─────────────────────────────────────────────
#  Общая страница вопросов
# ─────────────────────────────────────────────

@router.get("/voprosy")
def faq_page(request: Request, db: Session = Depends(get_db)):
    sets = db.execute(
        select(FaqSet)
        .where(FaqSet.is_published == True, FaqSet.on_faq_page == True)
        .order_by(FaqSet.order_index, FaqSet.id)
    ).scalars().all()

    blocks = [{"title": f.title or f.name, "html": _faq_html(f)} for f in sets if f.items]
    all_items = [i for f in sets for i in (f.items or [])]
    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": i["question"],
             "acceptedAnswer": {"@type": "Answer", "text": i["answer"]}}
            for i in all_items
        ],
    } if all_items else None

    return templates.TemplateResponse(
        "faq.html", _ctx(request, db, active_nav="faq", blocks=blocks, faq_ld=faq_ld)
    )


# ─────────────────────────────────────────────
#  Клуб (заглушка)
# ─────────────────────────────────────────────

@router.get("/klub")
def club(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("club.html", _ctx(request, db, active_nav="club", page=_site_page(db, "club")))


# ─────────────────────────────────────────────
#  robots.txt / sitemap.xml — чтобы поисковики знали, что обходить
# ─────────────────────────────────────────────

@router.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    return (
        "User-agent: *\n"
        "Allow: /\n"
        # Служебное — в индексе не нужно
        "Disallow: /admin\n"
        "Disallow: /api/\n"
        "Disallow: /m\n"
        # Страницы с фильтрами дублируют списки — пусть в индекс идут списки
        "Clean-param: type&district&paid&kid&difficulty\n"
        f"\nSitemap: {SITE_URL}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
def sitemap_xml(db: Session = Depends(get_db)):
    urls: list[tuple[str, Optional[str], str]] = [
        ("/", None, "daily"),
        ("/mesta", None, "weekly"),
        ("/marshruty", None, "weekly"),
        ("/stati", None, "weekly"),
        ("/kuda", None, "monthly"),
        ("/okrugi", None, "monthly"),
        ("/voprosy", None, "monthly"),
        ("/klub", None, "monthly"),
    ]
    for row in db.execute(select(Scenario.slug).where(Scenario.is_published == True)).scalars().all():
        urls.append((f"/kuda/{row}", None, "weekly"))
    for slug in DISTRICT_PAGES:
        urls.append((f"/okrugi/{slug}", None, "monthly"))

    for cp in db.execute(
        select(Checkpoint.id, Checkpoint.created_at)
        .where(Checkpoint.show_as_place == True, Checkpoint.is_published == True)
    ).all():
        urls.append((f"/mesta/{cp.id}", cp.created_at.date().isoformat() if cp.created_at else None, "monthly"))
    for t in db.execute(select(Trail.id, Trail.created_at).where(Trail.is_published == True)).all():
        urls.append((f"/marshruty/{t.id}", t.created_at.date().isoformat() if t.created_at else None, "monthly"))
    for a in db.execute(
        select(Article.slug, Article.created_at).where(Article.is_published == True)
    ).all():
        urls.append((f"/stati/{a.slug}", a.created_at.date().isoformat() if a.created_at else None, "monthly"))

    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod, changefreq in urls:
        body.append("<url>")
        body.append(f"<loc>{escape(SITE_URL + path)}</loc>")
        if lastmod:
            body.append(f"<lastmod>{lastmod}</lastmod>")
        body.append(f"<changefreq>{changefreq}</changefreq>")
        body.append("</url>")
    body.append("</urlset>")
    return Response("\n".join(body), media_type="application/xml")
