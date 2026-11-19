"""Админка партнёров: анкеты, карточки и брони. За тем же HTTP Basic, что /admin.

Обычные HTML-формы с POST и переадресацией, без JS. Номер обращения в боте
(inbox_ref) — единственная связь брони с туристом: имя и телефон туриста
живут в YDB бота (РФ) и сюда не копируются.
"""
import re
from decimal import Decimal, InvalidOperation
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bot_admin import (
    BotApiError, BotNotConfigured, _filter_items, _kind_titles, _load_inbox, _page, require_bot_admin,
)
from app.database import get_db
from app.models import Checkpoint, Partner, PartnerApplication, PartnerLead, Trail
from site_app import partners_audience
from site_app import partners_taxonomy as tx
from site_app.partners import bot_links, pd_in_site_db

router = APIRouter()

APP_STATUSES = [("new", "Новая", "badge-gold"), ("in_progress", "В работе", "badge-draft"),
                ("agreed", "Договорились", "badge-green"), ("rejected", "Отказ", "badge-muted")]
LEAD_STATUSES = [("requested", "Запрос", "badge-gold"), ("confirmed", "Бронь подтверждена", "badge-draft"),
                 ("completed", "Услуга оказана", "badge-green"), ("cancelled", "Отменена", "badge-muted")]
FEE_STATUSES = [("not_paid", "Сбор не оплачен", "badge-gold"), ("paid", "Сбор оплачен", "badge-green"),
                ("refunded", "Сбор возвращён", "badge-muted")]
APP_MAP = {c: (t, b) for c, t, b in APP_STATUSES}
LEAD_MAP = {c: (t, b) for c, t, b in LEAD_STATUSES}
FEE_MAP = {c: (t, b) for c, t, b in FEE_STATUSES}


def _s(form, name, limit=2000):
    v = form.get(name)
    v = "" if v is None else str(v).strip()
    return v[:limit] or None


