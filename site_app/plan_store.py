"""«Сохранить план в бота»: короткий id → план по дням.

Сайт кладёт сюда состав плана (ключи мест и маршрутов по дням, дорога),
бот MAX/Telegram забирает его по id из ссылки start=plan_<id> и присылает
туристу по дням. Названия, ссылки и координаты берутся из живого каталога
в момент чтения, поэтому в базе нет произвольного текста от браузера.
Персональных данных здесь нет: только случайный session_id браузера.
"""
import hashlib
import json
import logging
import re
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.database import get_db
from site_app.podbor_catalog import AREAS, catalog_items

log = logging.getLogger("adygid.plans")
router = APIRouter()

SITE = "https://www.adygid.ru"
MAX_BOT = "https://max.ru/se15002131_bot"
TG_BOT = "https://t.me/adygid_bot"
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_ID_RE = re.compile(r"^[A-Za-z0-9]{6,16}$")
_HASH_RE = re.compile(r"^plan=[a-z0-9.,]{8,200}$")


class PlanStopIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    k: str = Field(pattern=r"^(place|route):\d{1,6}$")
    drive: int | None = Field(default=None, ge=0, le=1000)
    also: bool = False


class PlanDayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area: str | None = Field(default=None, pattern=r"^[a-z_]{1,24}$")
    empty: bool = False
    total_min: int | None = Field(default=None, ge=0, le=2000)
    return_drive: int | None = Field(default=None, ge=0, le=1000)
    stops: list[PlanStopIn] = Field(default_factory=list, max_length=12)


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{4,64}$")
    hash: str = Field(max_length=210)
    season: str | None = Field(default=None, pattern=r"^(winter|summer|any)$")
    days: list[PlanDayIn] = Field(min_length=1, max_length=7)


def _new_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def fmt_min(m) -> str:
    """Как fmtMin в podbor-core.js: 95 → «1 ч 35 мин»."""
    if m is None:
        return ""
    m = int(round(m / 5.0) * 5)
    h, r = divmod(m, 60)
    if h:
        return f"{h} ч" + (f" {r} мин" if r else "")
    return f"{r} мин"


def fmt_range(v: dict) -> str:
    """Как fmtRange в podbor-core.js."""
    if not v:
        return ""
    lo, typ, hi = v.get("min"), v.get("typ"), v.get("max")
    if v.get("source") == "card" or lo == hi:
        return fmt_min(typ)
    if lo % 60 == 0 and hi % 60 == 0:
        return f"{lo // 60}–{hi // 60} ч"
    if hi <= 60:
        return f"{lo}–{hi} мин"
    return f"{fmt_min(lo)} – {fmt_min(hi)}"


def yandex_day_url(points: list) -> str:
    """Та же ссылка, что «Открыть день в Яндекс Картах» на странице плана."""
    pts = [(round(float(a), 6), round(float(b), 6)) for a, b in points if a is not None and b is not None]
    if len(pts) >= 2:
        return "https://yandex.ru/maps/?rtext=" + "~".join(f"{a},{b}" for a, b in pts) + "&rtt=auto"
    if len(pts) == 1:
        return f"https://yandex.ru/maps/?pt={pts[0][1]},{pts[0][0]}&z=14"
    return ""


