"""Партнёрский раздел: страница /partners и приём анкеты поставщика.

Страница доступна только по прямой ссылке (решение Frank 15.11): её нет в меню,
подвале, sitemap.xml и перелинковке, в <head> стоит noindex, follow. Старый
адрес /partneram отдаёт 301 на /partners.

Модель (решение 15.11.2026): партнёр ничего не платит ни за размещение, ни за
клиентов. Турист бронирует через АдыГид и платит АдыГиду собственный сервисный
сбор за подбор и бронь, услугу — партнёру на месте. Партнёр даёт клиентам
АдыГида скидку и не уводит их в обход сервиса.

152-ФЗ: база сайта стоит не в РФ (политика, раздел 6), поэтому имя контакта,
телефон и мессенджер по умолчанию сюда не пишутся. Анкета сохраняет сведения
о бизнесе, а контакт партнёр отправляет боту по ссылке ?start=partner_<код> —
обращение ложится в YDB (РФ), и бот сам шлёт уведомление в рабочие чаты.
PARTNER_PD_IN_SITE_DB=1 включает поля контактов прямо в анкете (только если
база сайта переехала в РФ).
"""
import logging
import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import Article, District, Scenario, PartnerApplication
from site_app import partners_audience
from site_app import partners_taxonomy as tx
from site_app.router import REVIEW_BOT, REVIEW_BOT_TG, _ctx, _footer_stats, templates

log = logging.getLogger("adygid.partners")
router = APIRouter()

CONSENT_VERSION = "1.0"
MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261115_partners.sql")
REGISTRY_MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261119_partner_stay_registry.sql")

# Реальные фото Адыгеи из базы сайта (места 54, 43, 72, 86, 55, 24).
_MEDIA = "https://hiotbrjgilwlztlfdkmg.supabase.co/storage/v1/object/public/uploads/"
PHOTOS = {
    "hero": (_MEDIA + "c911e2fb0705495686d34fce42913d1b.webp", "Рафт на порогах Белой у Даховской"),
    "plateau": (_MEDIA + "122d8d600b2444c0951446c8dda2498d.webp", "Плато Лаго-Наки"),
}
# «Рядом с какими местами»: настоящие карточки сайта (фото, подпись, ссылка).
SHOWCASE = [
    (_MEDIA + "448c4b816ebf4e748411e4320a874734.jpeg", "Хаджохская теснина", "/mesta/24", "Квадроциклы, джиппинг, кафе, гостевые дома"),
    (_MEDIA + "722b267dfc4b47c0b2dd6108581eaa62.webp", "Экстрим-парк «Мишоко»", "/mesta/43", "Конные прогулки, джип-туры, прокат"),
    (_MEDIA + "ef08fb489f5041e9a4c72371f0af7c6d.webp", "Термы «Псыгупс»", "/mesta/72", "Жильё, трансфер, ужин после терм"),
    (_MEDIA + "57c9f6c208bd468592a2235fb533b5a3.webp", "Козья ферма и сыроварня «Мамонтий»", "/mesta/86", "Дегустации, пасеки, трансфер"),
]


def pd_in_site_db() -> bool:
    return os.getenv("PARTNER_PD_IN_SITE_DB", "").strip() in ("1", "true", "yes")


def ensure_partner_tables() -> None:
    try:
        raw = open(MIGRATION, encoding="utf-8").read()
    except OSError:
        log.warning("partners migration missing")
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
        log.exception("partners migration failed")
    try:
        raw = open(REGISTRY_MIGRATION, encoding="utf-8").read()
    except OSError:
        log.warning("stay registry migration missing")
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
        log.exception("stay registry migration failed")


def bot_links(code: str) -> dict:
    payload = f"partner_{code}"
    return {"max": f"{REVIEW_BOT}?start={payload}", "telegram": f"{REVIEW_BOT_TG}?start={payload}"}


def _facts(db: Session) -> dict:
    stats = _footer_stats(db)
    articles = db.execute(select(func.count()).select_from(Article).where(Article.is_published == True)).scalar() or 0
    districts = db.execute(select(func.count()).select_from(District).where(District.is_published == True)).scalar() or 0
    scenarios = db.execute(select(func.count()).select_from(Scenario).where(Scenario.is_published == True)).scalar() or 0
    return {"places": stats["places"], "routes": stats["trails"], "articles": articles,
            "districts": districts, "scenarios": scenarios}


