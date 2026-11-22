"""Страница домика /dom/demo: noindex, учебный дом, боты, фото и время в пути.

База для самой страницы не нужна. Если каталог недоступен, блоки «рядом»
и «маршруты» остаются пустыми, а остальная страница открывается.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from PIL import Image

from site_app.data import dom_houses
from site_app.dom import REV, bot_links, router
from site_app.dom_drive import drive_minutes, rank_by_drive

ROOT = Path(__file__).resolve().parents[1]
PHOTOS = ROOT / "site_app" / "static" / "dom" / "demo"
EMPTY = {"ok": False, "places": [], "routes": [], "categories": []}


def _client():
    app = FastAPI()
    app.mount("/assets", StaticFiles(directory=str(ROOT / "site_app" / "static")), name="assets")
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def quiet_catalog(monkeypatch):
    """Текст страницы не должен зависеть от того, что лежит в тестовой базе."""
    monkeypatch.setattr("site_app.dom.load_catalog", lambda *_a, **_k: EMPTY)


def test_index_points_at_demo_and_is_hidden(quiet_catalog):
    page = _client().get("/dom")
    assert page.status_code == 200
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert 'name="robots" content="noindex, nofollow"' in page.text
    assert "/dom/demo" in page.text
    assert "А-фрейм у леса (демо)" in page.text
    assert "глэмпинг" not in page.text.lower()
    assert f"dom.css?v={REV}" in page.text


def test_slashes_redirect_and_unknown_codes_are_missing():
    client = _client()
    index = client.get("/dom/", follow_redirects=False)
    assert index.status_code == 307 and index.headers["location"] == "/dom"
    house = client.get("/dom/demo/", follow_redirects=False)
    assert house.status_code == 307 and house.headers["location"] == "/dom/demo"
    assert client.get("/dom/net-takogo").status_code == 404
    assert client.get("/dom/DEMO").status_code == 404
    assert client.get("/dom/demo_house").status_code == 404
    assert client.get("/dom/demo-zhurnal").status_code == 404


def test_demo_page_is_marked_and_not_a_real_listing(quiet_catalog):
    page = _client().get("/dom/demo")
    assert page.status_code == 200
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    html = page.text
    assert 'name="robots" content="noindex, nofollow"' in html
    assert "А-фрейм у леса (демо)" in html
    assert "Демо-страница" in html
    assert "не карточка настоящего объекта" in html
    assert "Демо-фото, сгенерированы для примера. На странице партнёра будут его настоящие фото." in html
    assert html.count("Демо-фото, сгенерированы для примера.") >= 2
    assert "Пример заполнения" in html
    assert "От хозяина" in html
    assert "по запросу (пример)" in html
    assert "заглушка" in html
    assert "Aframe-demo" in html and "les-demo" in html
    assert "район хутора Грозный" in html
    assert "44.6412" not in html and "40.2018" not in html
    assert "глэмпинг" not in html.lower()
    assert "Грозненская" not in html
    for anchor in ("host", "house", "services", "guide", "rules", "faq", "nearby", "routes", "ask"):
        assert f'id="{anchor}"' in html
    assert 'href="/podbor?src=dom"' in html
    assert 'href="/mesta"' in html
    assert 'href="/marshruty"' in html
    assert "<form" not in html.lower()


def test_contact_is_only_the_adygid_bots_and_112(quiet_catalog):
    page = _client().get("/dom/demo")
    links = bot_links("demo")
    assert links["telegram"] in page.text
    assert links["max"] in page.text
    assert links["telegram"].endswith("?start=dom_demo")
    assert links["max"].endswith("?start=dom_demo")
    assert links["host_telegram"].endswith("?start=dom_host")
    assert links["host_max"] in page.text
    assert "t.me/adygid_bot" in page.text
    assert "max.ru/se15002131_bot" in page.text
    assert 'href="tel:112"' in page.text
    assert "tel:+" not in page.text
    assert not re.search(r"\+7[\d\s()-]{8,}", page.text)
    assert "@" not in page.text


def test_house_config_has_no_personal_data_and_a_demo_pin():
    text = (ROOT / "site_app" / "data" / "dom_houses.py").read_text(encoding="utf-8")
    assert not re.search(r"\+7|8\s?\(?\d{3}\)?", text)
    assert "@" not in text
    origin = dom_houses.DEMO_ORIGIN
    assert 44.62 < origin["lat"] < 44.67
    assert 40.17 < origin["lon"] < 40.23
    assert origin["label"].startswith("район хутора Грозный")
    house = dom_houses.get_house("demo")
    assert house["place_limit"] == 8
    assert house["route_limit"] == 4
    assert len(house["gallery"]) == 6
    assert len(house["services"]) == 6
    assert len(house["host"]["paragraphs"]) == 5


def test_demo_photos_are_local_webp_with_alt_and_lazy(quiet_catalog):
    page = _client().get("/dom/demo").text
    files = sorted(p.name for p in PHOTOS.glob("*.webp"))
    assert len(files) == 12
    for name in files:
        path = PHOTOS / name
        assert path.stat().st_size < 260_000
        with Image.open(path) as image:
            image.load()
            assert image.format == "WEBP"
        assert name in page or name.split("-")[0] in page
    assert 'alt="Демо-фото: треугольный деревянный дом' in page
    assert 'loading="eager"' in page and 'fetchpriority="high"' in page
    assert page.count('loading="lazy"') >= 5
    client = _client()
    image = client.get("/assets/dom/demo/exterior-960.webp")
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/webp")
    assert image.content[:4] == b"RIFF"
    css = client.get(f"/assets/dom.css?v={REV}")
    assert css.status_code == 200 and ".dom-title" in css.text
    script = client.get(f"/assets/dom.js?v={REV}")
    assert script.status_code == 200 and "data-dom-filter" in script.text


def test_drive_minutes_match_podbor_core():
    pairs = [
        [44.6412, 40.2018, 44.605, 40.100],
        [44.6412, 40.2018, 44.295, 40.185],
        [44.6412, 40.2018, 44.000, 40.136],
        [44.6412, 40.2018, 44.6413, 40.2020],
        [44.60, 40.10, 44.70, 40.20],
        [44.20, 40.10, 44.30, 40.20],
    ]
    script = (
        "const C=require('./site_app/static/podbor-core.js');"
        "const pairs=JSON.parse(process.argv[1]);"
        "const out=pairs.map(p=>C.driveMin({lat:p[0],lon:p[1]},{lat:p[2],lon:p[3]}));"
        "process.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run(
        ["node", "-e", script, json.dumps(pairs)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    expected = json.loads(proc.stdout)
    assert [drive_minutes(*pair) for pair in pairs] == expected
    assert expected[3] == 0
    core = (ROOT / "site_app/static/podbor-core.js").read_text(encoding="utf-8")
    assert "speedKmh:50" in core and "mountainFactor:1.3" in core
    assert "plainFactor:1.2" in core and "plainLat:44.45" in core and "parkingMin:10" in core


def test_rank_by_drive_sorts_and_drops_unknown():
    rows = [
        {"name": "Б", "drive_min": 30},
        {"name": "А", "drive_min": 15},
        {"name": "нет", "drive_min": None},
        {"name": "В", "drive_min": 15},
    ]
    assert [row["name"] for row in rank_by_drive(rows, 2)] == ["А", "В"]


def test_catalog_cards_render_with_drive_time_and_filter(monkeypatch):
    catalog = {
        "ok": True,
        "categories": ["Водопад", "Музей"],
        "places": [
            {
                "url": "/mesta/tesnina",
                "name": "Тестовая теснина",
                "excerpt": "Коротко о месте",
                "cover_src": "/assets/dom/demo/exterior-960.webp",
                "cover_srcset": "",
                "cover_style": "",
                "popularity": "normal",
                "district_label": "Округ Хаджоха",
                "category": {"name": "Водопад", "icon_svg": "<svg class=\"cat-icon\"></svg>"},
                "category_name": "Водопад",
                "is_paid": None,
                "price_label": "уточняем, скоро появится :)",
                "kid_friendly": True,
                "drive_label": "≈ 25 мин на машине",
                "km_label": "12 км по прямой",
            },
            {
                "url": "/mesta/muzey",
                "name": "Тестовый музей",
                "excerpt": "",
                "cover_src": "",
                "cover_srcset": "",
                "cover_style": "",
                "popularity": "top",
                "district_label": "",
                "category": {"name": "Музей", "icon_svg": ""},
                "category_name": "Музей",
                "is_paid": False,
                "price_label": "Бесплатно",
                "kid_friendly": False,
                "drive_label": "≈ 40 мин на машине",
                "km_label": "22 км по прямой",
            },
        ],
        "routes": [{
            "url": "/marshruty/test-route",
            "name": "Тестовый маршрут",
            "excerpt": "По реке",
            "cover_src": "",
            "cover_srcset": "",
            "cover_style": "",
            "popularity": "top",
            "district_label": "Округ Хаджоха",
            "category": None,
            "category_name": "",
            "difficulty_label": "легко",
            "duration_label": "2 ч",
            "drive_label": "≈ 35 мин на машине",
            "km_label": "16 км по прямой",
        }],
    }
    monkeypatch.setattr("site_app.dom.load_catalog", lambda *_a, **_k: catalog)
    page = _client().get("/dom/demo")
    assert page.status_code == 200
    assert 'href="/mesta/tesnina"' in page.text
    assert "Тестовая теснина" in page.text
    assert "≈ 25 мин на машине" in page.text
    assert "12 км по прямой" in page.text
    assert "Для детей" in page.text
    assert 'data-dom-filter="Водопад"' in page.text
    assert 'href="/marshruty/test-route"' in page.text
    assert "Тестовый маршрут" in page.text
    assert "ТОП" in page.text
    assert "Время в пути приблизительное, по прямой" in page.text


def test_page_renders_when_catalog_database_is_down(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("site_app.dom_nearby.SessionLocal", boom)
    page = _client().get("/dom/demo")
    assert page.status_code == 200
    assert "Каталог мест сейчас недоступен" in page.text
    assert "Маршруты рядом появятся" in page.text
    assert "А-фрейм у леса (демо)" in page.text


def test_dom_stays_out_of_sitemap_robots_and_navigation():
    router_src = (ROOT / "site_app" / "router.py").read_text(encoding="utf-8")
    robots = router_src[router_src.index("def robots_txt"):router_src.index("def _yandex_verification_page")]
    assert "Disallow: /dom" not in robots
    sitemap = router_src[router_src.index("def sitemap_xml"):]
    assert '"/dom' not in sitemap and "'/dom" not in sitemap
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'path in ("/v", "/v/") or path.startswith("/assets/vpechatleniya/")' in main
    assert 'path == "/dom" or path.startswith("/dom/")' in main
    base = (ROOT / "site_app" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'href="/dom"' not in base
