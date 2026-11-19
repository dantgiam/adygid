"""Предупреждения о праздниках: логика окон, тексты без выдуманных цен."""
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from site_app.notices_preview import router
from site_app.travel_notices import (
    HOLIDAY_TEXT,
    should_show_holiday_notice,
    holiday_notice,
    in_holiday_window,
    in_may_window,
    in_new_year_core,
)

ROOT = Path(__file__).resolve().parents[1]


def test_windows_cover_ny_and_may_but_not_ordinary_november():
    assert in_new_year_core(date(2026, 12, 31))
    assert in_new_year_core(date(2027, 1, 7))
    assert in_holiday_window(date(2026, 12, 20))
    assert in_may_window(date(2027, 5, 1)) and in_may_window(date(2027, 5, 9))
    assert not in_holiday_window(date(2026, 11, 19))
    assert not in_may_window(date(2027, 5, 20))


def test_winter_season_shows_notice_even_outside_the_window():
    today = date(2026, 11, 19)
    assert not should_show_holiday_notice(today, season=None)
    assert not should_show_holiday_notice(today, season="summer")
    assert should_show_holiday_notice(today, season="winter")
    notice = holiday_notice(today, season="winter")
    assert notice and "31 декабря" in notice["text"]
    assert "93.ru" in notice["source"]["url"]
    assert notice["kicker"] == "Праздники и выходные"


def test_kicker_changes_inside_calendar_windows():
    assert holiday_notice(date(2026, 12, 25), season=None)["kicker"] == "Скоро новогодние каникулы"
    assert holiday_notice(date(2027, 1, 2), season=None)["kicker"] == "Сейчас новогодние каникулы"
    assert holiday_notice(date(2027, 5, 3), season=None)["kicker"] == "Майские праздники"


def test_copy_has_no_unverified_prices_or_invented_stats():
    assert "500" not in HOLIDAY_TEXT
    assert "156" not in HOLIDAY_TEXT
    assert "85%" not in HOLIDAY_TEXT
    assert "700" not in HOLIDAY_TEXT


def _client():
    app = FastAPI()
    app.mount("/assets", StaticFiles(directory=str(ROOT / "site_app" / "static")), name="assets")
    app.include_router(router)
    return TestClient(app)


def test_preview_is_hidden_and_shows_three_variants():
    page = _client().get("/chernovik/preduprezhdeniya")
    assert page.status_code == 200
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert 'name="robots" content="noindex, nofollow"' in page.text
    assert "trip-notice--plaque" in page.text
    assert "trip-notice--checklist" in page.text
    assert "trip-notice--editorial" in page.text
    assert "Рекомендую для подбора" in page.text
    assert "93.ru" in page.text
    # В плашках (то, что уйдёт в подбор) цифр турпотока и цен нет.
    # В блоке источников черновика можно явно сказать, почему их не ставим.
    plaque = page.text.split('id="var-a"')[1].split('id="var-b"')[0]
    assert "156 тыс" not in plaque and "500 ₽" not in plaque
    assert "не ставим" in page.text
    r = _client().get("/chernovik/preduprezhdeniya/", follow_redirects=False)
    assert r.status_code == 307


def test_lago_card_gains_sourced_crowd_field_without_new_prices():
    from site_app import seo
    keys = {k for k, _ in seo.PRACTICAL_LABELS}
    assert {"cash", "crowd", "without_car"} <= keys
    lago = seo.PLACE_PRACTICAL[55]
    assert "93.ru" in lago["crowd"]["source"]
    assert "2–3 января 2025" in lago["crowd"]["text"]
    assert "без машины обычно трудно" in lago["without_car"]
    # Новый блок не добавляет несверенную цену сверх уже существующей оговорки в tickets.
    assert "500" not in lago["crowd"]["text"]
    assert "500" not in lago["without_car"]
    assert "500" not in lago["cash"]


def test_podbor_wires_the_recommended_plaque():
    js = (ROOT / "site_app/static/podbor.js").read_text(encoding="utf-8")
    html = (ROOT / "site_app/templates/podbor.html").read_text(encoding="utf-8")
    assert "syncHolidayNotice" in js
    assert "trip-notice--plaque" in js
    assert 'id="trip-notice-slot"' in html
    assert "notices.css" in html
    router = (ROOT / "site_app/router.py").read_text(encoding="utf-8")
    assert '"holiday"' in router or "holiday" in router
