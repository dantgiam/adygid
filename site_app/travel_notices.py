"""Плашка «Новогодние каникулы» в подборе.

Совет как от знакомого местного: три действия, без прогнозов «до 9:00
будет свободно». Цена и способ оплаты на КПП, часы запасных мест берутся
из тех же проверенных фактов, что и «Коротко для поездки» на карточках
(seo.PLACE_PRACTICAL[...]["facts"]), — поменяли там, поменялось и здесь.

Окна дат считаются по Москве:
- 20.12–08.01 — плашка видна всем;
- 15.11–19.12 — только тем, кто выбрал в подборе «зима» (планируют каникулы).
Пик 31.12–07.01 — по данным комитета по туризму Адыгеи за сезон 2025/26
(РБК Краснодар); очередь у КПП «Лагонаки» 2–3.01.2025 — 93.ru.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from markupsafe import Markup, escape

from site_app import seo

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


def _closes(pid: int) -> str:
    f = seo.place_facts(pid) or {}
    spec = f.get("closes")
    return f"до {spec}" if spec else ""


def _link(pid: int, text: str, anchor: str = "") -> Markup:
    return Markup('<a href="/mesta/{}{}">{}</a>').format(pid, anchor, text)


def _plan_b() -> list:
    out = []
    for pid in PLAN_B:
        if pid in seo.PLACE_PRACTICAL:
            out.append((pid, _PLAN_B_NAMES[pid], _closes(pid)))
    return out


def _kpp() -> dict:
    f = seo.place_facts(LAGO) or {}
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
