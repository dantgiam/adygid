"""Досуг: каталог /dosug, заявка организатора и кабинет для новых активностей.

Заявка сразу попадает в модерацию (status=pending, is_published=false).
Публичная страница и sitemap видят только одобренное, и только по слагу:
/dosug/<id> отвечает 301 на слаг. Условия и состояние снаряжения — отдельные
поля. Сбор гостя 5% считается здесь и не меняет сбор жилья.

Контакты организатора пишем в базу, потому что бота и каналы MAX/Telegram
эта форма не вызывает. На сайт телефон и имя не выводятся.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import engine, get_db
from app.models import LeisureItem, LeisureOffer, LeisurePhoto, LeisureProvider, SlugRedirect
from site_app.content import DISTRICTS
from site_app import leisure_catalog as cat
from site_app import leisure_photos as photos
from site_app import seo
from site_app.router import SITE_URL, _ctx, templates

log = logging.getLogger("adygid.leisure")
router = APIRouter()

MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261119_leisure_offers.sql")
_PHONE_RE = re.compile(r"^[+\d][\d\s()\-]{8,20}$")
_URL_RE = re.compile(r"^https?://\S{4,500}$", re.I)
_CODE_RE = re.compile(r"^[a-f0-9]{16}$")


class FormError(Exception):
    def __init__(self, message: str, field: str = ""):
        self.message = message
        self.field = field


CSRF_COOKIE = "lz_csrf"
# Простой предел на публичную заявку: один процесс, один IP.
RATE_WINDOW_S = 600
RATE_MAX = 12
_HITS: dict[str, list[float]] = {}


def _csrf_pair(request: Request) -> tuple[str, str | None]:
    current = request.cookies.get(CSRF_COOKIE, "")
    if len(current) >= 20:
        return current, None
    fresh = secrets.token_urlsafe(32)
    return fresh, fresh


def _set_csrf_cookie(response, fresh: str | None) -> None:
    if fresh:
        response.set_cookie(CSRF_COOKIE, fresh, httponly=True, samesite="lax", path="/")


def assert_post_guard(request: Request, form) -> None:
    """CSRF-токен и свой Origin или Referer. Без заголовка запрос не принимаем."""
    host = (request.headers.get("host") or "").lower()
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if not origin and not referer:
        raise HTTPException(403, "Нужен заголовок Origin или Referer")
    for value in (origin, referer):
        if value and urlparse(value).netloc.lower() != host:
            raise HTTPException(403, "Форму можно отправить только с этого сайта")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    posted = form.get("csrf")
    posted = posted if isinstance(posted, str) else ""
    if len(cookie) < 20 or not secrets.compare_digest(posted, cookie):
        raise HTTPException(403, "Обновите страницу и отправьте форму ещё раз")


def assert_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = [stamp for stamp in _HITS.get(ip, []) if now - stamp < RATE_WINDOW_S]
    if len(hits) >= RATE_MAX:
        raise HTTPException(429, "Слишком много заявок с этого адреса. Попробуйте позже")
    hits.append(now)
    _HITS[ip] = hits


def ensure_leisure_tables() -> None:
    try:
        raw = open(MIGRATION, encoding="utf-8").read()
    except OSError:
        log.warning("leisure migration missing")
        return
    stmts = []
    for chunk in raw.split(";"):
        lines = [ln for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        if lines:
            stmts.append("\n".join(lines))
    try:
        with engine.begin() as conn:
            for stmt in stmts:
                conn.execute(text(stmt))
    except Exception:
        log.exception("leisure migration failed")


def is_public(offer: LeisureOffer | None) -> bool:
    return bool(offer and offer.is_published and offer.status == "approved" and offer.slug)


def _new_code(db: Session) -> str:
    for _ in range(8):
        code = secrets.token_hex(8)
        if not db.execute(select(LeisureProvider.id).where(LeisureProvider.code == code)).first():
            return code
    raise HTTPException(500, "Не удалось выдать номер кабинета")


def _text(form, name: str, limit: int) -> str:
    value = form.get(name)
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


_TEXT_KEYS = (
    "display_name", "legal_status", "legal_details", "licenses_note", "insurance_note",
    "instructor_note", "website", "socials", "contact_name", "contact_phone", "contact_messenger",
    "title", "activity_type", "description", "meeting_address", "finish_address", "lat", "lon", "district",
    "duration_text", "schedule_text", "weather_terms", "price_amount", "price_unit", "price_text", "included",
    "excluded", "group_min", "group_max", "age_text", "weight_limit", "health_limits", "difficulty",
    "what_to_bring", "provided_gear", "transfer", "transfer_note", "language_note", "conditions",
    "cancellation_terms", "equipment_state", "vest", "helmet", "gear_check", "briefing", "briefing_note",
    "has_instructor", "item_title", "item_quantity", "item_state", "item_price_text",
    "item_price_amount", "item_note", "code", "mode", "offer_id",
)


def _posted(form) -> dict:
    """Сырые значения формы — чтобы при ошибке вернуть их в поля."""
    data = {key: _text(form, key, 5000) for key in _TEXT_KEYS}
    for activity, fields in cat.CATEGORY_FIELDS.items():
        for field in fields:
            name = f"extra_{activity}_{field['key']}"
            data[name] = _text(form, name, 2000)
    data["seasons"] = [s for s in form.getlist("seasons") if s in cat.SEASON_BY_CODE]
    data["languages"] = [s for s in form.getlist("languages") if s in cat.LANGUAGE_BY_CODE]
    data["consent"] = form.get("consent") == "1"
    data["consent_own_service"] = form.get("consent_own_service") == "1"
    data["consent_docs"] = form.get("consent_docs") == "1"
    data["photos_honest"] = form.get("photos_honest") == "1"
    data["photos_vests"] = form.get("photos_vests") == "1"
    return data


def _need(value: str, label: str, min_len: int = 2, field: str = "") -> str:
    if len(value.strip()) < min_len:
        raise FormError(f"Заполните поле «{label}»", field)
    return value.strip()


def _money(value: str, label: str) -> Decimal | None:
    if not value:
        return None
    try:
        amount = Decimal(value.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise FormError(f"«{label}» должно быть числом")
    if amount < 0 or amount > Decimal("10000000"):
        raise FormError(f"«{label}» вне диапазона")
    return amount.quantize(Decimal("0.01"))


def _whole(value: str, label: str, lo: int, hi: int) -> int | None:
    if not value:
        return None
    if not re.fullmatch(r"\d{1,6}", value):
        raise FormError(f"«{label}» — целое число")
    number = int(value)
    if number < lo or number > hi:
        raise FormError(f"«{label}» вне диапазона")
    return number


def _coord(value: str, label: str, lo: Decimal, hi: Decimal) -> Decimal | None:
    if not value:
        return None
    try:
        number = Decimal(value.replace(",", "."))
    except InvalidOperation:
        raise FormError(f"Проверьте {label}")
    if number < lo or number > hi:
        raise FormError(f"Проверьте {label}")
    return number.quantize(Decimal("0.000001"))


def validate_provider(data: dict) -> dict:
    out = {
        "display_name": _need(data.get("display_name", ""), "Название организатора", 2, "display_name")[:200],
        "legal_status": data.get("legal_status") or "",
        "legal_details": (data.get("legal_details") or "")[:300] or None,
        "licenses_note": _need(data.get("licenses_note", ""), "Лицензии и допуски", 2, "licenses_note"),
        "insurance_note": _need(data.get("insurance_note", ""), "Страховка", 2, "insurance_note"),
        "has_instructor": data.get("has_instructor") == "1",
        "instructor_note": (data.get("instructor_note") or "")[:2000] or None,
        "website": (data.get("website") or "")[:500] or None,
        "socials": (data.get("socials") or "")[:500] or None,
        "contact_name": _need(data.get("contact_name", ""), "Имя контакта", 2, "contact_name")[:120],
        "contact_phone": (data.get("contact_phone") or "")[:40] or None,
        "contact_messenger": (data.get("contact_messenger") or "")[:160] or None,
    }
    if out["legal_status"] not in cat.LEGAL_BY_CODE:
        raise FormError("Выберите юридический статус", "legal_status")
    if data.get("has_instructor") not in ("0", "1"):
        raise FormError("Укажите, есть ли инструктор")
    if out["website"] and not _URL_RE.match(out["website"]):
        raise FormError("Сайт должен начинаться с https://")
    if not out["contact_phone"] and not out["contact_messenger"]:
        raise FormError("Оставьте телефон или мессенджер", "contact_phone")
    if out["contact_phone"] and not _PHONE_RE.match(out["contact_phone"]):
        raise FormError("Проверьте номер телефона")
    return out


def validate_offer(data: dict) -> dict:
    activity = data.get("activity_type") or ""
    if activity not in cat.ACTIVITY_BY_CODE:
        raise FormError("Выберите тип активности", "activity_type")
    seasons = [s for s in data.get("seasons") or [] if s in cat.SEASON_BY_CODE]
    languages = [s for s in data.get("languages") or [] if s in cat.LANGUAGE_BY_CODE]
    if not seasons:
        raise FormError("Отметьте сезон")
    if not languages:
        raise FormError("Отметьте язык")
    district = data.get("district") or ""
    if district and district not in DISTRICTS:
        raise FormError("Выберите район из списка")
    if data.get("difficulty") not in cat.DIFFICULTY_BY_CODE:
        raise FormError("Выберите уровень сложности")
    if data.get("transfer") not in cat.TRANSFER_BY_CODE:
        raise FormError("Укажите, есть ли трансфер")
    price_unit = data.get("price_unit") or "person"
    if price_unit not in cat.PRICE_UNIT_BY_CODE:
        raise FormError("Выберите, за что указана цена")
    group_min = _whole(data.get("group_min") or "", "Группа, минимум", 1, 500)
    group_max = _whole(data.get("group_max") or "", "Группа, максимум", 1, 500)
    if not group_min or not group_max:
        raise FormError("Укажите минимум и максимум группы", "group_min")
    if group_min > group_max:
        raise FormError("Минимум группы больше максимума")
    lat = _coord(data.get("lat") or "", "широту", Decimal("-90"), Decimal("90"))
    lon = _coord(data.get("lon") or "", "долготу", Decimal("-180"), Decimal("180"))
    if (lat is None) != (lon is None):
        raise FormError("Широту и долготу укажите вместе")
    vest = data.get("vest") or ""
    helmet = data.get("helmet") or ""
    briefing = data.get("briefing") or ""
    if vest not in dict(cat.GEAR_ANSWER):
        raise FormError("Укажите, выдаёте ли жилет")
    if helmet not in dict(cat.GEAR_ANSWER):
        raise FormError("Укажите, выдаёте ли шлем")
    if briefing not in dict(cat.BRIEFING_ANSWER):
        raise FormError("Укажите, проводите ли инструктаж")
    if activity in cat.WATER_TYPES and vest != "yes":
        raise FormError("Для сплава жилет обязателен", "vest")
    if activity in cat.WATER_TYPES and briefing != "yes":
        raise FormError("Для сплава нужен инструктаж", "briefing")
    state = (data.get("equipment_state") or "").strip()
    if cat.needs_state(activity):
        state = _need(state, "Состояние снаряжения или техники", 2, "equipment_state")
    if not data.get("consent_own_service"):
        raise FormError("Нужно подтверждение, что услугу и оплату принимаете вы", "consent_own_service")
    if not data.get("consent_docs"):
        raise FormError("Нужно подтверждение, что документы и страховку можете показать по запросу")
    extra = _category_extra(activity, data)
    out = {
        "title": _need(data.get("title", ""), "Название", 3, "title")[:200],
        "activity_type": activity,
        "description": _need(data.get("description", ""), "Описание", 20, "description")[:5000],
        "meeting_address": _need(data.get("meeting_address", ""), "Точка сбора", 3, "meeting_address")[:300],
        "finish_address": _need(data.get("finish_address", ""), "Точка финиша", 3, "finish_address")[:300],
        "lat": lat,
        "lon": lon,
        "district": district or None,
        "duration_text": _need(data.get("duration_text", ""), "Длительность", 1, "duration_text")[:200],
        "seasons": ",".join(seasons),
        "schedule_text": _need(data.get("schedule_text", ""), "Расписание", 2, "schedule_text")[:3000],
        "weather_terms": _need(data.get("weather_terms", ""), "Сезон и погода", 2, "weather_terms")[:3000],
        "price_amount": _money(data.get("price_amount") or "", "Цена числом"),
        "price_unit": price_unit,
        "price_text": _need(data.get("price_text", ""), "Цена", 2, "price_text")[:2000],
        "included": _need(data.get("included", ""), "Что включено", 2, "included")[:3000],
        "excluded": _need(data.get("excluded", ""), "Что не включено", 2, "excluded")[:3000],
        "group_min": group_min,
        "group_max": group_max,
        "age_text": _need(data.get("age_text", ""), "Возраст", 1, "age_text")[:200],
        "weight_limit": _need(data.get("weight_limit", ""), "Ограничение по весу", 2, "weight_limit")[:500],
        "health_limits": _need(data.get("health_limits", ""), "Ограничения по здоровью", 2, "health_limits")[:3000],
        "difficulty": data["difficulty"],
        "what_to_bring": _need(data.get("what_to_bring", ""), "Что взять с собой", 2, "what_to_bring")[:3000],
        "provided_gear": _need(data.get("provided_gear", ""), "Что выдают", 2, "provided_gear")[:3000],
        "transfer": data["transfer"],
        "transfer_note": (data.get("transfer_note") or "").strip()[:2000] or None,
        "languages": ",".join(languages),
        "language_note": (data.get("language_note") or "").strip()[:200] or None,
        "conditions": _need(data.get("conditions", ""), "Условия", 10, "conditions")[:5000],
        "cancellation_terms": _need(data.get("cancellation_terms", ""), "Условия отмены", 2, "cancellation_terms")[:3000],
        "equipment_state": state[:5000] or None,
        "vest": vest,
        "helmet": helmet,
        "gear_check": _need(data.get("gear_check", ""), "Кто и когда проверяет снаряжение", 2, "gear_check")[:2000],
        "briefing": briefing,
        "briefing_note": (data.get("briefing_note") or "").strip()[:2000] or None,
        "category_extra": extra,
        "consent_own_service": True,
        "consent_docs": True,
        "photos_honest": bool(data.get("photos_honest")),
        "photos_vests": bool(data.get("photos_vests")),
    }
    return out


def _category_extra(activity: str, data: dict) -> dict:
    out: dict[str, str] = {}
    for field in cat.category_fields(activity):
        raw = (data.get(f"extra_{activity}_{field['key']}") or "").strip()
        choices = dict(field.get("choices") or [])
        if choices and raw not in choices:
            raw = ""
        needed = field["required"] or (
            field.get("required_if") and out.get(field["required_if"][0]) == field["required_if"][1]
        )
        if needed and len(raw) < 2:
            raise FormError(f"Заполните «{field['label']}»", f"extra_{activity}_{field['key']}")
        if raw:
            out[field["key"]] = raw[:2000]
    return out


def validate_item(data: dict) -> dict:
    return {
        "title": _need(data.get("item_title", ""), "Название поставки", 2)[:200],
        "quantity": _whole(data.get("item_quantity") or "", "Количество", 1, 9999),
        "state_text": _need(data.get("item_state", ""), "Состояние новой поставки", 2)[:5000],
        "price_text": (data.get("item_price_text") or "").strip()[:300] or None,
        "price_amount": _money(data.get("item_price_amount") or "", "Цена поставки"),
        "note": (data.get("item_note") or "").strip()[:3000] or None,
    }


def _apply_provider(row: LeisureProvider, cleaned: dict) -> None:
    for key, value in cleaned.items():
        setattr(row, key, value)


def _apply_offer(row: LeisureOffer, cleaned: dict) -> None:
    for key, value in cleaned.items():
        setattr(row, key, value)


async def _take_photos(form) -> list[dict]:
    chosen = []
    for index in range(1, photos.MAX_FILES + 1):
        item = form.get(f"photo_{index}")
        if not getattr(item, "filename", None):
            continue
        alt = _text(form, f"alt_{index}", 300)
        if len(alt) < 3:
            raise FormError(f"У фото {index} нужна подпись: что на снимке", f"alt_{index}")
        chosen.append((item, alt))
    if len(chosen) > photos.MAX_FILES:
        raise FormError(f"Можно приложить не больше {photos.MAX_FILES} фото")
    saved: list[dict] = []
    try:
        for item, alt in chosen:
            stored = await photos.save_upload(item)
            stored["alt"] = alt
            saved.append(stored)
    except photos.PhotoError as exc:
        for row in saved:
            photos.forget(row.get("url"))
            photos.forget(row.get("thumb_url"))
        raise FormError(exc.message, "photo_1") from exc
    return saved


def _drop_photos(saved: list[dict]) -> None:
    for row in saved:
        photos.forget(row.get("url"))
        photos.forget(row.get("thumb_url"))


def _attach(db: Session, saved: list[dict], offer_id: int, item_id: int | None) -> None:
    for index, row in enumerate(saved):
        db.add(LeisurePhoto(
            offer_id=offer_id, item_id=item_id, url=row["url"], thumb_url=row["thumb_url"],
            alt=row.get("alt") or "", sort_order=index,
        ))


def _provider_by_code(db: Session, code: str) -> LeisureProvider | None:
    if not _CODE_RE.match(code or ""):
        return None
    return db.execute(select(LeisureProvider).where(LeisureProvider.code == code)).scalars().first()


def _blank() -> dict:
    return {
        "display_name": "", "legal_status": "", "legal_details": "", "licenses_note": "",
        "insurance_note": "", "has_instructor": "", "instructor_note": "", "website": "", "socials": "",
        "contact_name": "", "contact_phone": "", "contact_messenger": "",
        "title": "", "activity_type": "", "description": "", "meeting_address": "", "finish_address": "",
        "lat": "", "lon": "", "district": "", "duration_text": "", "schedule_text": "", "weather_terms": "",
        "price_amount": "", "price_unit": "person", "price_text": "", "included": "", "excluded": "",
        "group_min": "", "group_max": "", "age_text": "", "weight_limit": "", "health_limits": "",
        "difficulty": "medium", "what_to_bring": "", "provided_gear": "", "transfer": "none",
        "transfer_note": "", "language_note": "", "conditions": "", "cancellation_terms": "",
        "equipment_state": "", "vest": "", "helmet": "", "gear_check": "", "briefing": "", "briefing_note": "",
        "seasons": [], "languages": ["ru"], "consent": False, "consent_own_service": False,
        "consent_docs": False, "photos_honest": False, "photos_vests": False,
        "item_title": "", "item_quantity": "", "item_state": "", "item_price_text": "",
        "item_price_amount": "", "item_note": "", "code": "", "mode": "", "offer_id": "",
    }


def _from_provider(row: LeisureProvider) -> dict:
    data = _blank()
    data.update({
        "display_name": row.display_name or "",
        "legal_status": row.legal_status or "",
        "legal_details": row.legal_details or "",
        "licenses_note": row.licenses_note or "",
        "insurance_note": row.insurance_note or "",
        "has_instructor": "1" if row.has_instructor else "0",
        "instructor_note": row.instructor_note or "",
        "website": row.website or "",
        "socials": row.socials or "",
        "contact_name": row.contact_name or "",
        "contact_phone": row.contact_phone or "",
        "contact_messenger": row.contact_messenger or "",
        "code": row.code,
        "consent": True,
    })
    for activity, fields in cat.CATEGORY_FIELDS.items():
        for field in fields:
            data.setdefault(f"extra_{activity}_{field['key']}", "")
    return data


def _form_page(request, db, data, error="", error_field="", provider=None, target=None, status_code=200, notice=""):
    for activity, fields in cat.CATEGORY_FIELDS.items():
        for field in fields:
            data.setdefault(f"extra_{activity}_{field['key']}", "")
    token, fresh = _csrf_pair(request)
    response = templates.TemplateResponse(
        "leisure_apply.html",
        _ctx(
            request, db, active_nav="leisure",
            values=data, error=error, error_field=error_field, provider=provider, target=target, notice=notice, csrf=token,
            mode="item" if target is not None else "offer",
            activities=cat.ACTIVITIES, legal_statuses=cat.LEGAL_STATUSES, seasons=cat.SEASONS,
            difficulties=cat.DIFFICULTIES, transfers=cat.TRANSFERS, languages=cat.LANGUAGES,
            price_units=cat.PRICE_UNITS, state_required=sorted(cat.STATE_REQUIRED),
            fee_pct=cat.pct_label(cat.LEISURE_SERVICE_FEE_PCT),
            districts=list(DISTRICTS.items()),
            category_fields=cat.CATEGORY_FIELDS, gear_answer=cat.GEAR_ANSWER, briefing_answer=cat.BRIEFING_ANSWER,
            photo_slots=list(range(1, photos.MAX_FILES + 1)), min_width=photos.MIN_WIDTH,
        ),
        status_code=status_code,
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    _set_csrf_cookie(response, fresh)
    return response


def _load_offer(db: Session, offer_id: int) -> LeisureOffer | None:
    return db.execute(
        select(LeisureOffer).where(LeisureOffer.id == offer_id).options(
            selectinload(LeisureOffer.photos),
            selectinload(LeisureOffer.items).selectinload(LeisureItem.photos),
            joinedload(LeisureOffer.provider),
        )
    ).unique().scalars().first()


def resolve_offer(db: Session, request: Request, key: str):
    """Карточка по каноническому слагу или 301 с id, регистра и старого слага."""
    low = key.lower().strip("-")

    def go(obj, redirect: bool):
        if not is_public(obj):
            raise HTTPException(404, "Страница не найдена")
        if not redirect:
            return obj
        query = request.url.query
        location = f"/dosug/{obj.slug}" + (f"?{query}" if query else "")
        return RedirectResponse(location, status_code=301)

    if len(key) <= 120:
        found = db.execute(select(LeisureOffer).where(LeisureOffer.slug == key)).scalars().first()
        if found is not None:
            return go(found, False)
    if key.isdigit() and len(key) <= 9:
        return go(db.get(LeisureOffer, int(key)), True)
    if low != key and len(low) <= 120:
        found = db.execute(select(LeisureOffer).where(LeisureOffer.slug == low)).scalars().first()
        if found is not None:
            return go(found, True)
    old_id = db.execute(
        select(SlugRedirect.entity_id).where(
            SlugRedirect.kind == "leisure", SlugRedirect.old_slug.in_({key, low})
        )
    ).scalars().first()
    if old_id is not None:
        return go(db.get(LeisureOffer, old_id), True)
    raise HTTPException(404, "Страница не найдена")


def _excerpt(text_: str, limit: int = 160) -> str:
    flat = re.sub(r"\s+", " ", text_ or "").strip()
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rsplit(" ", 1)[0] + "…"


def _safe_url(value: str | None) -> str:
    if value and _URL_RE.match(value):
        return value
    return ""


def _group_label(offer: LeisureOffer) -> str:
    if offer.group_min and offer.group_max:
        return f"от {offer.group_min} до {offer.group_max}"
    if offer.group_min:
        return f"от {offer.group_min}"
    if offer.group_max:
        return f"до {offer.group_max}"
    return ""


def _map_url(offer: LeisureOffer) -> str:
    if offer.lat is None or offer.lon is None:
        return ""
    return f"https://yandex.ru/maps/?pt={offer.lon},{offer.lat}&z=15&l=map"


def present_offer(offer: LeisureOffer, districts: dict) -> dict:
    gallery = [p for p in offer.photos if p.item_id is None]
    items = []
    for item in offer.items:
        if item.status != "approved":
            continue
        items.append({
            "title": item.title,
            "quantity": item.quantity,
            "state_text": item.state_text,
            "price_text": item.price_text or "",
            "note": item.note or "",
            "photos": [p for p in item.photos],
        })
    fee = cat.fee_parts(offer.price_amount, offer.service_fee_pct)
    district = districts.get(offer.district) if offer.district else ""
    return {
        "id": offer.id,
        "title": offer.title,
        "lead": _excerpt(offer.description, 180),
        "slug": offer.slug,
        "url": f"/dosug/{offer.slug}",
        "activity": cat.activity_title(offer.activity_type),
        "description": offer.description,
        "meeting_address": offer.meeting_address,
        "finish_address": offer.finish_address,
        "map_url": _map_url(offer),
        "lat": offer.lat,
        "lon": offer.lon,
        "district": district,
        "district_url": f"/okrugi/{offer.district}" if district else "",
        "duration": offer.duration_text,
        "seasons": cat.join_labels(offer.seasons, cat.SEASON_BY_CODE),
        "schedule": offer.schedule_text,
        "weather": offer.weather_terms,
        "price_text": offer.price_text,
        "price_unit": cat.PRICE_UNIT_BY_CODE.get(offer.price_unit or "", ""),
        "included": offer.included or "",
        "excluded": offer.excluded or "",
        "group": _group_label(offer),
        "age": offer.age_text,
        "weight": offer.weight_limit,
        "health": offer.health_limits,
        "difficulty": cat.DIFFICULTY_BY_CODE.get(offer.difficulty, ""),
        "bring": offer.what_to_bring or "",
        "provided": offer.provided_gear or "",
        "transfer": cat.TRANSFER_BY_CODE.get(offer.transfer, ""),
        "transfer_note": offer.transfer_note or "",
        "languages": cat.join_labels(offer.languages, cat.LANGUAGE_BY_CODE),
        "language_note": offer.language_note or "",
        "conditions": offer.conditions,
        "cancellation": offer.cancellation_terms,
        "equipment_state": offer.equipment_state or "",
        "vest": dict(cat.GEAR_ANSWER).get(offer.vest, ""),
        "helmet": dict(cat.GEAR_ANSWER).get(offer.helmet, ""),
        "gear_check": offer.gear_check or "",
        "briefing": dict(cat.BRIEFING_ANSWER).get(offer.briefing, ""),
        "briefing_note": offer.briefing_note or "",
        "extra": cat.public_extra(offer.activity_type, offer.category_extra),
        "supplies": items,
        "show_state": bool(offer.equipment_state or items),
        "photos": gallery,
        "cover": (gallery[0].url if gallery else ""),
        "provider_name": offer.provider.display_name,
        "legal_status": cat.LEGAL_BY_CODE.get(offer.provider.legal_status, ""),
        "has_instructor": offer.provider.has_instructor,
        "docs_on_request": bool(offer.consent_docs),
        "website": _safe_url(offer.provider.website),
        "socials": offer.provider.socials or "",
        "fee": fee,
        "fee_pct": cat.pct_label(offer.service_fee_pct),
        "rub": cat.rub,
    }


def _service_ld(view: dict) -> dict:
    data = {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": view["title"],
        "description": _excerpt(view["description"], 300),
        "url": SITE_URL + view["url"],
        "provider": {"@type": "Organization", "name": view["provider_name"]},
        "areaServed": "Республика Адыгея",
        "inLanguage": "ru-RU",
    }
    return data


@router.get("/dosug")
def leisure_list(request: Request, type: str = "", district: str = "", db: Session = Depends(get_db)):
    query = (
        select(LeisureOffer)
        .where(LeisureOffer.is_published == True, LeisureOffer.status == "approved")
        .options(selectinload(LeisureOffer.photos), joinedload(LeisureOffer.provider))
        .order_by(LeisureOffer.created_at.desc())
    )
    if type in cat.ACTIVITY_BY_CODE:
        query = query.where(LeisureOffer.activity_type == type)
    if district in DISTRICTS:
        query = query.where(LeisureOffer.district == district)
    rows = db.execute(query).unique().scalars().all()
    labels = _ctx(request, db)["districts"]
    cards = []
    for offer in rows:
        gallery = [p for p in offer.photos if p.item_id is None]
        cards.append({
            "url": f"/dosug/{offer.slug}",
            "title": offer.title,
            "activity": cat.activity_title(offer.activity_type),
            "excerpt": _excerpt(offer.description),
            "cover": gallery[0].thumb_url or gallery[0].url if gallery else "",
            "price": offer.price_text,
            "duration": offer.duration_text,
            "district": labels.get(offer.district, ""),
            "where": offer.meeting_address,
        })
    return templates.TemplateResponse(
        "leisure_list.html",
        _ctx(
            request, db, active_nav="leisure", offers=cards, activities=cat.ACTIVITIES,
            selected_type=type if type in cat.ACTIVITY_BY_CODE else "",
            selected_district=district if district in DISTRICTS else "",
            fee_pct=cat.pct_label(cat.LEISURE_SERVICE_FEE_PCT),
        ),
    )


@router.get("/dosug/zayavka")
def leisure_apply_form(request: Request, code: str = "", offer: str = "", sent: str = "",
                       db: Session = Depends(get_db)):
    if sent == "bot":
        return _form_page(request, db, _blank(), notice="Заявка принята.")
    provider = _provider_by_code(db, code) if code else None
    if code and provider is None:
        raise HTTPException(404, "Кабинет не найден")
    target = None
    if offer:
        if provider is None or not offer.isdigit():
            raise HTTPException(404, "Активность не найдена")
        target = db.get(LeisureOffer, int(offer))
        if target is None or target.provider_id != provider.id or target.status == "rejected":
            raise HTTPException(404, "Активность не найдена")
    data = _from_provider(provider) if provider else _blank()
    if target is not None:
        data["mode"] = "item"
        data["offer_id"] = str(target.id)
    page = _form_page(request, db, data, provider=provider, target=target)
    return page


@router.post("/dosug/zayavka")
async def leisure_apply_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    assert_post_guard(request, form)
    assert_rate_limit(request)
    if _text(form, "company_url", 200):
        return RedirectResponse("/dosug/zayavka?sent=bot", status_code=303)
    data = _posted(form)
    provider = _provider_by_code(db, data["code"]) if data["code"] else None
    if data["code"] and provider is None:
        return _form_page(request, db, data, "Кабинет по этому коду не найден", status_code=400)
    target = None
    if data["mode"] == "item" or data["offer_id"]:
        if provider is None or not str(data["offer_id"]).isdigit():
            return _form_page(request, db, data, "Не выбрана активность для поставки", provider=provider, status_code=400)
        target = db.get(LeisureOffer, int(data["offer_id"]))
        if target is None or target.provider_id != provider.id or target.status == "rejected":
            return _form_page(request, db, data, "Эту активность нельзя дополнить", provider=provider, status_code=400)
    try:
        if target is not None:
            item_clean = validate_item(data)
        else:
            provider_clean = validate_provider(data)
            offer_clean = validate_offer(data)
            if provider is None and not data["consent"]:
                raise FormError("Нужно согласие на обработку данных", "consent")
    except FormError as exc:
        return _form_page(request, db, data, exc.message, exc.field, provider=provider, target=target, status_code=400)
    saved: list[dict] = []
    try:
        saved = await _take_photos(form)
        if target is None and saved and not data.get("photos_honest"):
            raise FormError("Подтвердите, что на фото нет логотипов и сгенерированных ИИ изображений", "photos_honest")
        if target is None and saved and data.get("activity_type") in cat.WATER_TYPES and not data.get("photos_vests"):
            raise FormError("Для сплава подтвердите, что на фото все участники в жилетах", "photos_vests")
    except FormError as exc:
        _drop_photos(saved)
        return _form_page(request, db, data, exc.message, exc.field, provider=provider, target=target, status_code=400)
    known_provider = provider if provider is not None and provider.id else None
    try:
        if target is None:
            if provider is None:
                provider = LeisureProvider(
                    code=_new_code(db), consent_version=cat.CONSENT_VERSION,
                    consent_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                db.add(provider)
            _apply_provider(provider, provider_clean)
            if provider.consent_at is None:
                provider.consent_version = cat.CONSENT_VERSION
                provider.consent_at = datetime.now(timezone.utc).replace(tzinfo=None)
            offer = LeisureOffer(
                provider=provider, status="pending", is_published=False,
                service_fee_pct=cat.LEISURE_SERVICE_FEE_PCT,
            )
            _apply_offer(offer, offer_clean)
            db.add(offer)
            db.flush()
            _attach(db, saved, offer.id, None)
            log.info("leisure offer %s type=%s", offer.id, offer.activity_type)
        else:
            item = LeisureItem(offer_id=target.id, status="pending", **item_clean)
            db.add(item)
            db.flush()
            _attach(db, saved, target.id, item.id)
            log.info("leisure item %s offer=%s", item.id, target.id)
        db.commit()
    except Exception:
        _drop_photos(saved)
        db.rollback()
        log.exception("leisure apply failed")
        return _form_page(
            request, db, data, "Не удалось сохранить заявку. Попробуйте ещё раз.",
            provider=known_provider, target=target, status_code=500,
        )
    code = provider.code
    tail = "item" if target is not None else "1"
    return RedirectResponse(f"/dosug/kabinet/{code}?sent={tail}", status_code=303)


@router.get("/dosug/kabinet/{code}")
def leisure_cabinet(request: Request, code: str, sent: str = "", db: Session = Depends(get_db)):
    provider = _provider_by_code(db, code)
    if provider is None:
        raise HTTPException(404, "Кабинет не найден")
    offers = db.execute(
        select(LeisureOffer).where(LeisureOffer.provider_id == provider.id)
        .options(selectinload(LeisureOffer.items))
        .order_by(LeisureOffer.created_at.desc())
    ).scalars().all()
    response = templates.TemplateResponse(
        "leisure_cabinet.html",
        _ctx(
            request, db, active_nav="leisure", provider=provider, offers=offers, sent=sent,
            status_label=cat.STATUS_BY_CODE, activity_title=cat.activity_title,
            state_required=cat.STATE_REQUIRED,
        ),
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@router.get("/dosug/{key}")
def leisure_detail(request: Request, key: str, db: Session = Depends(get_db)):
    found = resolve_offer(db, request, key)
    if isinstance(found, RedirectResponse):
        return found
    offer = _load_offer(db, found.id)
    if not is_public(offer):
        raise HTTPException(404, "Страница не найдена")
    districts = _ctx(request, db)["districts"]
    view = present_offer(offer, districts)
    return templates.TemplateResponse(
        "leisure_detail.html",
        _ctx(
            request, db, active_nav="leisure", offer=view, rub=cat.rub,
            service_ld=_service_ld(view),
            breadcrumbs_ld=seo.breadcrumbs_ld(SITE_URL, [("Досуг", "/dosug"), (offer.title, view["url"])]),
        ),
    )
