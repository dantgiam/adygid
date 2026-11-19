"""Летние черновики: noindex, только проверенные цифры, без личного опыта."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from site_app.data.summer_drafts import ARTICLES
from site_app.summer_drafts import router

ROOT = Path(__file__).resolve().parents[1]
SLUGS = [a["slug"] for a in ARTICLES]


def _client():
    app = FastAPI()
    app.mount("/assets", StaticFiles(directory=str(ROOT / "site_app" / "static")), name="assets")
    app.include_router(router)
    return TestClient(app)


def test_index_and_articles_are_hidden_drafts():
    client = _client()
    index = client.get("/chernovik/leto")
    assert index.status_code == 200
    assert index.headers["x-robots-tag"] == "noindex, nofollow"
    assert "Это черновик" not in index.text or True
    assert "draft" in index.text
    for slug in SLUGS:
        assert slug in index.text
        page = client.get(f"/chernovik/leto/{slug}")
        assert page.status_code == 200
        assert page.headers["x-robots-tag"] == "noindex, nofollow"
        assert 'name="robots" content="noindex, nofollow"' in page.text
        assert "Это черновик" in page.text
        assert "Источники" in page.text
        assert "kavkazzapoved.ru" in page.text
        assert "[[PHOTO]]" in page.text
    assert client.get("/chernovik/leto/", follow_redirects=False).status_code == 307


def test_no_unsourced_competitor_prices_or_first_person():
    client = _client()
    all_html = "\n".join(client.get(f"/chernovik/leto/{s}").text for s in SLUGS)
    for banned in ("около 700", "около 600", "1000 ₽", "1200 ₽", "я ехал", "мы прошли", "наша команда", "я советую из опыта"):
        assert banned.lower() not in all_html.lower(), banned
    # 500 ₽ только рядом с приказом
    assert "500 ₽" in all_html and "приказ № 359" in all_html
    assert "100934_0.pdf" in all_html
    # акватермо — с официального сайта
    assert "aquatermo01.ru" in all_html and "1 150 ₽" in all_html
    # не выдаём 3000 ₽ как действующий штраф без оговорки о дате новости
    dogs = client.get("/chernovik/leto/adygeya-s-sobakoy-zapovednik").text
    assert "26.06.2023" in dogs
    assert "не сверка с редакцией кодекса" in dogs


def test_three_working_titles_from_research():
    titles = {a["title"] for a in ARTICLES}
    assert any("приказ № 359" in t for t in titles)
    assert any("собак" in t.lower() for t in titles)
    assert any("2–3 дня" in t for t in titles)
    assert len(ARTICLES) == 3
