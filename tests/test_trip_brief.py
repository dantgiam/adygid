"""Блок «Коротко для поездки»: только проверенные факты, превью скрыто."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from site_app import seo
from site_app.trip_brief_preview import router

ROOT = Path(__file__).resolve().parents[1]
PUNKTY = "https://www.kavkazzapoved.ru/punkty-vydachi-propuskov"
PRAVILA = "https://www.kavkazzapoved.ru/pravila"
REZHIM = "https://www.kavkazzapoved.ru/rezhim-raboty"
AQUA = "https://aquatermo01.ru/residence/day/"
TESNINA = "https://pokolenie.adygheya.gov.ru/tourism/khadzhokhskaya-tesnina/"
CABLE = "https://pokolenie.adygheya.gov.ru/tourism/savranskaya-kanatnaya-doroga/"


def _text(val):
    return val["text"] if isinstance(val, dict) else val


def _src(val):
    return val.get("source") if isinstance(val, dict) else None


def test_official_hours_and_cash_for_lago_and_eco():
    lago = seo.PLACE_PRACTICAL[55]
    assert "500 ₽ за посещение (с 15.08.2026, приказ № 359)" in _text(lago["tickets"])
    assert "Дорога и смотровые до КПП — без пропуска." in _text(lago["tickets"])
    assert "05:00–20:00" in _text(lago["hours"]) and _src(lago["hours"]) == PUNKTY
    assert "только наличными" in _text(lago["cash"]) and _src(lago["cash"]) == PUNKTY
    assert "домашних животных" in _text(lago["pets"]) and _src(lago["pets"]) == PRAVILA
    eco = seo.PLACE_PRACTICAL[62]
    assert "10:00–17:00" in _text(eco["hours"]) and _src(eco["hours"]) == REZHIM
    assert "понедельник" not in _text(eco["hours"]).lower()
    assert "понедельник" not in _text(seo.PLACE_PRACTICAL[63]["hours"]).lower()


def test_official_prices_and_portal_hours():
    aqua = seo.PLACE_PRACTICAL[67]
    assert _src(aqua["tickets"]) == AQUA and "1 150 ₽" in _text(aqua["tickets"])
    assert "31.12.2026–08.01.2027" in _text(aqua["tickets"])
    assert _src(aqua["hours"]) == AQUA and "09:00–23:00" in _text(aqua["hours"])
    tesnina = seo.PLACE_PRACTICAL[24]
    assert _src(tesnina["hours"]) == TESNINA and "08:00–18:00" in _text(tesnina["hours"])
    cable = seo.PLACE_PRACTICAL[48]
    assert _src(cable["hours"]) == CABLE and "профилактические" in _text(cable["hours"])
    assert seo.PLACE_PRACTICAL[43]["hours"]["source"].endswith("ekstrim-park-meshoko/")
    assert 56 in seo.PLACE_PRACTICAL and 50 not in seo.PLACE_PRACTICAL
    assert 16 <= len(seo.PLACE_PRACTICAL) <= 20


def test_preview_is_hidden_and_has_three_variants():
    app = FastAPI()
    app.mount("/assets", StaticFiles(directory=str(ROOT / "site_app" / "static")), name="assets")
    app.include_router(router)
    client = TestClient(app)
    a = client.get("/chernovik/korotko-dlya-poezdki")
    b = client.get("/chernovik/korotko-dlya-poezdki?v=istochniki")
    c = client.get("/chernovik/korotko-dlya-poezdki?v=kartochki")
    for page in (a, b, c):
        assert page.status_code == 200
        assert page.headers["x-robots-tag"] == "noindex, nofollow"
        assert "Лаго-Наки" in page.text
        assert "Каменное море" in page.text
        assert "Яворова поляна" in page.text
        assert "Михайло-Афонская" in page.text
        assert "Старый мост" in page.text
        assert "500 ₽" in page.text
        assert "kavkazzapoved.ru" in page.text
    assert "рекомендую" in a.text
    assert "tb-grid" in c.text
    slash = client.get("/chernovik/korotko-dlya-poezdki/", follow_redirects=False)
    assert slash.status_code == 307


def test_yavorova_bridge_monastery_official_only():
    bridge = seo.PLACE_PRACTICAL[49]
    assert _src(bridge["tickets"]) == "https://pokolenie.adygheya.gov.ru/tourism/dakhovskiy-most/"
    assert "бесплатн" in _text(bridge["tickets"]).lower()
    assert "круглосуточн" in _text(bridge["hours"])
    mon = seo.PLACE_PRACTICAL[30]
    assert "Родниковая, 5" in _text(mon["how"])
    assert "mae-monastery.cerkov.ru" in (_src(mon["how"]) or "")
    assert "прайса" in _text(mon["tickets"]).lower()
    assert "часы работы не указаны" in _text(mon["hours"])
    yav = seo.PLACE_PRACTICAL[64]
    assert "Узуруб" in _text(yav["how"])
    assert _src(yav["how"]).endswith("ruchey-belyy")
    assert "06:00–20:00" in _text(yav["hours"]) and _src(yav["hours"]) == PUNKTY
    assert "только наличными" in _text(yav["cash"])
    assert 50 not in seo.PLACE_PRACTICAL
    assert 19 <= len(seo.PLACE_PRACTICAL) <= 20
