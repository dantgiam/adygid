"""Скрытая страница /v: noindex, вымышленный каталог, живой прогон в браузере.

База не нужна. Проверяется сам маршрут и то, что обработчики каталога
исполняются, а не только лежат строкой в файле.
"""
import json
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from PIL import Image

from site_app.vpechatleniya import router

ROOT = Path(__file__).resolve().parents[1]
PHOTOS = ROOT / "site_app" / "static" / "vpechatleniya" / "photos"


def _client():
    app = FastAPI()
    app.mount("/assets", StaticFiles(directory=str(ROOT / "site_app" / "static")), name="assets")
    app.include_router(router)
    return TestClient(app)


def test_credits_match_decoded_photos():
    doc = json.loads((ROOT / "site_app" / "data" / "vpechatleniya_credits.json").read_text(encoding="utf-8"))
    photos = doc["photos"]
    assert len(photos) == 39
    assert len({p["key"] for p in photos}) == 39
    files = sorted(p.name for p in PHOTOS.glob("*.webp"))
    assert files == sorted(p["file"] for p in photos)
    seen = set()
    for photo in photos:
        path = PHOTOS / photo["file"]
        with Image.open(path) as im:
            im.load()
            assert im.format == "WEBP"
            assert im.size[0] >= 320 and im.size[1] >= 200
        digest = path.read_bytes()
        assert digest[:4] == b"RIFF" and digest[8:12] == b"WEBP"
        seen.add(digest)
        assert photo["page"].startswith("https://commons.wikimedia.org/wiki/File:")
        assert photo["author"]
        assert photo["license"]
        if photo["credit_required"]:
            assert photo["license_url"].startswith("http")
            assert photo["source_in_supplied_doc"] or photo["source_note"]
        if not photo["license_url"]:
            assert photo["license"] == "Public domain"
            assert photo["author_note"]
    assert len(seen) == 39
    ferrata = next(p for p in photos if p["key"] == "ferrata")
    assert ferrata["source_in_supplied_doc"] is False
    assert "Ethan Zook" in ferrata["source_note"]
    assert ferrata["license"] == "CC BY-SA 4.0"
    snow = next(p for p in photos if p["key"] == "snowmobile")
    assert snow["author_incomplete"] is True
    assert "не восстанавливалось" in snow["author_note"]


def test_page_is_noindex_demo_and_serves_distinct_photos():
    client = _client()
    page = client.get("/v")
    assert page.status_code == 200
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    html = page.text
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert "<title>Впечатления АдыГида</title>" in html
    assert 'id="demo-disclaimer"' in html
    assert "предложения вымышлены" in html
    assert "цены ориентировочные" in html
    assert "не снимки партнёров" in html
    assert "заявки не отправляются" in html
    assert "<form" not in html.lower()
    assert "mc.yandex" not in html
    assert "/assets/vpechatleniya/v.js?v=" in html
    assert "/assets/vpechatleniya/v.css?v=" in html
    assert "Ethan Zook" in html
    assert client.get("/v/").status_code == 200
    assert client.post("/v").status_code == 405
    raft = client.get("/assets/vpechatleniya/photos/raft.webp")
    bike = client.get("/assets/vpechatleniya/photos/bike.webp")
    assert raft.status_code == 200 and raft.headers["content-type"].startswith("image/webp")
    assert bike.status_code == 200
    assert raft.content != bike.content
    js = (ROOT / "site_app" / "static" / "vpechatleniya" / "v.js").read_text(encoding="utf-8")
    assert js.count("const OFFERS") == 1
    assert "var OFFERS" not in js
    assert "fetch(" not in js and "XMLHttpRequest" not in js and "sendBeacon" not in js
    assert "data:image" not in js
    assert "Точечное обновление" not in js
    assert "Что изменено" not in js
    assert "V7" not in js and "V6" not in js


def test_hidden_from_navigation_sitemap_and_robots_disallow():
    router_src = (ROOT / "site_app" / "router.py").read_text(encoding="utf-8")
    robots = router_src[router_src.index("def robots_txt"):router_src.index("def _yandex_verification_page")]
    assert "Allow: /" in robots
    assert "Disallow: /v" not in robots
    sitemap = router_src[router_src.index("def sitemap_xml"):]
    assert '"/v"' not in sitemap and "'/v'" not in sitemap
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'path in ("/v", "/v/") or path.startswith("/assets/vpechatleniya/")' in main
    for path in (ROOT / "site_app" / "templates").rglob("*.html"):
        if path.name == "vpechatleniya.html":
            continue
        text = path.read_text(encoding="utf-8")
        assert 'href="/v"' not in text and 'href="/v/"' not in text, path.name
    for path in (ROOT / "app" / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert 'href="/v"' not in text and 'href="/v/"' not in text, path.name


def test_browser_executes_catalog_interactions():
    proc = subprocess.run(
        ["node", "tests/vpechatleniya_browser.cjs"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stdout[-4000:] + "\n" + proc.stderr[-4000:])
    report = json.loads(proc.stdout)
    assert report["ok"] is True
    assert report["initial"]["cards"] == 12
    assert report["images"]["cards"] == 92
    assert report["images"]["photos"] == 39
    for name in ("v_desktop_catalog", "v_desktop_detail_money", "v_request_not_sent", "v_mobile_catalog", "v_mobile_categories"):
        matches = [s for s in report["shots"] if s.endswith(name + ".png")]
        assert len(matches) == 1, report["shots"]
        assert Path(matches[0]).stat().st_size > 10000
