"""Плашка «Новогодние каникулы» в подборе: окна по Москве, три совета,
цена и наличные — из тех же фактов, что и на карточке Лаго-Наки."""
import re
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from site_app import seo, travel_notices as tn


@pytest.fixture()
def client():
    return TestClient(app)


def _plain(m) -> str:
    return re.sub(r"<[^>]+>", "", str(m))


def test_windows_are_moscow_dates():
    # 19.12 21:30 UTC — в Москве уже 20.12, пиковое окно
    assert tn.today_msk(datetime(2026, 12, 19, 21, 30, tzinfo=timezone.utc)) == date(2026, 12, 20)
    assert tn.in_peak_window(date(2026, 12, 20)) and tn.in_peak_window(date(2027, 1, 8))
    assert not tn.in_peak_window(date(2027, 1, 9))
    assert tn.in_planning_window(date(2026, 11, 19)) and not tn.in_planning_window(date(2026, 11, 14))
    assert tn.holiday_notice(date(2026, 10, 1)) is None and tn.holiday_notice(date(2027, 2, 1)) is None


def test_planning_window_shows_only_for_winter_and_peak_for_everyone():
    n = tn.holiday_notice(date(2026, 11, 19))
    assert n["winter_only"] and not n["always"] and n["kicker"] == "Едете на новогодние каникулы?"
    p = tn.holiday_notice(date(2027, 1, 2))
    assert p["always"] and not p["winter_only"] and p["kicker"] == "Сейчас новогодние каникулы"


@pytest.mark.parametrize("variant", ["a", "b"])
def test_both_variants_carry_three_tips_from_card_facts(variant):
    n = tn.holiday_notice(date(2026, 12, 25), variant=variant)
    blob = " ".join(_plain(t["head"]) + " " + _plain(t["html"]) for t in n["tips"]) if variant == "a" else _plain(n["text"])
    f = seo.place_facts(55)
    assert f"{f['price']} ₽" in blob and "наличные" in blob
    assert "пробк" in blob and "час" in blob
    for pid in tn.PLAN_B:
        assert seo.place_facts(pid)["closes"] in blob
    # без обещаний и канцелярита
    for bad in ("до 9:00", "до 9 утра", "будет свободно", "не является прогнозом", "общее предупреждение", "официально не"):
        assert bad not in blob.lower(), bad
    html = str(n["tips"][1]["html"]) if variant == "a" else str(n["text"])
    assert '/mesta/55#kratko' in html


def test_podbor_renders_notice_hidden_until_winter(client, monkeypatch):
    monkeypatch.setattr(tn, "today_msk", lambda now=None: date(2026, 11, 19))
    html = client.get("/podbor").text
    m = re.search(r'<aside class="trip-notice[^"]*" id="trip-notice"([^>]*)>', html)
    assert m and 'data-winter-only="1"' in m.group(1) and "hidden" in m.group(1)
    assert "Совет от местных" in html and "наличные" in html
    monkeypatch.setattr(tn, "today_msk", lambda now=None: date(2027, 1, 3))
    m = re.search(r'<aside class="trip-notice[^"]*" id="trip-notice"([^>]*)>', client.get("/podbor").text)
    assert m and 'data-always="1"' in m.group(1) and "hidden" not in m.group(1)
    monkeypatch.setattr(tn, "today_msk", lambda now=None: date(2027, 3, 1))
    assert 'id="trip-notice"' not in client.get("/podbor").text