def _money(value):
    if value in (None, ""):
        return None
    try:
        d = Decimal(str(value).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise HTTPException(400, "Сумма должна быть числом")
    if d < 0 or d > Decimal("100000000"):
        raise HTTPException(400, "Сумма вне диапазона")
    return d.quantize(Decimal("0.01"))


def _ids(value) -> list[int]:
    return [int(x) for x in re.findall(r"\d{1,6}", value or "")][:50]


def _rub(value) -> str:
    if value is None:
        return "—"
    return f"{Decimal(value):,.0f}".replace(",", " ") + " ₽"


def _ctx(request, **extra):
    base = {
        "request": request, "section": "partners", "tx": tx, "rub": _rub,
        "app_statuses": APP_STATUSES, "lead_statuses": LEAD_STATUSES, "fee_statuses": FEE_STATUSES,
        "app_map": APP_MAP, "lead_map": LEAD_MAP, "fee_map": FEE_MAP, "pd_in_site_db": pd_in_site_db(),
    }
    base.update(extra)
    return base


def _lead_totals(rows) -> dict:
    paid = sum((r.service_fee_amount or 0) for r in rows if r.fee_status == "paid")
    pending = sum((r.service_fee_amount or 0) for r in rows if r.fee_status == "not_paid" and r.status != "cancelled")
    gmv = sum((r.provider_price or 0) for r in rows if r.status == "completed")
    return {
        "count": len(rows),
        "completed": sum(1 for r in rows if r.status == "completed"),
        "repeat": sum(1 for r in rows if r.is_repeat),
        "fee_paid": paid, "fee_pending": pending, "gmv": gmv,
    }


@router.get("/admin/partners")
def partners_home(request: Request, tab: str = "applications", status: str = "", saved: str = "",
                  db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    tab = tab if tab in ("applications", "partners", "leads", "audience") else "applications"
    counts = dict(db.execute(select(PartnerApplication.status, func.count()).group_by(PartnerApplication.status)).all())
    ctx = _ctx(request, tab=tab, status=status if status in APP_MAP else "", counts=counts)
    if tab == "applications":
        q = select(PartnerApplication).order_by(PartnerApplication.created_at.desc())
        if ctx["status"]:
            q = q.where(PartnerApplication.status == ctx["status"])
        ctx["applications"] = db.execute(q).scalars().all()
    elif tab == "audience":
        ctx.update(audience_raw=partners_audience.load_raw(db), audience=partners_audience.view(db), saved=saved)
    elif tab == "partners":
        partners = db.execute(select(Partner).order_by(Partner.is_active.desc(), Partner.name)).scalars().all()
        lead_counts = dict(db.execute(select(PartnerLead.partner_id, func.count()).group_by(PartnerLead.partner_id)).all())
        ctx.update(partners=partners, lead_counts=lead_counts)
    else:
        rows = db.execute(select(PartnerLead).order_by(PartnerLead.created_at.desc())).scalars().all()
        names = dict(db.execute(select(Partner.id, Partner.name)).all())
        ctx.update(leads=rows, names=names, totals=_lead_totals(rows))
    return _page("partners_list.html", ctx)


@router.post("/admin/partners/audience")
async def audience_save(request: Request, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    """Цифры аудитории для /partners — переписать вручную из Метрики."""
    form = await request.form()
    values = {k: _s(form, k, 300) for k in partners_audience.INT_FIELDS + partners_audience.STR_FIELDS}
    partners_audience.save(db, values)
    return RedirectResponse("/admin/partners?tab=audience&saved=1", status_code=303)


async def _bot_matches(code: str) -> tuple[list[dict], str]:
    """Обращения в боте с start_payload partner_<код>: только показ, без записи."""
    try:
        raw, _t = await _load_inbox(None)
        titles = await _kind_titles()
    except BotNotConfigured:
        return [], "Бот не подключён (нет BOT_API_TOKEN) — обращения партнёра посмотрите во «Входящих» бота."
    except BotApiError:
        return [], "Бот сейчас не ответил — попробуйте обновить страницу."
    want = f"partner_{code}"
    out = [v for v in _filter_items(raw, titles, None) if v.get("start_payload") == want]
    return out, ""


@router.get("/admin/partners/applications/{app_id}")
async def application_detail(request: Request, app_id: int, saved: str = "",
                             db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    row = db.get(PartnerApplication, app_id)
    if not row:
        raise HTTPException(404, "Заявка не найдена")
    matches, bot_note = await _bot_matches(row.code)
    return _page("partners_application.html", _ctx(
        request, a=row, saved=saved == "1", bot=bot_links(row.code), matches=matches, bot_note=bot_note,
    ))


@router.post("/admin/partners/applications/{app_id}")
async def application_save(request: Request, app_id: int,
                           db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    row = db.get(PartnerApplication, app_id)
    if not row:
        raise HTTPException(404, "Заявка не найдена")
    form = await request.form()
    status = _s(form, "status", 20)
    if status not in APP_MAP:
        raise HTTPException(400, "Неизвестный статус")
    row.status = status
    row.notes = _s(form, "notes", 5000)
    db.commit()
    return RedirectResponse(f"/admin/partners/applications/{app_id}?saved=1", status_code=303)


@router.post("/admin/partners/applications/{app_id}/convert")
def application_convert(app_id: int, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    row = db.get(PartnerApplication, app_id)
    if not row:
        raise HTTPException(404, "Заявка не найдена")
    if row.partner_id and db.get(Partner, row.partner_id):
        return RedirectResponse(f"/admin/partners/{row.partner_id}", status_code=303)
    contacts = {}
    if pd_in_site_db():
        contacts = {k: v for k, v in {
            "name": row.contact_name, "phone": row.contact_phone, "messenger": row.contact_messenger,
        }.items() if v}
    for k, v in (("website", row.website), ("socials", row.socials)):
        if v:
            contacts[k] = v
    contacts["bot_ref"] = f"partner_{row.code}"
    p = Partner(
        name=row.company, category=row.category, subcategory=row.subcategory, location=row.location,
        short=(row.services or "")[:280], description=row.services, price_from=row.prices, seasons=row.seasons,
        discount=row.discount, booking_terms=row.booking_terms, contacts=contacts, is_active=False,
        application_id=row.id, photos=[], place_ids=[], route_ids=[], service_fee_pct=Decimal("5"),
    )
    db.add(p)
    db.flush()
    row.partner_id = p.id
    if row.status in ("new", "in_progress"):
        row.status = "agreed"
    db.commit()
    return RedirectResponse(f"/admin/partners/{p.id}?saved=1", status_code=303)


def _link_options(db: Session):
    places = db.execute(select(Checkpoint.id, Checkpoint.name).where(Checkpoint.show_as_place == True)
                        .order_by(Checkpoint.name)).all()
    routes = db.execute(select(Trail.id, Trail.name).order_by(Trail.name)).all()
    return places, routes


def _card(request, db, p, leads, saved):
    places, routes = _link_options(db)
    return _page("partners_card.html", _ctx(
        request, p=p, leads=leads, totals=_lead_totals(leads), places=places, routes=routes,
        place_names=dict(places), route_names=dict(routes), saved=saved,
    ))


@router.get("/admin/partners/new")
def partner_new(request: Request, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    blank = Partner(name="", category="adventure", photos=[], place_ids=[], route_ids=[], contacts={},
                    service_fee_pct=Decimal("5"), is_active=False)
    return _card(request, db, blank, [], False)


@router.get("/admin/partners/{partner_id}")
def partner_card(request: Request, partner_id: int, saved: str = "",
                 db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    p = db.get(Partner, partner_id)
    if not p:
        raise HTTPException(404, "Партнёр не найден")
    leads = db.execute(select(PartnerLead).where(PartnerLead.partner_id == p.id)
                       .order_by(PartnerLead.created_at.desc())).scalars().all()
    return _card(request, db, p, leads, saved == "1")


@router.post("/admin/partners/save")
async def partner_save(request: Request, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    form = await request.form()
    pid = _s(form, "id", 10)
    p = db.get(Partner, int(pid)) if pid and pid.isdigit() else None
    if pid and not p:
        raise HTTPException(404, "Партнёр не найден")
    name = _s(form, "name", 200)
    category = _s(form, "category", 40)
    sub = _s(form, "subcategory", 40)
    if not name:
        raise HTTPException(400, "Укажите название")
    if not tx.valid_pair(category, sub):
        raise HTTPException(400, "Подкатегория не из этой категории")
    fee = _money(_s(form, "service_fee_pct", 10)) or Decimal("0")
    if fee > 50:
        raise HTTPException(400, "Сбор больше 50% — проверьте")
    photos = [u.strip() for u in (_s(form, "photos", 5000) or "").splitlines() if u.strip().startswith("https://")][:12]
    contacts = {}
    for key in ("website", "socials", "bot_ref") + (("name", "phone", "messenger") if pd_in_site_db() else ()):
        v = _s(form, f"contact_{key}", 300)
        if v:
            contacts[key] = v
    if p is None:
        p = Partner(name=name, category=category)
        db.add(p)
    p.name, p.category, p.subcategory = name, category, sub
    for field in ("location", "short", "description", "price_from", "discount", "booking_terms",
                  "cancellation_terms", "agreement", "notes"):
        setattr(p, field, _s(form, field, 5000))
    p.seasons = ",".join(s for s in form.getlist("seasons") if s in tx.SEASON_TITLES) or None
    p.service_fee_pct = fee
    p.photos = photos
    p.place_ids = _ids(_s(form, "place_ids", 500))
    p.route_ids = _ids(_s(form, "route_ids", 500))
    p.contacts = contacts
    p.is_active = form.get("is_active") == "1"
    p.stay_registry_number = _s(form, "stay_registry_number", 80)
    url = _s(form, "stay_registry_url", 500)
    p.stay_registry_url = url if url and url.startswith("https://") else None
    listed = (form.get("stay_registry_listed") or "").strip()
    p.stay_registry_listed = None if listed not in ("0", "1") else listed == "1"
    checked = _s(form, "stay_registry_checked_on", 20)
    try:
        p.stay_registry_checked_on = date.fromisoformat(checked) if checked else None
    except ValueError:
        p.stay_registry_checked_on = None
    db.commit()
    return RedirectResponse(f"/admin/partners/{p.id}?saved=1", status_code=303)


def _apply_lead(lead: PartnerLead, form, partner: Partner):
    status = _s(form, "status", 20) or "requested"
    fee_status = _s(form, "fee_status", 20) or "not_paid"
    if status not in LEAD_MAP or fee_status not in FEE_MAP:
        raise HTTPException(400, "Неизвестный статус")
    lead.inbox_ref = _s(form, "inbox_ref", 40)
    lead.service = _s(form, "service", 200)
    raw_date = _s(form, "service_date", 10)
    try:
        lead.service_date = date.fromisoformat(raw_date) if raw_date else None
    except ValueError:
        raise HTTPException(400, "Дата в формате ГГГГ-ММ-ДД")
    lead.people = _s(form, "people", 60)
    lead.status, lead.fee_status = status, fee_status
    lead.provider_price = _money(_s(form, "provider_price", 20))
    lead.discount_amount = _money(_s(form, "discount_amount", 20))
    pct = _money(_s(form, "service_fee_pct", 10))
    lead.service_fee_pct = pct if pct is not None else partner.service_fee_pct
    fee = _money(_s(form, "service_fee_amount", 20))
    if fee is None and lead.provider_price is not None and lead.service_fee_pct is not None:
        fee = (lead.provider_price * lead.service_fee_pct / 100).quantize(Decimal("1"))
    lead.service_fee_amount = fee
    # Модель 15.11: скидка партнёра по умолчанию равна сбору АдыГида.
    if lead.discount_amount is None and fee is not None:
        lead.discount_amount = fee
    lead.is_repeat = form.get("is_repeat") == "1"
    lead.notes = _s(form, "notes", 2000)


@router.post("/admin/partners/{partner_id}/leads")
async def lead_add(request: Request, partner_id: int, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    p = db.get(Partner, partner_id)
    if not p:
        raise HTTPException(404, "Партнёр не найден")
    lead = PartnerLead(partner_id=p.id)
    _apply_lead(lead, await request.form(), p)
    db.add(lead)
    db.commit()
    return RedirectResponse(f"/admin/partners/{p.id}?saved=1#leads", status_code=303)


@router.post("/admin/partners/leads/{lead_id}")
async def lead_update(request: Request, lead_id: int, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    lead = db.get(PartnerLead, lead_id)
    if not lead:
        raise HTTPException(404, "Бронь не найдена")
    form = await request.form()
    p = db.get(Partner, lead.partner_id)
    if form.get("delete") == "1":
        db.delete(lead)
    else:
        _apply_lead(lead, form, p)
    db.commit()
    return RedirectResponse(f"/admin/partners/{p.id}?saved=1#leads", status_code=303)
