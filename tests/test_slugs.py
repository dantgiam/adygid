"""Читаемые адреса: /mesta/<slug>, /marshruty/<slug>, /stati/<slug>.
Слаг канонический; /<раздел>/<id> и прежние слаги — 301 навсегда."""
import json
import os
import re
import uuid
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app
from app.slugs import backfill_slugs, entity_slug_base, slugify
from site_app import urls as site_urls
from site_app.router import SITE_URL

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])


@pytest.fixture()
def client():
    return TestClient(app)


def _uid() -> str:
    # Только буквы: цифры в названии дали бы цифры и в слаге.
    return "".join("абвгдежзиклмнопрстуф"[int(c, 16)] for c in uuid.uuid4().hex[:6])


def _place(client, name, **extra):
    r = client.post("/api/checkpoints", json={"name": name, "lon": 40.2, "lat": 44.3, "is_paid": False, **extra}, auth=AUTH)
    assert r.status_code == 201, r.text
    return r.json()


def _route(client, name, **extra):
    r = client.post("/api/trails", json={"name": name, "is_paid": False, **extra}, auth=AUTH)
    assert r.status_code == 201, r.text
    return r.json()


def _ld_blocks(html: str) -> list:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


# ── правила слага ──────────────────────────────────────────────

@pytest.mark.parametrize("name,kind,expected", [
    ("«Кедровый бор»: термальный бассейн в Цветочном", "place", "kedrovyy-bor"),
    ("Плато Лаго-Наки", "place", "plato-lago-naki"),
    ("Хаджохская теснина", "place", "hadzhohskaya-tesnina"),
    ("«АкваТермо»: термальные бассейны в Тульском", "place", "akvatermo"),
    ("Пещера Сквозная у Руфабго (Кошачий глаз)", "place", "peschera-skvoznaya-u-rufabgo"),
    ("Скала Чёртов палец", "place", "skala-chertov-palets"),
    ("Победа: грот Череп и скала Галкина", "route", "pobeda-grot-cherep-i-skala-galkina"),
    ("Смотровая с качелями по дороге на Лаго-Наки", "place", "smotrovaya-s-kachelyami-po-doroge-na-lago-naki"),
    ("2024", "place", "mesto-2024"),
    ("123", "route", "marshrut-123"),
])
def test_slug_rules(name, kind, expected):
    assert entity_slug_base(name, kind) == expected


def test_long_names_are_trimmed_on_word_boundary_without_dangling_preposition():
    s = entity_slug_base("Каменномостский: скала Молоток, Окно в Европу и Космодром", "route")
    assert len(s) <= 50 and not s.endswith(("-i", "-v")) and s.startswith("kamennomostskiy-skala-molotok")
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s)


def test_slugify_keeps_existing_article_style():
    assert slugify("Хаджох зимой") == "hadzhoh-zimoy"
    assert slugify("Адыгея в декабре") == "adygeya-v-dekabre"


# ── новые записи, редиректы, canonical ─────────────────────────

def test_new_place_gets_slug_and_canonical_page(client):
    u = _uid()
    cp = _place(client, f"Водопад {u}: тестовый")
    assert cp["slug"] == slugify(f"Водопад {u}")
    assert cp["url"] == f"/mesta/{cp['slug']}"

    r = client.get(cp["url"], follow_redirects=False)
    assert r.status_code == 200
    html = r.text
    canonical = SITE_URL + cp["url"]
    assert f'<link rel="canonical" href="{canonical}">' in html
    assert f'<meta property="og:url" content="{canonical}">' in html
    attr = next(b for b in _ld_blocks(html) if b.get("@type") == "TouristAttraction")
    assert attr["url"] == canonical
    crumbs = next(b for b in _ld_blocks(html) if b.get("@type") == "BreadcrumbList")
    assert crumbs["itemListElement"][-1]["item"] == canonical


