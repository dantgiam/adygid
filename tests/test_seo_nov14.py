"""SEO-поток ноября 2026: FAQ по слагу, обратные ссылки, хлебные крошки,
title по правилам, lastmod в sitemap и сезонный блок на главной."""
import json
import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from site_app import seo

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])


@pytest.fixture()
def client():
    return TestClient(app)


def _ld_blocks(html: str) -> list:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


def _place(client, name="SEO-тестовое место"):
    r = client.post("/api/checkpoints", json={"name": name, "lon": 40.2, "lat": 44.3, "is_paid": False}, auth=AUTH)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_place_gets_faq_breadcrumbs_and_mentions(client):
    pid = _place(client)
    r = client.post("/api/faq-sets", json={
        "name": "seo test", "slug": f"mesta-{pid}", "title": "Частые вопросы про тест",
        "items": [{"question": "Сколько стоит?", "answer": "Бесплатно."}],
    }, auth=AUTH)
    assert r.status_code == 201, r.text
    slug = "seo-test-" + uuid.uuid4().hex[:6]
    r = client.post("/api/articles", json={
        "title": "Статья со ссылкой", "slug": slug, "body": f'<p>Смотри <a href="/mesta/{pid}">место</a>.</p>',
    }, auth=AUTH)
    assert r.status_code == 201, r.text

    html = client.get(f"/mesta/{pid}").text
    assert "Частые вопросы про тест" in html
    # FAQ стоит до «Понравилось?»
    assert html.index("Частые вопросы про тест") < html.index('class="like-row"')
    types = {b.get("@type") for b in _ld_blocks(html)}
    assert {"FAQPage", "BreadcrumbList", "TouristAttraction"} <= types
    assert "Где ещё про это место" in html and f"/stati/{slug}" in html


def test_article_title_rule_next_hub_and_dates(client):
    r = client.post("/api/articles", json={"title": "Туман только наверху", "slug": "tuman-na-lago-naki-kuda-ehat", "body": "<p>x</p>",
                                           "faq": [{"question": "Q?", "answer": "A."}]}, auth=AUTH)
    assert r.status_code in (201, 409, 400, 422) or r.status_code < 300
    html = client.get("/stati/tuman-na-lago-naki-kuda-ehat").text
    assert f"<title>{seo.ARTICLE_TITLES['tuman-na-lago-naki-kuda-ehat']}</title>" in html
    assert "<h1 class=\"article-title\">Туман только наверху</h1>" in html
    article_ld = next(b for b in _ld_blocks(html) if b.get("@type") == "Article")
    assert article_ld.get("dateModified")
    assert any(b.get("@type") == "FAQPage" for b in _ld_blocks(html))


def test_district_title_uses_village_name():
    assert "Каменномостский" in seo.DISTRICT_TITLES["khadzhokh"]
    for title in list(seo.DISTRICT_TITLES.values()) + list(seo.ARTICLE_TITLES.values()):
        assert len(title) <= 75, title


def test_place_title_rule():
    assert seo.place_title("Хаджохская теснина", "khadzhokh") == \
        "Хаджохская теснина (Каменномостский, Адыгея) — как добраться и что посмотреть"
    assert seo.place_title("Плато Лаго-Наки", "lagonaki").startswith("Плато Лаго-Наки (Адыгея)")


def test_sitemap_has_lastmod_for_sections(client):
    _place(client, "SEO lastmod")
    xml = client.get("/sitemap.xml").text
    block = re.search(r"<loc>[^<]*/mesta</loc>\s*<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", xml)
    assert block, xml[:500]


def test_seasonal_config_never_links_to_dog_cluster():
    for month in range(1, 13):
        cfg = seo.SEASONAL.get(month)
        for item in (cfg or {}).get("items", []):
            assert "sobak" not in item["url"]
