"""Блок отзыва на месте, маршруте и статье — после «Понравилось?», перед клубом — и плашка cookie.

Данные маршрута 11 и места 50 не меняются: тест только читает их, если они есть.
Страницу /privacy не создаём — в подвале пока только ссылка.
"""
import os
import re
import uuid
from html import unescape
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from site_app.router import review_bot_url, review_token

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])
ROOT = Path(__file__).resolve().parents[1]
BOT = "https://max.ru/se15002131_bot?start="
REVIEW_COPY = "Поделитесь впечатлениями или свежей информацией — это поможет другим путешественникам"
COOKIE_COPY = "Мы используем cookie и Яндекс Метрику, чтобы сайт становился удобнее."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _h1(html: str) -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.S)
    assert match, "на странице нет h1"
    text = re.sub(r"<[^>]+>", "", match.group(1))
    return unescape(text).strip()


def _review(html: str) -> str:
    start = html.find('class="section review-cta-section"')
    assert start != -1, "блока отзыва нет"
    end = html.find("</section>", start)
    return html[start:end]


def test_review_token_keeps_url_safe_slice():
    assert review_token(54) == "54"
    assert review_token("kak-doehat") == "kak-doehat"
    assert review_token("A b/c_д!") == "Abc"
    assert review_token(None) == ""
    assert len(review_token("a" * 100)) == 80
    assert review_bot_url("m", 54) == BOT + "rv_m54"
    assert review_bot_url("r", 11) == BOT + "rv_r11"
    assert review_bot_url("s", "my-slug") == BOT + "rv_smy-slug"
    assert review_bot_url("x", "1") == BOT + "rv_1"


def test_review_block_on_place_route_and_article_only(client):
    mark = uuid.uuid4().hex[:8]
    place = client.post("/api/checkpoints", json={
        "name": f"Отзыв место {mark}", "lon": 40.11, "lat": 44.11, "description": "Описание места для отзыва.",
    }, auth=AUTH)
    route = client.post("/api/trails", json={"name": f"Отзыв маршрут {mark}", "description": "Описание маршрута."}, auth=AUTH)
    article = client.post("/api/articles", json={
        "title": f"Отзыв статья {mark}",
        "slug": f"otzyv-{mark}",
        "body": "<p>Текст статьи.</p>",
    }, auth=AUTH)
    assert place.status_code == 201, place.text
    assert route.status_code == 201, route.text
    assert article.status_code == 201, article.text
    place_id = place.json()["id"]
    route_id = route.json()["id"]
    slug = article.json()["slug"]
    try:
        pages = {
            "place": client.get(f"/mesta/{place_id}"),
            "route": client.get(f"/marshruty/{route_id}"),
            "article": client.get(f"/stati/{slug}"),
        }
        expected = {
            "place": ("m", str(place_id), f"Отзыв место {mark}"),
            "route": ("r", str(route_id), f"Отзыв маршрут {mark}"),
            "article": ("s", slug, f"Отзыв статья {mark}"),
        }
        for kind, response in pages.items():
            assert response.status_code == 200, response.text
            html = response.text
            letter, token, title = expected[kind]
            assert _h1(html) == title
            assert "Уже бывали тут?" not in _h1(html)
            block = _review(html)
            assert "Уже бывали тут?" in block
            assert REVIEW_COPY in block
            assert "Оставить отзыв в MAX" in block
            assert f'href="{BOT}rv_{letter}{token}"' in block
            assert 'target="_blank"' in block
            assert f'data-page-type="{kind}"' in block
            assert f'data-page-id="{token}"' in block
            assert html.count("review-cta-section") == 1
            review_at = html.find("review-cta-section")
            club_at = html.find("club-cta-section")
            assert html.find("<h1") < review_at < club_at < html.find("</main>") < html.find("<footer")
            assert html.find('id="review-cta-title"') > html.find("</h1>")
            # Клуб и всё, что шло за ним (маршруты, похожие), остаётся ниже отзыва.
            assert html.rfind("review-cta-section") < club_at
            if kind != "article":
                like_at = html.find('class="like-row"')
                assert 0 <= like_at < review_at
                assert "Понравилось" in html[like_at:review_at]

        for path in ("/", "/mesta", "/marshruty", "/stati", "/podbor", "/klub"):
            page = client.get(path)
            assert page.status_code == 200, path
            assert "review-cta-section" not in page.text, path
            assert "Уже бывали тут?" not in page.text, path
    finally:
        client.delete(f"/api/checkpoints/{place_id}", auth=AUTH)
        client.delete(f"/api/trails/{route_id}", auth=AUTH)
        client.delete(f"/api/articles/{article.json()['id']}", auth=AUTH)


def test_place_50_and_route_11_are_only_read(client):
    """Страницы, если они есть, получают блок отзыва, но имена остаются из базы."""
    place = client.get("/api/checkpoints/50")
    if place.status_code == 200:
        page = client.get("/mesta/50")
        if page.status_code == 200:
            assert _h1(page.text) == place.json()["name"]
            assert 'start=rv_m50' in page.text
        again = client.get("/api/checkpoints/50")
        assert again.json()["name"] == place.json()["name"]
        assert again.json().get("description") == place.json().get("description")

    route = client.get("/api/trails/11")
    if route.status_code == 200:
        page = client.get("/marshruty/11")
        if page.status_code == 200:
            assert _h1(page.text) == route.json()["name"]
            assert "start=rv_r11" in page.text
        again = client.get("/api/trails/11")
        assert again.json()["name"] == route.json()["name"]
        assert again.json().get("description") == route.json().get("description")


def test_cookie_banner_is_on_the_public_site_and_not_in_admin(client):
    home = client.get("/")
    assert home.status_code == 200
    assert re.search(r'<div id="cookie-banner" class="cookie-banner" hidden\b', home.text)
    assert COOKIE_COPY in home.text
    assert '<a href="/privacy">политике конфиденциальности</a>' in home.text
    assert ">Принять</button>" in home.text
    assert ">Только необходимые</button>" in home.text
    assert 'href="/privacy">Политика конфиденциальности' in home.text
    assert 'id="cookie-settings">Настройки cookie' in home.text
    assert "metrika/tag.js" not in home.text
    assert "mc.yandex.ru/watch" not in home.text

    base = (ROOT / "site_app" / "templates" / "base.html").read_text(encoding="utf-8")
    js = (ROOT / "site_app" / "static" / "site.js").read_text(encoding="utf-8")
    assert "metrika/tag.js" not in base
    assert "mc.yandex.ru/watch" not in base
    assert "reachGoal" not in base
    assert "ADYGID_METRIKA_ID" in base
    assert "review_click" in js
    assert "adygid_cookie_consent" in js
    assert 'consent !== "accepted"' in js
    assert "queue.push" in js
    assert "https://mc.yandex.ru/metrika/tag.js?id=" in js
    assert 'ym(id, "reachGoal"' in js

    admin = client.get("/admin", auth=AUTH)
    assert admin.status_code == 200
    assert "cookie-banner" not in admin.text
    assert "Настройки cookie" not in admin.text
    assert "Уже бывали тут?" not in admin.text
    for relative in (
        "static/admin.html",
        "app/templates/bot_base.html",
        "app/templates/bot_inbox.html",
        "app/templates/bot_inbox_detail.html",
        "app/templates/bot_templates.html",
        "app/templates/bot_problem.html",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "cookie-banner" not in text, relative
        assert "Настройки cookie" not in text, relative
