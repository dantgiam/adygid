"""Поездки автора: слаг, 301 с числового id, черновики и sitemap.
Страница автора и черновик Белореченского водопада."""
import json
import os
import re
import uuid
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.content_fixes import (
    MONASTERY_NAME,
    MONASTERY_OLD_NAME,
    MONASTERY_OLD_TITLE,
    WATERFALL_NAME,
    WATERFALL_OSM_NODE,
    WATERFALL_SLUG,
    rename_mikhailovsky,
)
from app.database import SessionLocal, engine
from app.main import app
from app.models import Checkpoint
from site_app.router import SITE_URL
from site_app.seo import PLACE_TITLES
from site_app.video import video_embed_src
from site_app import trip_facts

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])
_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@pytest.fixture()
def client():
    return TestClient(app)


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _locs(xml: str) -> list:
    return [e.text for e in ElementTree.fromstring(xml).iter(f"{_NS}loc")]


def _ld(html: str) -> list:
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


def _save(client, **fields):
    data = {
        "id": "",
        "title": "Поездка",
        "trip_date": "2026-04-02",
        "slug": "",
        "body": "Был на месте.",
        "changes_note": "",
        "spent_note": "",
        "video_url": "",
        "source_url": "",
        "photo_url": "",
        "photo_alt": "",
    }
    data.update(fields)
    r = client.post("/admin/poezdki/save", data=data, auth=AUTH, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"]


# ── видео: в iframe только известные хосты ─────────────────────

def test_video_embed_allowlist():
    assert video_embed_src("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == \
        "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
    assert video_embed_src("https://youtu.be/dQw4w9WgXcQ") == \
        "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
    assert video_embed_src("https://rutube.ru/video/0123456789abcdef0123456789abcdef/") == \
        "https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef"
    assert video_embed_src("https://vk.com/video-1_2") == "https://vk.com/video_ext.php?oid=-1&id=2&hd=2"
    assert video_embed_src("https://example.com/watch?v=dQw4w9WgXcQ") is None
    assert video_embed_src("javascript:alert(1)") is None
    assert video_embed_src("") is None


# ── страница автора ─────────────────────────────────────────────

def test_author_page_footer_and_article_person(client):
    page = client.get("/avtor")
    assert page.status_code == 200
    assert "Данила" in page.text and "Даня" in page.text
    assert "МГТУ" in page.text
    assert 'href="https://t.me/adygid"' in page.text
    assert "https://max.ru/join/0qCTe9sSqljJIWYNI5hWBecoM1rr3B_proAXGK5O0tE" in page.text
    assert 'href="/poezdki"' in page.text
    person = next(b["mainEntity"] for b in _ld(page.text) if b.get("@type") == "ProfilePage")
    assert person["@type"] == "Person" and person["name"] == "Данила"
    assert person["url"] == SITE_URL + "/avtor"

    home = client.get("/")
    assert 'href="/avtor"' in home.text
    articles = client.get("/stati")
    assert 'href="/avtor"' in articles.text

    slug = "avtor-ld-" + _uid()
    r = client.post("/api/articles", json={
        "title": "Про автора", "slug": slug, "body": "<p>текст</p>", "is_published": True,
    }, auth=AUTH)
    assert r.status_code in (200, 201), r.text
    html = client.get(f"/stati/{slug}").text
    article = next(b for b in _ld(html) if b.get("@type") == "Article")
    assert article["author"] == {"@type": "Person", "name": "Данила", "url": SITE_URL + "/avtor"}
    assert 'href="/avtor"' in html

    admin = client.get("/admin/texts/pages?page=avtor", auth=AUTH)
    assert admin.status_code == 200
    assert "avtor.schema_name" in admin.text and "avtor.telegram_url" in admin.text
    assert client.get("/admin/poezdki").status_code == 401


# ── поездки: слаг, черновик, sitemap ────────────────────────────

def test_trip_slug_redirect_draft_and_sitemap(client):
    token = _uid()
    loc = _save(
        client,
        title=f"Выезд {token}",
        body="Короткий текст поездки.",
        changes_note="Тропа стала **мокрее**.",
        spent_note="500 рублей на бензин",
        source_url="https://t.me/adygid/10",
        video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=junk",
        photo_url=["https://example.com/a.webp", ""],
        photo_alt=["Река после дождя", ""],
    )
    trip_id = int(re.search(r"/admin/poezdki/(\d+)", loc).group(1))
    with SessionLocal() as db:
        row = db.execute(text("SELECT slug, is_published FROM author_trips WHERE id=:i"), {"i": trip_id}).one()
    assert row.is_published is False
    assert row.slug.startswith("vyezd-")
    assert client.get(f"/poezdki/{row.slug}", follow_redirects=False).status_code == 404
    assert client.get(f"/poezdki/{trip_id}", follow_redirects=False).status_code == 404
    hidden = client.get("/sitemap.xml").text
    assert f"/poezdki/{row.slug}" not in hidden
    assert f"/poezdki/{trip_id}" not in hidden
    assert any(u.endswith("/poezdki") for u in _locs(hidden))
    assert any(u.endswith("/avtor") for u in _locs(hidden))

    new_slug = f"poezdka-{token}"
    r = client.post("/admin/poezdki/save", data={
        "id": str(trip_id), "title": f"Выезд {token}", "trip_date": "2026-04-02",
        "slug": new_slug, "body": "Короткий текст поездки.",
        "changes_note": "Тропа стала **мокрее**.", "spent_note": "500 рублей на бензин",
        "source_url": "https://t.me/adygid/10",
        "video_url": "https://youtu.be/dQw4w9WgXcQ",
        "photo_url": "https://example.com/a.webp", "photo_alt": "Река после дождя",
        "is_published": "1",
    }, auth=AUTH, follow_redirects=False)
    assert r.status_code == 303, r.text

    redir = client.get(f"/poezdki/{trip_id}?utm=max", follow_redirects=False)
    assert redir.status_code == 301
    assert redir.headers["location"] == f"/poezdki/{new_slug}?utm=max"
    old = client.get(f"/poezdki/{row.slug}", follow_redirects=False)
    assert old.status_code == 301 and old.headers["location"] == f"/poezdki/{new_slug}"
    page = client.get(f"/poezdki/{new_slug}")
    assert page.status_code == 200
    assert f'<link rel="canonical" href="{SITE_URL}/poezdki/{new_slug}">' in page.text
    assert "Тропа стала <strong>мокрее</strong>." in page.text
    assert "500 рублей на бензин" in page.text
    assert 'alt="Река после дождя"' in page.text
    assert "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" in page.text
    assert "list=junk" not in page.text
    assert 'href="https://t.me/adygid/10"' in page.text
    assert f"Выезд {token}" in client.get("/poezdki").text

    locs = _locs(client.get("/sitemap.xml").text)
    assert SITE_URL + f"/poezdki/{new_slug}" in locs
    assert not [u for u in locs if re.search(r"/poezdki/\d+$", u)]

    # чужой https не становится iframe
    client.post("/admin/poezdki/save", data={
        "id": str(trip_id), "title": f"Выезд {token}", "trip_date": "2026-04-02",
        "slug": new_slug, "body": "Короткий текст поездки.",
        "video_url": "https://example.com/clip", "is_published": "1",
        "photo_url": "", "photo_alt": "",
    }, auth=AUTH, follow_redirects=False)
    html = client.get(f"/poezdki/{new_slug}").text
    assert "<iframe" not in html
    assert 'href="https://example.com/clip"' in html

    # без alt фото не сохраняется
    bad = client.post("/admin/poezdki/save", data={
        "id": str(trip_id), "title": f"Выезд {token}", "trip_date": "2026-04-02",
        "slug": new_slug, "body": "x", "photo_url": "https://example.com/a.webp", "photo_alt": "",
    }, auth=AUTH)
    assert bad.status_code == 400


def test_empty_state_when_nothing_published(client):
    with engine.begin() as conn:
        conn.execute(text("UPDATE author_trips SET is_published = false"))
    html = client.get("/poezdki").text
    assert "empty-state" in html
    assert "Поездок пока нет" in html
    locs = _locs(client.get("/sitemap.xml").text)
    assert any(u.endswith("/poezdki") for u in locs)
    assert not [u for u in locs if re.search(r"/poezdki/[a-z0-9-]+$", u)]


def test_trip_links_only_published_places(client):
    mark = _uid()
    pub = client.post("/api/checkpoints", json={
        "name": f"Место поездки {mark}", "lon": 40.2, "lat": 44.2, "is_paid": False, "is_published": True,
    }, auth=AUTH).json()
    hid = client.post("/api/checkpoints", json={
        "name": f"Черновик места {mark}", "lon": 40.2, "lat": 44.2, "is_paid": False, "is_published": False,
    }, auth=AUTH).json()
    slug = f"svyaz-{mark}"
    _save(client, title=f"Связка {mark}", slug=slug, is_published="1",
          place_ids=[str(pub["id"]), str(hid["id"])])
    html = client.get(f"/poezdki/{slug}").text
    assert pub["url"] in html
    assert hid["url"] not in html
    assert f"Черновик места {mark}" not in html


# ── черновик водопада и название монастыря ─────────────────────

def test_waterfall_is_draft_and_not_in_sitemap(client):
    from app.content_fixes import seed_waterfall
    with SessionLocal() as db:
        seed_waterfall(db)
        db.commit()
    try:
        with SessionLocal() as db:
            row = db.execute(text(
                "SELECT id, slug, is_published, show_as_place, description, is_paid, "
                "ST_Y(geom) AS lat, ST_X(geom) AS lon "
                "FROM checkpoints WHERE name = :n"
            ), {"n": WATERFALL_NAME}).one()
        assert row.slug == WATERFALL_SLUG
        assert row.is_published is False and row.show_as_place is True
        assert row.is_paid is None
        assert abs(row.lat - 44.7342467) < 1e-6 and abs(row.lon - 39.8775977) < 1e-6
        desc = row.description
        assert WATERFALL_OSM_NODE in desc
        assert "kubnews.ru" in desc
        assert "База Эльна" in desc and "Тополиной" in desc
        assert "глинист" in desc and "обув" in desc
        assert "₽" not in desc and "км" not in desc and "3,4" not in desc
        assert client.get(f"/mesta/{row.slug}", follow_redirects=False).status_code == 404
        assert client.get(f"/mesta/{row.id}", follow_redirects=False).status_code == 404
        assert WATERFALL_SLUG not in client.get("/sitemap.xml").text
        with SessionLocal() as db:
            assert seed_waterfall(db) is False
            db.rollback()
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM checkpoints WHERE name = :n"), {"n": WATERFALL_NAME})


def test_monastery_title_keeps_slug(client):
    slug = "mihaylo-afonskaya-pustyn"
    with SessionLocal() as db:
        cp = db.get(Checkpoint, 30)
        if cp is None:
            cp = Checkpoint(
                id=30,
                name=MONASTERY_OLD_NAME,
                slug=slug,
                geom="SRID=4326;POINT(40.16 44.27)",
                is_published=True,
                show_as_place=True,
                is_paid=False,
            )
            db.add(cp)
            db.commit()
            cp = db.get(Checkpoint, 30)
        elif (cp.name or "").strip() not in (MONASTERY_OLD_NAME, MONASTERY_NAME):
            pytest.skip("в тестовой базе id 30 занят другой карточкой")
        slug_before = cp.slug
        db.execute(text(
            "INSERT INTO place_trip_blocks (place_id, enabled, seo_title, rows, combine_ids, auto_visit, search_facts, sources) "
            "VALUES (30, false, :old, '[]'::jsonb, '[]'::jsonb, true, '{}'::jsonb, '[]'::jsonb) "
            "ON CONFLICT (place_id) DO UPDATE SET seo_title = :old"
        ), {"old": MONASTERY_OLD_TITLE})
        db.commit()
        rename_mikhailovsky(db)
        db.commit()
        db.refresh(cp)
        title = db.execute(text("SELECT seo_title FROM place_trip_blocks WHERE place_id = 30")).scalar()
        name, kept = cp.name, cp.slug
        published = cp.is_published and cp.show_as_place
    trip_facts.invalidate()
    assert MONASTERY_NAME in name or "Свято-Михайловский монастырь" in name
    assert kept == slug_before
    assert title == PLACE_TITLES[30]
    if published:
        html = client.get(f"/mesta/{kept}").text
        assert "<h1" in html and "Свято-Михайловский монастырь" in html
        assert "Свято-Михайловский монастырь" in html.split("</title>", 1)[0]
        # второй прогон слаг не плодит
        with SessionLocal() as db:
            again = db.get(Checkpoint, 30).slug
            rename_mikhailovsky(db)
            db.commit()
            assert db.get(Checkpoint, 30).slug == again
    with SessionLocal() as db:
        cp = db.get(Checkpoint, 30)
        if cp is not None:
            cp.is_published = False
            if cp.is_paid is None:
                cp.is_paid = False
            db.commit()
