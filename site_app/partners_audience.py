"""Цифры аудитории для страницы /partners — только настоящие, из Метрики.

Источник по умолчанию — site_app/data/partners_audience.json (его пишет
scripts/partners_audience_metrika.py). Если в админке /admin/partners на
вкладке «Цифры для /partners» сохранены свои значения, они лежат в таблице
partner_settings (ключ audience) и перекрывают файл.

Округляем только вниз и честно: 303 → «300+», 1 027 → «1 000+». Рост
показываем, только если он положительный.
"""
import json
import logging
import os
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("adygid.partners")
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "partners_audience.json")
SETTINGS_KEY = "audience"

INT_FIELDS = ("users_30d", "visits_30d", "pageviews_30d", "users_prev_30d", "users_total", "search_share_visits")
STR_FIELDS = ("period_from", "period_to", "total_since", "top_regions", "updated")
_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"]
_MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
               "сентябрь", "октябрь", "ноябрь", "декабрь"]


def _file_defaults() -> dict:
    try:
        with open(DATA_FILE, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        log.warning("partners audience file missing or broken")
        raw = {}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def clean(raw: dict) -> dict:
    out: dict = {}
    for k in INT_FIELDS:
        v = raw.get(k)
        if v in (None, ""):
            continue
        try:
            n = int(str(v).replace(" ", "").replace("\u00a0", ""))
        except ValueError:
            continue
        if n >= 0:
            out[k] = n
    for k in STR_FIELDS:
        v = raw.get(k)
        if v not in (None, ""):
            out[k] = str(v).strip()[:300]
    return out


def load_raw(db: Session | None = None) -> dict:
    data = clean(_file_defaults())
    if db is not None:
        try:
            row = db.execute(text("SELECT value FROM partner_settings WHERE key = :k"), {"k": SETTINGS_KEY}).first()
            if row and row[0]:
                data.update(clean(json.loads(row[0])))
        except Exception:
            db.rollback()
            log.warning("partner_settings unavailable, using file defaults")
    return data


def save(db: Session, values: dict) -> dict:
    data = clean(values)
    data["updated"] = data.get("updated") or date.today().isoformat()
    db.execute(
        text("INSERT INTO partner_settings (key, value, updated_at) VALUES (:k, :v, now()) "
             "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"),
        {"k": SETTINGS_KEY, "v": json.dumps(data, ensure_ascii=False)},
    )
    db.commit()
    return data


def round_down(n: int) -> int:
    """Красивое число не больше настоящего."""
    if n < 100:
        return n
    if n < 1000:
        return n // 50 * 50
    if n < 10000:
        return n // 100 * 100
    return n // 1000 * 1000


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", "\u00a0")


def _day(iso: str | None) -> str:
    try:
        d = date.fromisoformat(iso or "")
    except ValueError:
        return ""
    return f"{d.day} {_MONTHS[d.month - 1]}"


def view(db: Session | None = None) -> dict:
    """Готовые подписи для шаблона."""
    d = load_raw(db)
    users = d.get("users_30d", 0)
    total = d.get("users_total", 0)
    prev = d.get("users_prev_30d", 0)
    growth = round((users - prev) * 100 / prev) if prev and users > prev else 0
    since = ""
    if d.get("total_since"):
        try:
            y, m = d["total_since"].split("-")[:2]
            since = f"{_MONTHS_NOM[int(m) - 1]} {y}"
        except (ValueError, IndexError):
            since = d["total_since"]
    year = (d.get("period_to") or "")[:4]
    period = f"{_day(d.get('period_from'))} — {_day(d.get('period_to'))} {year}".strip(" —")
    return {
        "users_30d": users,
        "users_30d_label": (fmt(round_down(users)) + "+") if users >= 100 else fmt(users),
        "visits_30d": d.get("visits_30d", 0),
        "visits_30d_label": (fmt(round_down(d.get("visits_30d", 0))) + "+") if d.get("visits_30d", 0) >= 100 else fmt(d.get("visits_30d", 0)),
        "pageviews_30d": d.get("pageviews_30d", 0),
        "users_total": total,
        "users_total_label": (fmt(round_down(total)) + "+") if total >= 100 else fmt(total),
        "since": since,
        "growth_pct": growth if growth > 0 else 0,
        "search_share": d.get("search_share_visits", 0),
        "top_regions": d.get("top_regions", ""),
        "period": period,
        "updated": d.get("updated", ""),
    }