def test_numeric_place_url_redirects_301_forever_with_query(client):
    cp = _place(client, f"Скала {_uid()}")
    r = client.get(f"/mesta/{cp['id']}", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == cp["url"]
    r = client.get(f"/mesta/{cp['id']}?utm_source=qr&x=1", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == cp["url"] + "?utm_source=qr&x=1"
    # заглавные буквы в слаге — тоже 301 на канонический
    r = client.get(cp["url"].upper().replace("/MESTA/", "/mesta/"), follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == cp["url"]


def test_rename_keeps_slug(client):
    cp = _place(client, f"Поляна {_uid()}")
    r = client.patch(f"/api/checkpoints/{cp['id']}", json={"name": "Совсем другое имя"}, auth=AUTH)
    assert r.status_code == 200 and r.json()["slug"] == cp["slug"]
    assert client.get(cp["url"], follow_redirects=False).status_code == 200


def test_admin_slug_change_keeps_old_address_as_301(client):
    cp = _place(client, f"Грот {_uid()}")
    new = f"grot-novyy-{uuid.uuid4().hex[:6]}"
    r = client.patch(f"/api/checkpoints/{cp['id']}", json={"slug": new.upper().replace("-", " ")}, auth=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == new
    old = client.get(cp["url"], follow_redirects=False)
    assert old.status_code == 301 and old.headers["location"] == f"/mesta/{new}"
    by_id = client.get(f"/mesta/{cp['id']}", follow_redirects=False)
    assert by_id.status_code == 301 and by_id.headers["location"] == f"/mesta/{new}"
    assert client.get(f"/mesta/{new}", follow_redirects=False).status_code == 200
    # вернуть прежний слаг можно — без петли редиректов
    r = client.patch(f"/api/checkpoints/{cp['id']}", json={"slug": cp["slug"]}, auth=AUTH)
    assert r.json()["slug"] == cp["slug"]
    assert client.get(cp["url"], follow_redirects=False).status_code == 200
    assert client.get(f"/mesta/{new}", follow_redirects=False).headers["location"] == cp["url"]


def test_old_slug_is_not_given_to_another_place(client):
    a = _place(client, f"Утёс {_uid()}")
    new = f"utes-{uuid.uuid4().hex[:6]}"
    client.patch(f"/api/checkpoints/{a['id']}", json={"slug": new}, auth=AUTH)
    b = _place(client, "Другое", slug=a["slug"])
    assert b["slug"] == a["slug"] + "-2"


def test_same_names_get_suffix_and_digit_slug_is_refused(client):
    name = f"Озеро {_uid()}"
    a, b = _place(client, name), _place(client, name)
    assert b["slug"] == a["slug"] + "-2"
    c = _place(client, f"Пещера {_uid()}")
    r = client.patch(f"/api/checkpoints/{c['id']}", json={"slug": "777"}, auth=AUTH)
    assert r.json()["slug"].startswith("mesto-777")
    assert client.get(f"/mesta/{r.json()['slug']}", follow_redirects=False).status_code == 200


def test_hidden_place_by_id_is_404_not_redirect(client):
    cp = _place(client, f"Скрытое {_uid()}", is_published=False)
    assert client.get(f"/mesta/{cp['id']}", follow_redirects=False).status_code == 404
    assert client.get(cp["url"], follow_redirects=False).status_code == 404
    pt = _place(client, f"Развилка {_uid()}", show_as_place=False)
    assert client.get(f"/mesta/{pt['id']}", follow_redirects=False).status_code == 404
    assert client.get("/mesta/net-takogo-mesta-xyz", follow_redirects=False).status_code == 404
    assert client.get("/mesta/999999999", follow_redirects=False).status_code == 404


def test_route_slug_redirects_and_gpx(client):
    t = _route(client, f"Тропа {_uid()}: к водопаду")
    assert t["url"] == f"/marshruty/{t['slug']}"
    r = client.get(f"/marshruty/{t['id']}?a=1", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == t["url"] + "?a=1"
    page = client.get(t["url"], follow_redirects=False)
    assert page.status_code == 200
    assert f'<link rel="canonical" href="{SITE_URL}{t["url"]}">' in page.text
    gpx = client.get(f"/marshruty/{t['id']}/track.gpx", follow_redirects=False)
    assert gpx.status_code == 301 and gpx.headers["location"] == t["url"] + "/track.gpx"
    gpx = client.get(t["url"] + "/track.gpx", follow_redirects=False)
    assert gpx.status_code == 200 and f"{SITE_URL}{t['url']}" in gpx.text
    new = f"tropa-{uuid.uuid4().hex[:6]}"
    client.patch(f"/api/trails/{t['id']}", json={"slug": new}, auth=AUTH)
    r = client.get(t["url"], follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/marshruty/{new}"


def test_article_id_and_old_slug_redirect(client):
    slug = "slug-test-" + uuid.uuid4().hex[:6]
    r = client.post("/api/articles", json={"title": "Тест слага", "slug": slug, "body": "<p>x</p>", "is_published": True}, auth=AUTH)
    assert r.status_code in (200, 201), r.text
    aid = r.json()["id"]
    r = client.get(f"/stati/{aid}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/stati/{slug}"
    client.patch(f"/api/articles/{aid}", json={"slug": slug + "-new"}, auth=AUTH)
    r = client.get(f"/stati/{slug}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/stati/{slug}-new"
    assert client.get(f"/stati/{slug}-new", follow_redirects=False).status_code == 200


# ── внутренние ссылки и sitemap ─────────────────────────────────

_HREF_RE = re.compile(r'href="(/(?:mesta|marshruty)/[^"#?]+)')


def test_internal_links_are_canonical_without_redirect(client):
    a = _place(client, f"Каньон {_uid()}")
    b = _place(client, f"Ручей {_uid()}")
    t = _route(client, f"Маршрут {_uid()}")
    slug = "slug-links-" + uuid.uuid4().hex[:6]
    body = (f'<p><a href="/mesta/{a["id"]}">раз</a>, <a href="/mesta/{b["id"]}#faq">два</a>, '
            f'<a href="/marshruty/{t["id"]}">тропа</a>, <a href="https://www.adygid.ru/mesta/{a["id"]}">абсолютная</a>.</p>')
    r = client.post("/api/articles", json={
        "title": "Ссылки", "slug": slug, "body": body, "is_published": True,
        "featured_checkpoint_ids": [a["id"]], "featured_trail_ids": [t["id"]],
    }, auth=AUTH)
    assert r.status_code in (200, 201), r.text
    site_urls.invalidate()
    html = client.get(f"/stati/{slug}").text
    assert f'href="{a["url"]}"' in html and f'href="{b["url"]}#faq"' in html and f'href="{t["url"]}"' in html
    assert f'href="https://www.adygid.ru{a["url"]}"' in html
    # «Где ещё про это место» находит статью и после подмены ссылок
    assert f"/stati/{slug}" in client.get(a["url"]).text

    pages = ["/", "/mesta", "/marshruty", f"/stati/{slug}", a["url"], t["url"], "/podbor"]
    for page in pages:
        html = client.get(page).text
        # Числовая ссылка допустима только на несуществующую карточку (в
        # тестовой базе нет боевых id вроде 55 из плашек) — живые подменены.
        for num in set(re.findall(r'href="(/(?:mesta|marshruty)/\d+)["#?/]', html)):
            assert client.get(num, follow_redirects=False).status_code == 404, (page, num)
        for href in set(_HREF_RE.findall(html)):
            if href.endswith("/track.gpx") or re.fullmatch(r"/(mesta|marshruty)/\d+", href):
                continue
            r = client.get(href, follow_redirects=False)
            assert r.status_code == 200, (page, href, r.status_code)


def test_sitemap_lists_slug_urls_only(client):
    cp = _place(client, f"Карта сайта {_uid()}")
    t = _route(client, f"Карта маршрут {_uid()}")
    xml = client.get("/sitemap.xml").text
    locs = [e.text for e in ElementTree.fromstring(xml).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert SITE_URL + cp["url"] in locs and SITE_URL + t["url"] in locs
    assert not [u for u in locs if re.search(r"/(mesta|marshruty)/\d+$", u)]


def test_podbor_catalog_and_api_urls_use_slugs(client):
    cp = _place(client, f"Подбор {_uid()}", kid_friendly=True)
    assert cp["url"] in client.get("/podbor").text
    fav = client.get(f"/api/site/favorites?items=place:{cp['id']}").json()
    assert fav[0]["url"] == cp["url"]


def test_backfill_fills_missing_slugs_without_touching_updated_at(client):
    cp = _place(client, f"Бэкфилл {_uid()}")
    with SessionLocal() as db:
        before = db.execute(text("SELECT updated_at FROM checkpoints WHERE id=:i"), {"i": cp["id"]}).scalar()
        db.execute(text("UPDATE checkpoints SET slug = NULL, updated_at = :u WHERE id = :i"), {"i": cp["id"], "u": before})
        db.commit()
        # без слага страница всё равно открывается по id
        site_urls.invalidate()
        assert client.get(f"/mesta/{cp['id']}", follow_redirects=False).status_code == 200
        assert backfill_slugs(db) >= 1
        db.commit()
        row = db.execute(text("SELECT slug, updated_at FROM checkpoints WHERE id=:i"), {"i": cp["id"]}).one()
    assert row.slug == cp["slug"] and row.updated_at == before
    assert client.get(f"/mesta/{cp['id']}", follow_redirects=False).status_code == 301


# ── админка «Тексты сайта» ──────────────────────────────────────

def test_admin_texts_links_to_slug_and_edits_slug(client):
    cp = _place(client, f"Тексты {_uid()}")
    lst = client.get("/admin/texts/places", auth=AUTH).text
    assert f'href="{cp["url"]}#kratko"' in lst
    page = client.get(f"/admin/texts/places/{cp['id']}", auth=AUTH).text
    assert f'href="{cp["url"]}#kratko"' in page
    assert f'value="{cp["slug"]}"' in page and f'<span data-sn="slug">{cp["slug"]}</span>' in page
    new = f"teksty-{uuid.uuid4().hex[:6]}"
    r = client.post(f"/admin/texts/places/{cp['id']}", data={"slug": new, "enabled": "1"}, auth=AUTH, follow_redirects=False)
    assert r.status_code == 303, r.text
    assert client.get(f"/mesta/{new}", follow_redirects=False).status_code == 200
    old = client.get(cp["url"], follow_redirects=False)
    assert old.status_code == 301 and old.headers["location"] == f"/mesta/{new}"
