"""Скрытые страницы /dom: макет таблички, без базы и без выдуманного дома."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from pathlib import Path

from site_app.dom import REV, bot_links, router
from site_app.data import dom_houses

ROOT = Path(__file__).resolve().parents[1]


def _client():
    app = FastAPI()
    app.mount("/assets", StaticFiles(directory=str(ROOT / "site_app" / "static")), name="assets")
    app.include_router(router)
    return TestClient(app)


def test_index_lists_both_variants_and_is_hidden_from_index():
    page = _client().get("/dom")
    assert page.status_code == 200
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert 'name="robots" content="noindex, nofollow"' in page.text
    assert "/dom/demo" in page.text
    assert "/dom/demo-zhurnal" in page.text
    assert "Рекомендую для пилота" in page.text
    assert "Грозненская тишь" not in page.text
    assert f"dom.css?v={REV}" in page.text


def test_index_slash_redirects():
    page = _client().get("/dom/", follow_redirects=False)
    assert page.status_code == 307
    assert page.headers["location"] == "/dom"


def test_plate_demo_is_a_marked_mock_not_a_real_house():
    page = _client().get("/dom/demo")
    assert page.status_code == 200
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert "dom--plate" in page.text
    assert "Демо-домик" in page.text
    assert "Макет" in page.text
    assert "не карточка настоящего объекта" in page.text
    assert "Пример правил, не правила конкретного дома" in page.text
    assert "выдумывать доступ незачем" in page.text
    assert "Грозненская тишь" not in page.text
    assert "password" not in page.text.lower() or "пароль появятся" in page.text.lower()
    # Учебный текст не должен притворяться адресом или координатами.
    assert "хутор Грозный" not in page.text
    assert "44." not in page.text


def test_house_slash_redirects_and_unknown_codes_404():
    client = _client()
    ok = client.get("/dom/demo/", follow_redirects=False)
    assert ok.status_code == 307
    assert ok.headers["location"] == "/dom/demo"
    assert client.get("/dom/net-takogo-doma").status_code == 404
    assert client.get("/dom/DEMO").status_code == 404
    assert client.get("/dom/demo_house").status_code == 404


def test_journal_variant_shares_copy_and_uses_other_layout():
    page = _client().get("/dom/demo-zhurnal")
    assert page.status_code == 200
    assert "dom--journal" in page.text
    assert "dom--plate" not in page.text
    assert "Демо-домик" in page.text
    assert "Пример правил, не правила конкретного дома" in page.text


def test_contact_goes_only_through_adygid_bots():
    plate = _client().get("/dom/demo")
    links = bot_links("demo")
    assert links["telegram"] in plate.text
    assert links["max"] in plate.text
    assert links["telegram"].endswith("?start=dom_demo")
    assert links["max"].endswith("?start=dom_demo")
    assert "t.me/adygid_bot" in plate.text
    assert "max.ru/se15002131_bot" in plate.text
    assert "tel:112" in plate.text
    # Прямого телефона хозяина в макете быть не должно.
    assert "tel:+" not in plate.text


def test_nearby_links_point_to_existing_catalog_urls():
    page = _client().get("/dom/demo")
    assert 'href="/mesta/24"' in page.text
    assert 'href="/mesta/52"' in page.text
    assert 'href="/podbor"' in page.text
    assert "не список «рядом с домом»" in page.text
    titles = {item["title"] for item in dom_houses.CATALOG_EXAMPLES}
    assert titles == {"Хаджохская теснина", "Гранитный каньон", "Подобрать поездку"}


def test_css_and_messenger_icons_are_served():
    client = _client()
    css = client.get(f"/assets/dom.css?v={REV}")
    assert css.status_code == 200
    assert ".dom--plate" in css.text and ".dom--journal" in css.text
    assert client.get("/assets/magnet-tg.png").status_code == 200
    assert client.get("/assets/magnet-max.png").status_code == 200
