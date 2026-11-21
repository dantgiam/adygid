"""Модерация досуга: /admin/dosug. Тот же HTTP Basic, что у остальной админки.

Админ правит любой текст, включая условия и состояние, и публикует или
отклоняет. Черновик на сайт не выходит. Сбор заявки — процент этой карточки,
у новой он 5%. Карточки партнёров и их сбор здесь не меняются.
"""
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.bot_admin import (
    BotApiError, BotNotConfigured, _filter_items, _kind_titles, _load_inbox, _page, require_bot_admin,
)
from app.database import get_db
from app.models import LeisureItem, LeisureOffer, LeisurePhoto, LeisureProvider
from app.slugs import set_slug
from site_app.content import DISTRICTS
from site_app import leisure_catalog as cat
from site_app.leisure import (
    FormError, _apply_offer, _apply_provider, _attach, _csrf_pair, _drop_photos, _posted, _set_csrf_cookie,
    _take_photos, assert_post_guard, leisure_bot_links, validate_offer, validate_provider,
)
from site_app.partners import pd_in_site_db
from site_app import leisure_photos as photos

router = APIRouter()
_RESERVED = {"zayavka", "kabinet"}


def _load(db: Session, offer_id: int) -> LeisureOffer | None:
    return db.execute(
        select(LeisureOffer).where(LeisureOffer.id == offer_id).options(
            selectinload(LeisureOffer.photos),
            selectinload(LeisureOffer.items).selectinload(LeisureItem.photos),
            joinedload(LeisureOffer.provider),
        )
    ).unique().scalars().first()


def _fee(value: str, current: Decimal) -> Decimal:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return Decimal(current)
    try:
        number = Decimal(raw)
    except InvalidOperation:
        raise FormError("Сбор должен быть числом")
    if number < 0 or number > 50:
        raise FormError("Сбор досуга — от 0 до 50%")
    return number.quantize(Decimal("0.01"))


def _status(offer: LeisureOffer, action: str) -> None:
    if action == "approve":
        offer.status = "approved"
        offer.is_published = True
    elif action == "reject":
        offer.status = "rejected"
        offer.is_published = False
    elif action == "pending":
        offer.status = "pending"
        offer.is_published = False
    elif action == "save":
        offer.is_published = offer.status == "approved"
    else:
        raise FormError("Неизвестное действие")


def _items(form, offer: LeisureOffer) -> None:
    for item in offer.items:
        prefix = f"item_{item.id}_"
        title = (form.get(f"{prefix}title") or "")
        title = title.strip() if isinstance(title, str) else ""
        state = form.get(f"{prefix}state")
        state = state.strip() if isinstance(state, str) else ""
        if len(title) < 2 or len(state) < 2:
            raise FormError(f"У поставки «{item.title}» нужны название и состояние")
        status = (form.get(f"{prefix}status") or item.status)
        if isinstance(status, str):
            status = status.strip()
        if status not in cat.STATUS_BY_CODE:
            raise FormError("Неизвестный статус поставки")
        price = form.get(f"{prefix}price_amount")
        price = price.strip() if isinstance(price, str) else ""
        amount = None
        if price:
            try:
                amount = Decimal(price.replace(" ", "").replace(",", "."))
            except InvalidOperation:
                raise FormError("Цена поставки должна быть числом")
            if amount < 0 or amount > Decimal("10000000"):
                raise FormError("Цена поставки вне диапазона")
            amount = amount.quantize(Decimal("0.01"))
        qty_raw = form.get(f"{prefix}quantity")
        qty_raw = qty_raw.strip() if isinstance(qty_raw, str) else ""
        quantity = None
        if qty_raw:
            if not qty_raw.isdigit() or not (1 <= int(qty_raw) <= 9999):
                raise FormError("Количество поставки вне диапазона")
            quantity = int(qty_raw)
        note = form.get(f"{prefix}note")
        price_text = form.get(f"{prefix}price_text")
        item.title = title[:200]
        item.state_text = state[:5000]
        item.status = status
        item.price_amount = amount
        item.price_text = (price_text.strip()[:300] if isinstance(price_text, str) and price_text.strip() else None)
        item.quantity = quantity
        item.note = (note.strip()[:3000] if isinstance(note, str) and note.strip() else None)


@router.get("/admin/dosug")
def leisure_admin_list(request: Request, status: str = "pending", db: Session = Depends(get_db),
                       _: str = Depends(require_bot_admin)):
    chosen = status if status in cat.STATUS_BY_CODE or status == "all" else "pending"
    counts = dict(db.execute(select(LeisureOffer.status, func.count()).group_by(LeisureOffer.status)).all())
    query = (
        select(LeisureOffer)
        .options(joinedload(LeisureOffer.provider))
        .order_by(LeisureOffer.created_at.desc())
    )
    if chosen != "all":
        query = query.where(LeisureOffer.status == chosen)
    rows = db.execute(query).unique().scalars().all()
    return _page("leisure_admin_list.html", {
        "request": request, "section": "leisure", "rows": rows, "status": chosen,
        "counts": counts, "status_label": cat.STATUS_BY_CODE, "activity_title": cat.activity_title,
        "rub": cat.rub, "fee_parts": cat.fee_parts, "pct_label": cat.pct_label,
    })


_TELEGRAM_KEYS = ("telegram", "tg", "username")


def _payload_telegram(raw: dict) -> str | None:
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    for key in _TELEGRAM_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return None