PAGE_PATH = "/partners"


@router.get("/partneram")
@router.get("/partneram/")
def partners_old_url():
    return RedirectResponse(PAGE_PATH, status_code=301)


@router.get("/partners")
def partners_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "partners.html",
        _ctx(
            request, db, active_nav=None,
            facts=_facts(db),
            audience=partners_audience.view(db),
            categories=tx.CATEGORIES,
            taxonomy_json=tx.as_json(),
            seasons=tx.SEASONS,
            lead_channels=tx.LEAD_CHANNELS,
            photos=PHOTOS,
            showcase=SHOWCASE,
            pd_in_site_db=pd_in_site_db(),
            bot_max=REVIEW_BOT,
            bot_tg=REVIEW_BOT_TG,
        ),
    )


_PHONE_RE = re.compile(r"^[+\d][\d\s()\-]{8,20}$")
_URL_RE = re.compile(r"^(https?://)?[\w.-]+\.[a-zа-я]{2,}(/\S*)?$|^@?[\w.]{3,64}$", re.I)


class PartnerApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    company: str = Field(min_length=2, max_length=200)
    category: str = Field(max_length=40)
    subcategory: str | None = Field(default=None, max_length=40)
    location: str = Field(min_length=2, max_length=200)
    services: str = Field(min_length=3, max_length=3000)
    prices: str | None = Field(default=None, max_length=2000)
    seasons: list[str] = Field(default_factory=list, max_length=5)
    discount: str = Field(min_length=1, max_length=500)
    booking_terms: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=500)
    socials: str | None = Field(default=None, max_length=500)
    lead_channels: list[str] = Field(default_factory=list, max_length=5)
    comment: str | None = Field(default=None, max_length=2000)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, max_length=40)
    contact_messenger: str | None = Field(default=None, max_length=120)
    consent: bool
    source: str | None = Field(default=None, max_length=80)
    website_hp: str | None = Field(default=None, max_length=200)  # ловушка для ботов


def _new_code(db: Session) -> str:
    for _ in range(8):
        code = secrets.token_hex(4)
        if not db.execute(select(PartnerApplication.id).where(PartnerApplication.code == code)).first():
            return code
    raise HTTPException(500, "Не удалось выдать номер заявки")


def save_application(db: Session, body: PartnerApplyIn) -> dict:
    if body.website_hp:
        return {"ok": True, "code": "00000000", "bot": bot_links("00000000"), "contacts_via_bot": True}
    if not body.consent:
        raise HTTPException(400, "Нужно согласие на обработку данных")
    if not tx.valid_pair(body.category, body.subcategory or None):
        raise HTTPException(400, "Выберите категорию из списка")
    seasons = [s for s in body.seasons if s in tx.SEASON_TITLES]
    channels = [c for c in body.lead_channels if c in tx.LEAD_CHANNEL_TITLES]
    store_pd = pd_in_site_db()
    if store_pd:
        if not body.contact_phone and not body.contact_messenger:
            raise HTTPException(400, "Оставьте телефон или мессенджер")
        if body.contact_phone and not _PHONE_RE.match(body.contact_phone):
            raise HTTPException(400, "Проверьте номер телефона")
    app_row = PartnerApplication(
        code=_new_code(db),
        company=body.company,
        category=body.category,
        subcategory=body.subcategory or None,
        location=body.location,
        services=body.services,
        prices=body.prices or None,
        seasons=",".join(seasons) or None,
        discount=body.discount,
        booking_terms=body.booking_terms or None,
        website=body.website or None,
        socials=body.socials or None,
        lead_channels=",".join(channels) or None,
        comment=body.comment or None,
        contact_name=(body.contact_name or None) if store_pd else None,
        contact_phone=(body.contact_phone or None) if store_pd else None,
        contact_messenger=(body.contact_messenger or None) if store_pd else None,
        consent_version=CONSENT_VERSION,
        consent_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status="new",
    )
    db.add(app_row)
    db.commit()
    # В журнал — только номер и категория: ни названия, ни контактов.
    log.info("partner application %s category=%s", app_row.code, app_row.category)
    return {"ok": True, "code": app_row.code, "bot": bot_links(app_row.code), "contacts_via_bot": not store_pd}


@router.post("/api/partners/apply", status_code=201)
def post_partner_application(body: PartnerApplyIn, db: Session = Depends(get_db)):
    return save_application(db, body)
