"""Общие практические предупреждения для поездки в Адыгею.

Тексты без конкретных цен, часов кассы и расписания транспорта: эти цифры
быстро устаревают, а часть не сверена с первоисточником. Источники — в
SOURCES. Окна дат — календарные, не прогноз «сегодня будет тихо / нет».
"""
from __future__ import annotations

from datetime import date
from typing import Optional

SOURCES = {
    "queues_jan_2025": {
        "title": "93.ru: очередь к Лаго-Наки 2–3 января 2025",
        "url": "https://93.ru/text/winter/2025/01/03/74955743/",
    },
    "ny_peak_media": {
        "title": "РБК Краснодар и «Вестник Кавказа» со ссылкой на комитет по туризму Адыгеи: пик загрузки 31.12–07.01 в сезон 2025/26",
        "url": "https://kuban.rbc.ru/krasnodar/freenews/698f43369a794746e6bbf798",
        "also": "https://vestikavkaza.ru/news/godovoj-turpotok-v-adygeu-vpervye-prevysil-1-mln-celovek.html",
        "note": "Цифры турпотока (156 тыс., загрузка 85%) в тексты сайта не ставим: первичный отчёт комитета не читали.",
    },
}

# 31.12–07.01 — пик, о котором писали СМИ со ссылкой на комитет.
# 20.12–30.12 — приближение каникул; 08.01 ещё часто продолжают ездить.
# 1–11 мая — широкое окно майских праздников, без утверждения официальных выходных конкретного года.
NY_CORE = (12, 31), (1, 8)
NY_APPROACH_FROM = (12, 20)
MAY_RANGE = (5, 1), (5, 11)

HOLIDAY_TEXT = (
    "В новогодние каникулы (31 декабря – 7 января) и в другие длинные выходные, "
    "включая майские, популярные места и дорога на плато часто бывают загружены. "
    "2–3 января 2025 к Лаго-Наки уже собиралась очередь из машин, часть людей "
    "шла вдоль дороги пешком. Если едете в такие дни, закладывайте больше времени "
    "и запасной план. Это общее предупреждение, а не прогноз на конкретную дату."
)

CASH_TEXT = (
    "На части касс в горной Адыгее просят наличные, а связь у окна бывает слабой. "
    "Имеет смысл везти запас наличных и не рассчитывать только на карту. "
    "Способ оплаты конкретного объекта уточняйте перед поездкой: здесь нет общего "
    "подтверждённого прайса."
)

NO_CAR_LAGO_TEXT = (
    "Добраться до самого плато Лаго-Наки без машины обычно трудно: общественного "
    "рейса «до шлагбаума» в надёжном расписании мы здесь не публикуем — оно быстро "
    "меняется. Без своего транспорта чаще рассчитывают на экскурсию, такси или попутку."
)

PLATEAU_TEXT = (
    "Дорога и часть смотровых до КПП «Лагонаки» и зона за шлагбаумом — не одно и то же. "
    "За КПП действуют правила и плата Кавказского заповедника. Не ждите «плато целиком» "
    "сразу за первой площадкой у дороги. Актуальный тариф на этой странице специально "
    "не указываем: его нужно сверять с официальным прайсом заповедника перед публикацией."
)

GENERIC_TIPS = [
    {"key": "crowd", "title": "Праздники и очереди", "text": HOLIDAY_TEXT,
     "source_key": "queues_jan_2025"},
    {"key": "cash", "title": "Наличные и кассы", "text": CASH_TEXT, "source_key": None},
    {"key": "plateau", "title": "Где начинается плато", "text": PLATEAU_TEXT, "source_key": None},
    {"key": "no_car", "title": "Без машины на Лаго-Наки", "text": NO_CAR_LAGO_TEXT, "source_key": None},
]


def in_new_year_core(d: date) -> bool:
    return (d.month == 12 and d.day >= 31) or (d.month == 1 and d.day <= 8)


def in_new_year_approach(d: date) -> bool:
    return d.month == 12 and NY_APPROACH_FROM[1] <= d.day <= 30


def in_may_window(d: date) -> bool:
    return d.month == 5 and MAY_RANGE[0][1] <= d.day <= MAY_RANGE[1][1]


def in_holiday_window(d: date) -> bool:
    return in_new_year_core(d) or in_new_year_approach(d) or in_may_window(d)


def should_show_holiday_notice(today: date, season: Optional[str] = None) -> bool:
    """Показываем плашку, если выбран зимний сезон в подборщике или сегодня
    попадаем в календарное окно каникул / майских / подхода к ним."""
    if season == "winter":
        return True
    return in_holiday_window(today)


def holiday_notice(today: Optional[date] = None, season: Optional[str] = None) -> Optional[dict]:
    today = today or date.today()
    if not should_show_holiday_notice(today, season):
        return None
    if in_new_year_core(today):
        kicker = "Сейчас новогодние каникулы"
    elif in_new_year_approach(today):
        kicker = "Скоро новогодние каникулы"
    elif in_may_window(today):
        kicker = "Майские праздники"
    else:
        kicker = "Праздники и выходные"
    return {
        "kicker": kicker,
        "title": "В пиковые дни на популярных местах бывает тесно",
        "text": HOLIDAY_TEXT,
        "source": SOURCES["queues_jan_2025"],
    }