async def _leisure_bot_matches(code: str) -> tuple[list[dict], str]:
    """Обращения с start_payload leisure_<код>: только показ, в базу сайта не пишем."""
    try:
        raw, _t = await _load_inbox(None)
        titles = await _kind_titles()
    except BotNotConfigured:
        return [], "Бот не подключён (нет BOT_API_TOKEN) — контакты организатора посмотрите во «Входящих» бота."
    except BotApiError:
        return [], "Бот сейчас не ответил — попробуйте обновить страницу."
    want = f"leisure_{code}"
    telegram_by_id = {
        item.get("id"): _payload_telegram(item)
        for item in raw
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    out = []
    for view in _filter_items(raw, titles, None):
        if view.get("start_payload") != want:
            continue
        row = dict(view)
        row["telegram"] = telegram_by_id.get(view["id"])
        out.append(row)
    return out, ""


@router.get("/admin/dosug/{offer_id}")
async def leisure_admin_offer(request: Request, offer_id: int, saved: str = "", error: str = "",
                              db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    offer = _load(db, offer_id)
    if offer is None:
        raise HTTPException(404, "Заявка не найдена")
    return await _render(request, offer, saved == "1", error)


async def _render(request, offer, saved, error, status_code=200):
    token, fresh = _csrf_pair(request)
    code = offer.provider.code if offer.provider is not None else ""
    matches, bot_note = await _leisure_bot_matches(code) if code else ([], "")
    response = _page("leisure_admin_offer.html", {
        "request": request, "section": "leisure", "o": offer, "saved": saved, "error": error, "csrf": token,
        "matches": matches, "bot_note": bot_note, "pd_in_site_db": pd_in_site_db(),
        "bot": leisure_bot_links(code) if code else {"max": "", "telegram": ""},
        "activities": cat.ACTIVITIES, "legal_statuses": cat.LEGAL_STATUSES, "seasons": cat.SEASONS,
        "difficulties": cat.DIFFICULTIES, "transfers": cat.TRANSFERS, "languages": cat.LANGUAGES,
        "price_units": cat.PRICE_UNITS, "statuses": cat.STATUSES, "districts": list(DISTRICTS.items()),
        "state_required": cat.STATE_REQUIRED, "fee": cat.fee_parts(offer.price_amount, offer.service_fee_pct),
        "rub": cat.rub, "pct_label": cat.pct_label, "needs_state": cat.needs_state(offer.activity_type),
        "category_fields": cat.CATEGORY_FIELDS, "gear_answer": cat.GEAR_ANSWER, "briefing_answer": cat.BRIEFING_ANSWER,
        "photo_slots": [1, 2, 3, 4],
    }, status_code=status_code)
    _set_csrf_cookie(response, fresh)
    return response


@router.post("/admin/dosug/{offer_id}")
async def leisure_admin_save(request: Request, offer_id: int, db: Session = Depends(get_db),
                             _: str = Depends(require_bot_admin)):
    offer = _load(db, offer_id)
    if offer is None:
        raise HTTPException(404, "Заявка не найдена")
    form = await request.form()
    assert_post_guard(request, form)
    action = form.get("action") if isinstance(form.get("action"), str) else "save"
    data = _posted(form)
    saved_photos: list[dict] = []
    try:
        provider_clean = validate_provider(data)
        offer_clean = validate_offer(data)
        saved_photos = await _take_photos(form)
        if saved_photos and not data.get("photos_honest"):
            raise FormError("Подтвердите, что на фото нет логотипов и сгенерированных ИИ изображений")
        if saved_photos and data.get("activity_type") in cat.WATER_TYPES and not data.get("photos_vests"):
            raise FormError("Для сплава подтвердите, что на фото все участники в жилетах")
        fee = _fee(form.get("service_fee_pct") if isinstance(form.get("service_fee_pct"), str) else "", offer.service_fee_pct)
        _items(form, offer)
        slug_raw = form.get("slug")
        slug_raw = slug_raw.strip() if isinstance(slug_raw, str) else ""
        for photo in list(offer.photos):
            alt = form.get(f"alt_id_{photo.id}")
            if not isinstance(alt, str):
                continue
            alt = alt.strip()
            if len(alt) < 3:
                raise FormError("У каждого фото нужна подпись")
            photo.alt = alt[:300]
        _apply_provider(offer.provider, provider_clean)
        _apply_offer(offer, offer_clean)
        offer.service_fee_pct = fee
        note = form.get("moderation_note")
        admin_notes = form.get("admin_notes")
        offer.moderation_note = note.strip()[:3000] if isinstance(note, str) and note.strip() else None
        offer.admin_notes = admin_notes.strip()[:5000] if isinstance(admin_notes, str) and admin_notes.strip() else None
        _status(offer, action)
        if slug_raw and slug_raw != (offer.slug or ""):
            new_slug = set_slug(db, offer, slug_raw)
            if new_slug in _RESERVED:
                raise FormError("Этот адрес занят разделом «заявка» или «кабинет»")
        for raw_id in form.getlist("delete_photo"):
            if not str(raw_id).isdigit():
                continue
            photo = db.get(LeisurePhoto, int(raw_id))
            if photo is None or photo.offer_id != offer.id:
                continue
            photos.forget(photo.url)
            photos.forget(photo.thumb_url)
            db.delete(photo)
        if saved_photos:
            db.flush()
            start = max((p.sort_order for p in offer.photos), default=-1) + 1
            for index, row in enumerate(saved_photos):
                db.add(LeisurePhoto(
                    offer_id=offer.id, url=row["url"], thumb_url=row["thumb_url"],
                    alt=row.get("alt") or "", sort_order=start + index,
                ))
        db.commit()
    except FormError as exc:
        _drop_photos(saved_photos)
        db.rollback()
        fresh = _load(db, offer_id)
        return await _render(request, fresh, False, exc.message, status_code=400)
    except Exception:
        _drop_photos(saved_photos)
        db.rollback()
        raise
    return RedirectResponse(f"/admin/dosug/{offer.id}?saved=1", status_code=303)