def _missing_table(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "podbor_plans" in msg or "does not exist" in msg or "undefinedtable" in msg


def _index(db: Session) -> dict:
    return {f'{x["type"]}:{x["id"]}': x for x in catalog_items(db)}


def save_plan(db: Session, body: PlanIn) -> dict:
    if not _HASH_RE.match(body.hash):
        raise HTTPException(400, "Некорректная ссылка плана")
    known = _index(db)
    days = []
    for d in body.days:
        stops = [s.model_dump() for s in d.stops if s.k in known]
        if d.stops and not stops:
            raise HTTPException(400, "В плане нет известных мест")
        days.append({"area": d.area if d.area in AREAS else None, "empty": bool(d.empty or not stops),
                     "total_min": d.total_min, "return_drive": d.return_drive, "stops": stops})
    if not any(day["stops"] for day in days):
        raise HTTPException(400, "План пустой")
    data = {"v": 1, "hash": body.hash, "season": body.season, "days": days}
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sig = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
    try:
        if body.session_id:
            row = db.execute(
                text("SELECT id FROM podbor_plans WHERE session_id = :s AND sig = :g LIMIT 1"),
                {"s": body.session_id, "g": sig},
            ).first()
            if row:
                return _links(row[0], reused=True)
        for _ in range(5):
            pid = _new_id()
            if not db.execute(text("SELECT 1 FROM podbor_plans WHERE id = :i"), {"i": pid}).first():
                break
        db.execute(
            text("INSERT INTO podbor_plans (id, session_id, sig, data) VALUES (:i, :s, :g, :d)"),
            {"i": pid, "s": body.session_id, "g": sig, "d": raw},
        )
        db.commit()
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        if _missing_table(exc):
            log.warning("podbor_plans table missing; plan not stored")
            raise HTTPException(503, "Сохранение планов временно недоступно")
        raise
    return _links(pid)


def _links(pid: str, reused: bool = False) -> dict:
    return {
        "ok": True,
        "id": pid,
        "reused": reused,
        "max_url": f"{MAX_BOT}?start=plan_{pid}",
        "tg_url": f"{TG_BOT}?start=plan_{pid}",
    }


def load_plan(db: Session, pid: str, count_open: bool = False) -> dict | None:
    if not _ID_RE.match(pid or ""):
        return None
    try:
        row = db.execute(
            text("SELECT id, data, created_at FROM podbor_plans WHERE id = :i"), {"i": pid}
        ).first()
        if row and count_open:
            db.execute(
                text("UPDATE podbor_plans SET opens = opens + 1, last_open_at = now() WHERE id = :i"),
                {"i": pid},
            )
            db.commit()
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        if _missing_table(exc):
            return None
        raise
    if not row:
        return None
    data = json.loads(row[1])
    known = _index(db)
    days_out = []
    for i, d in enumerate(data.get("days") or []):
        stops = []
        points = []
        for s in d.get("stops") or []:
            x = known.get(s.get("k"))
            if not x:
                continue  # место сняли с публикации — просто пропускаем
            stops.append({
                "type": x["type"],
                "id": x["id"],
                "name": x["name"],
                "url": SITE + x["url"],
                "drive_min": s.get("drive"),
                "visit": fmt_range(x.get("visit") or {}),
                "also": bool(s.get("also")),
                "winter_check": data.get("season") == "winter" and x.get("winter_ok") == "unknown",
            })
            points.append((x.get("lat"), x.get("lon")))
        area = d.get("area")
        days_out.append({
            "n": i + 1,
            "area": area,
            "area_name": AREAS[area][0] if area in AREAS else "Адыгея",
            "empty": not stops,
            "total_min": d.get("total_min"),
            "total": fmt_min(d.get("total_min")) if d.get("total_min") else "",
            "return_drive_min": d.get("return_drive"),
            "map_url": yandex_day_url(points),
            "stops": stops,
        })
    created = row[2]
    return {
        "id": row[0],
        "created_at": created.isoformat() if created else None,
        "season": data.get("season"),
        "n_days": len(days_out),
        "site_url": f"{SITE}/podbor#" + quote(data.get("hash") or "", safe="=.,"),
        "days": days_out,
        **{k: v for k, v in _links(row[0]).items() if k.endswith("_url")},
    }


@router.post("/api/podbor/plans", status_code=201)
def post_plan(body: PlanIn, db: Session = Depends(get_db)):
    return save_plan(db, body)


@router.get("/api/podbor/plans/{plan_id}")
def get_plan(plan_id: str, bot: int = 0, db: Session = Depends(get_db)):
    plan = load_plan(db, plan_id, count_open=bool(bot))
    if not plan:
        raise HTTPException(404, "План не найден")
    return plan
