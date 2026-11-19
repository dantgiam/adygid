"""Плашка «Новогодние каникулы» в подборе.

Совет как от знакомого местного: три действия, без прогнозов «до 9:00
будет свободно». Цена и способ оплаты на КПП, часы запасных мест берутся
из тех же проверенных фактов, что и «Коротко для поездки» на карточках
(seo.PLACE_PRACTICAL[...]["facts"]), — поменяли там, поменялось и здесь.

Окна дат считаются по Москве:
- 20.12–08.01 — плашка видна всем;
- 15.11–19.12 — только тем, кто выбрал в подборе «зима» (планируют каникулы).
Сама плашка (текст, даты, вкл/выкл) с 19.11.2026 живёт в базе — таблица
site_notices, правится в админке «Тексты сайта → Плашки». Здесь — сборка
автоматического текста (варианты A и B) и правила окон; если таблицы нет
недоступна, работает прежняя плашка из кода (holiday_notice).

Пик 31.12–07.01 — по данным комитета по туризму Адыгеи за сезон 2025/26
(РБК Краснодар); очередь у КПП «Лагонаки» 2–3.01.2025 — 93.ru.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from markupsafe import Markup, escape

from sqlalchemy import text

from site_app import seo
from site_app import trip_facts

log = logging.getLogger("adygid.notices")

MSK = ZoneInfo("Europe/Moscow")
QUEUE_SOURCE = {"title": "93.ru, январь 2025", "url": "https://93.ru/text/winter/2025/01/03/74955743/"}

# Какой текст показывать: "a" — три пункта списком, "b" — одним абзацем.
VARIANT = "b"

LAGO = 55
PLAN_B = [24, 67, 62]  # теснина, «АкваТермо», музей природы в Гузерипле
_PLAN_B_NAMES = {24: "Хаджохская теснина", 67: "«АкваТермо» в Тульском", 62: "музей природы в Гузерипле"}


def today_msk(now: Optional[datetime] = None) -> date:
    return (now or datetime.now(MSK)).astimezone(MSK).date()


def in_peak_window(d: date) -> bool:
    return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 8)


def in_planning_window(d: date) -> bool:
    return (d.month == 11 and d.day >= 15) or (d.month == 12 and d.day < 20)


def _facts(pid: int) -> dict:
    """Факты карточки из базы (как на сайте), без записи — из кода."""
    return trip_facts.facts(trip_facts.block_for(pid)) or {}


def _closes(pid: int) -> str:
    f = _facts(pid)
    spec = f.get("closes")
    return f"до {spec}" if spec else ""


def _link(pid: int, text: str, anchor: str = "") -> Markup:
    return Markup('<a href="/mesta/{}{}">{}</a>').format(pid, anchor, text)


def _plan_b() -> list:
    out = []
    for pid in PLAN_B:
        if trip_facts.block_for(pid) is not None:
            out.append((pid, _PLAN_B_NAMES[pid], _closes(pid)))
    return out


def _kpp() -> dict:
    f = _facts(LAGO)
    return {"price": f.get("price"), "cash_only": bool(f.get("cash_only"))}


def tips_a() -> list:
    """Вариант A: три коротких пункта — заголовок-действие и пояснение."""
    kpp = _kpp()
    src = Markup('<a class="trip-src" href="{}" target="_blank" rel="noopener">{}</a>').format(QUEUE_SOURCE["url"], QUEUE_SOURCE["title"])
    road = Markup(
        "Серпантин к Лаго-Наки и подъезд к КПП в каникулы встают в пробку: в январе 2025 машины стояли "
        "так, что люди шли к шлагбауму пешком ({}). Утром глянь пробки в Яндекс Картах и заложи к дороге лишний час."
    ).format(src)
    cash_bits = []
    if kpp["cash_only"]:
        cash_bits.append("На КПП «Лагонаки» карту не примут — только наличные.")
    if kpp["price"]:
        cash_bits.append(f"Вход {kpp['price']} ₽ с человека, дети и пенсионеры — бесплатно, если взять документы.")
    cash = Markup("{} {}").format(" ".join(cash_bits), _link(LAGO, "Тариф и льготы", "#kratko"))
    alts = [Markup("{} ({})").format(_link(pid, name), closes) if closes else _link(pid, name) for pid, name, closes in _plan_b()]
    plan = Markup("Если у подъёма к плато всё стоит — не жди, разворачивайся: {}.").format(Markup(", ").join(alts))
    return [
        {"head": "Проверь дорогу и выезжай с запасом", "html": road},
        {"head": "Возьми наличные на КПП", "html": cash},
        {"head": "Держи запасной план", "html": plan},
    ]


def text_b() -> Markup:
    """Вариант B: одним абзацем, как сообщение от знакомого из Адыгеи."""
    kpp = _kpp()
    alts = _plan_b()
    parts = [Markup(
        "На каникулах в горы едут все сразу, так что пара советов. Перед выездом открой пробки и заложи час "
        "запаса — в январе 2025 к шлагбауму на Лаго-Наки стояла очередь машин ({})."
    ).format(Markup('<a class="trip-src" href="{}" target="_blank" rel="noopener">{}</a>').format(QUEUE_SOURCE["url"], QUEUE_SOURCE["title"]))]
    if kpp["cash_only"] and kpp["price"]:
        parts.append(Markup("Положи в карман наличные: на {} карту не примут, вход {} ₽ с человека, детям и пенсионерам бесплатно.").format(
            _link(LAGO, "КПП «Лагонаки»", "#kratko"), kpp["price"]))
    if alts:
        bits = [Markup("{} — {}").format(_link(pid, name), closes) if closes else _link(pid, name) for pid, name, closes in alts]
        parts.append(Markup("И сразу реши, куда свернёшь, если наверх не пробиться: {}.").format(Markup(", ").join(bits)))
    return Markup(" ").join(parts)


def holiday_notice(today: Optional[date] = None, variant: Optional[str] = None) -> Optional[dict]:
    """Данные плашки для /podbor или None, если сейчас не сезон."""
    d = today or today_msk()
    peak, planning = in_peak_window(d), in_planning_window(d)
    if not (peak or planning):
        return None
    v = variant or VARIANT
    if d.month == 1 or (d.month == 12 and d.day == 31):
        kicker = "Сейчас новогодние каникулы"
    else:
        kicker = "Едете на новогодние каникулы?"
    notice = {"variant": v, "kicker": kicker, "always": peak, "winter_only": planning and not peak}
    if v == "b":
        notice.update(title="Совет от местных", text=text_b())
    else:
        notice.update(title="В праздники в горах людно. Три вещи, которые сберегут день", tips=tips_a())
    return notice


# ───────────────── плашки из базы (site_notices) ─────────────────

MODES = {
    "auto_b": "Автоматический текст одним абзацем (вариант B)",
    "auto_a": "Автоматический текст тремя пунктами (вариант A)",
    "custom": "Свой текст",
}
_COLS = ("id", "slug", "name", "placement", "is_enabled", "priority", "repeat_yearly", "winter_from",
         "show_from", "show_to", "kicker", "kicker_late", "kicker_late_from", "title", "mode", "body",
         "updated_at", "updated_by")
_CACHE: dict = {"rows": None, "at": 0.0}
_CACHE_TTL_S = 30
_LOCK = threading.Lock()


def _load() -> Optional[list]:
    from app.database import engine
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT {', '.join(_COLS)} FROM site_notices ORDER BY priority DESC, id")).all()
    except Exception:
        log.exception("site_notices unavailable — плашка из кода")
        return None
    return [dict(zip(_COLS, r)) for r in rows]


def db_notices() -> Optional[list]:
    now = time.monotonic()
    with _LOCK:
        if _CACHE["at"] and now - _CACHE["at"] < _CACHE_TTL_S:
            return _CACHE["rows"]
    rows = _load()
    with _LOCK:
        _CACHE["rows"], _CACHE["at"] = rows, time.monotonic()
    return rows


def invalidate() -> None:
    with _LOCK:
        _CACHE["at"] = 0.0


def _md(d: date) -> tuple:
    return (d.month, d.day)


def in_range(d: date, start: Optional[date], end: Optional[date], yearly: bool) -> bool:
    """d в [start, end]; при yearly сравниваются только день и месяц (окно может
    переходить через Новый год: 20.12–08.01)."""
    if not start or not end:
        return False
    if not yearly:
        return start <= d <= end
    a, b, x = _md(start), _md(end), _md(d)
    return a <= x <= b if a <= b else (x >= a or x <= b)


def notice_windows(n: dict, d: date) -> tuple:
    """(видна всем, видна только выбравшим зиму)."""
    yearly = bool(n.get("repeat_yearly"))
    if not n.get("show_from") and not n.get("show_to") and not n.get("winter_from"):
        return True, False
    always = in_range(d, n.get("show_from"), n.get("show_to"), yearly)
    winter = False
    if not always and n.get("winter_from") and n.get("show_from"):
        winter = in_range(d, n["winter_from"], n["show_from"] - timedelta(days=1), yearly)
    return always, winter


_PH_RE = re.compile(r"\{(цена|price|закрытие|closes):(\d{1,6})\}")


def fill_placeholders(body: str) -> str:
    """{цена:55} → 500, {закрытие:24} → 17:00 — из проверенных фактов карточки."""
    def sub(m):
        f = _facts(int(m.group(2)))
        if m.group(1) in ("цена", "price"):
            return str(f["price"]) if f.get("price") is not None else "?"
        return f.get("closes") or "?"
    return _PH_RE.sub(sub, body or "")


def auto_body_markdown() -> str:
    """Текст варианта B в разметке админки — заготовка для «Своего текста»."""
    return (
        "На каникулах в горы едут все сразу, так что пара советов. Перед выездом открой пробки и заложи час "
        f"запаса — в январе 2025 к шлагбауму на Лаго-Наки стояла очередь машин ([{QUEUE_SOURCE['title']}]({QUEUE_SOURCE['url']})). "
        f"Положи в карман наличные: на [КПП «Лагонаки»](/mesta/{LAGO}#kratko) карту не примут, вход {{цена:{LAGO}}} ₽ с человека, "
        "детям и пенсионерам бесплатно. И сразу реши, куда свернёшь, если наверх не пробиться: "
        + ", ".join(f"[{_PLAN_B_NAMES[p]}](/mesta/{p}) — до {{закрытие:{p}}}" for p in PLAN_B) + "."
    )


def render_notice(n: dict, d: date, *, force: bool = False) -> Optional[dict]:
    """Данные для шаблона или None. force — для предпросмотра в админке."""
    always, winter = notice_windows(n, d)
    if not force and not (n.get("is_enabled") and (always or winter)):
        return None
    kicker = n.get("kicker") or ""
    late = n.get("kicker_late_from")
    if n.get("kicker_late") and late and in_range(d, late, n.get("show_to") or late, bool(n.get("repeat_yearly"))):
        kicker = n["kicker_late"]
    mode = n.get("mode") or "custom"
    out = {"variant": {"auto_b": "b", "auto_a": "a"}.get(mode, "custom"), "kicker": kicker,
           "always": always or (force and not winter), "winter_only": winter and not always,
           "title": n.get("title") or "", "slug": n.get("slug")}
    if mode == "auto_a":
        out["tips"] = tips_a()
    elif mode == "auto_b":
        out["text"] = text_b()
    else:
        from site_app.site_texts import render_inline
        out["text"] = render_inline(fill_placeholders(n.get("body") or ""))
    return out


def current_notice(placement: str = "podbor", today: Optional[date] = None) -> Optional[dict]:
    """Плашка для страницы: самая приоритетная включённая из базы. Если
    таблица недоступна (миграция не прошла) — прежняя плашка из кода.
    Пустая таблица — значит, все плашки удалили в админке: плашки нет."""
    d = today or today_msk()
    rows = db_notices()
    if rows is None:
        return holiday_notice(d)
    for n in rows:
        if n.get("placement") != placement:
            continue
        out = render_notice(n, d)
        if out:
            return out
    return None


SEED = {
    "slug": "novogodnie-kanikuly", "name": "Новогодние каникулы", "placement": "podbor",
    "is_enabled": True, "priority": 10, "repeat_yearly": True,
    "winter_from": date(2026, 11, 15), "show_from": date(2026, 12, 20), "show_to": date(2027, 1, 8),
    "kicker": "Едете на новогодние каникулы?", "kicker_late": "Сейчас новогодние каникулы",
    "kicker_late_from": date(2026, 12, 31), "title": "Совет от местных", "mode": "auto_b",
}


def seed(conn) -> int:
    """Одна плашка «Новогодние каникулы», как сейчас в коде (вызывается один раз,
    см. site_app/admin_texts_db.py)."""
    vals = dict(SEED, body=auto_body_markdown(), mode="auto_b" if VARIANT == "b" else "auto_a")
    if VARIANT != "b":
        vals["title"] = "В праздники в горах людно. Три вещи, которые сберегут день"
    conn.execute(text(
        "INSERT INTO site_notices (slug, name, placement, is_enabled, priority, repeat_yearly, winter_from, show_from, "
        "show_to, kicker, kicker_late, kicker_late_from, title, mode, body, updated_at, updated_by) VALUES "
        "(:slug, :name, :placement, :is_enabled, :priority, :repeat_yearly, :winter_from, :show_from, :show_to, "
        ":kicker, :kicker_late, :kicker_late_from, :title, :mode, :body, now(), 'перенос из кода') "
        "ON CONFLICT (slug) DO NOTHING"
    ), vals)
    return 1
