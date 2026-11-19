"""Черновик хаба входных: noindex, без публикации несверенных цен как факта."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from site_app.data.tickets_hub import ROWS, ZAPOVED_DRAFT_FIGURE
from site_app.tickets_hub import router

ROOT = Path(__file__).resolve().parents[1]


def _client():
    app = FastAPI()
    app.mount("/assets", StaticFiles(directory=str(ROOT / "site_app" / "static")), name="assets")
    app.include_router(router)
    return TestClient(app)


def test_both_variants_are_hidden_drafts():
    client = _client()
    table = client.get("/chernovik/vhodnye-2026")
    articles = client.get("/chernovik/vhodnye-2026?v=statyi")
    for page in (table, articles):
        assert page.status_code == 200
        assert page.headers["x-robots-tag"] == "noindex, nofollow"
        assert 'name="robots" content="noindex, nofollow"' in page.text
        assert "Это черновик" in page.text
        assert "Сверить перед публикацией" in page.text
        assert "kavkazzapoved.ru" in page.text
        assert "93.ru" in page.text
    assert "th-table" in table.text
    assert "th-article" in articles.text
    assert "рекомендую" in table.text
    slash = client.get("/chernovik/vhodnye-2026/", follow_redirects=False)
    assert slash.status_code == 307


def test_500_rub_is_only_inside_the_verification_box():
    html = _client().get("/chernovik/vhodnye-2026").text
    # Цифра есть только как пометка «сверить», не как готовый прайс в заголовке.
    assert "500 ₽" in html
    assert "Сверить перед публикацией" in html
    lead = html.split("Это черновик")[0]
    assert "500 ₽" not in lead
    assert ZAPOVED_DRAFT_FIGURE in html or "приказ № 359" in html
    # Чужие ориентиры теснины / Руфабго / пещеры в хаб не копируем.
    assert "700 ₽" not in html
    assert "600 ₽" not in html
    assert "1000 ₽" not in html
    assert "1200 ₽" not in html


def test_rows_cover_main_objects_and_keep_statuses():
    ids = [r["id"] for r in ROWS]
    assert ids == ["zapoved", "tesnina", "rufabgo", "azish", "cable", "cash", "holidays"]
    assert ROWS[0]["status"] == "draft_price" and ROWS[0]["draft_figure"]
    assert all(r["draft_figure"] is None for r in ROWS[1:])
