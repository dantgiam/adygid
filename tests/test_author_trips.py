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
    person = next(b for b in _ld(page.text) if b.get("@type") == "Person")
    assert person["name"] == "Данила"
    assert person["url"] == SITE_URL + "/avtor"
    assert person["sameAs"] == [
        "https://t.me/adygid",
        "https://max.ru/join/0qCTe9sSqljJIWYNI5hWBecoM1rr3B_proAXGK5O0tE",
    ]
    assert "affiliation" not in person and "alumniOf" not in person and "worksFor" not in person
    assert not any(b.get("@type") in ("CollegeOrUniversity", "EducationalOrganization", "Organization") for b in _ld(page.text))

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


# Тексты, которые гость видит на /avtor, в подвале, в статьях и на пустом /poezdki.
_EDITABLE_COPY = (
    "avtor.meta.title", "avtor.meta.desc", "avtor.eyebrow", "avtor.schema_name",
    "avtor.aka_line", "avtor.lead", "avtor.bio",
    "avtor.telegram_label", "avtor.telegram_url", "avtor.max_label", "avtor.max_url",
    "avtor.photo_alt", "avtor.photo_caption",
    "avtor.trips_link", "avtor.trips_title", "avtor.trips_note", "avtor.trips_empty",
    "avtor.materials_title", "avtor.materials_note", "avtor.materials_articles",
    "avtor.materials_routes", "avtor.materials_empty",
    "avtor.stats_title", "avtor.stats_note",
    "footer.author",
    "articles.author_note", "articles.author_link", "articles.byline_prefix", "articles.byline_name",
    "poezdki.meta.title", "poezdki.meta.desc", "poezdki.eyebrow", "poezdki.title",
    "poezdki.lead", "poezdki.author_link", "poezdki.empty",
    "poezdki.eyebrow_link", "poezdki.by_author", "poezdki.changes_title",
    "poezdki.spent_title", "poezdki.video_link", "poezdki.places_title", "poezdki.source",
)


def _save_text(client, key, value, action="save"):
    r = client.post(
        "/admin/texts/pages/edit",
        data={"key": key, "value": value, "action": action},
        auth=AUTH, follow_redirects=False,
    )
    assert r.status_code == 303, (key, r.status_code, r.text)


def test_author_and_trip_copy_is_edited_in_admin_texts(client):
    listing = client.get("/admin/texts/pages", auth=AUTH).text
    missing = [key for key in _EDITABLE_COPY if key not in listing]
    assert missing == []

    mark = "PRAVKA" + _uid()[:6]
    edited = {
        "avtor.telegram_label": f"Телеграм {mark}",
        "avtor.max_label": f"Макс {mark}",
        "avtor.trips_link": f"К поездкам {mark}",
        "avtor.trips_title": f"Поездки раздела {mark}",
        "avtor.materials_title": f"Материалы раздела {mark}",
        "avtor.stats_title": f"Счётчик раздела {mark}",
        "avtor.stats_note": f"Пометка счётчика {mark}",
        "avtor.trips_empty": f"Пустые поездки автора {mark}",
        "footer.author": f"Подвал автора {mark}",
        "articles.author_note": f"Заметка статей {mark}",
        "articles.author_link": f"Ссылка статей {mark}",
        "articles.byline_prefix": f"Кто {mark}",
        "articles.byline_name": f"Имя {mark}",
        "poezdki.empty": f"Пустой раздел {mark}",
        "poezdki.title": f"Заголовок поездок {mark}",
        "poezdki.author_link": f"Автор поездок {mark}",
    }
    published = []
    try:
        for key, value in edited.items():
            _save_text(client, key, value)
        avtor = client.get("/avtor").text
        assert edited["avtor.telegram_label"] in avtor
        assert edited["avtor.max_label"] in avtor
        assert edited["avtor.trips_link"] in avtor
        assert edited["avtor.trips_title"] in avtor
        assert edited["avtor.materials_title"] in avtor
        assert edited["avtor.stats_title"] in avtor
        assert edited["avtor.stats_note"] in avtor
        assert edited["footer.author"] in avtor
        stati = client.get("/stati").text
        assert edited["articles.author_note"] in stati
        assert edited["articles.author_link"] in stati
        assert edited["footer.author"] in stati
        slug = "tekst-avtora-" + _uid()
        made = client.post("/api/articles", json={
            "title": "Текст автора", "slug": slug, "body": "<p>абзац</p>", "is_published": True,
        }, auth=AUTH)
        assert made.status_code in (200, 201), made.text
        article = client.get(f"/stati/{slug}").text
        assert edited["articles.byline_prefix"] in article
        assert edited["articles.byline_name"] in article
        with engine.begin() as conn:
            published = conn.execute(text(
                "SELECT id FROM author_trips WHERE is_published"
            )).scalars().all()
            conn.execute(text("UPDATE author_trips SET is_published = false"))
        trips = client.get("/poezdki").text
        assert edited["poezdki.empty"] in trips
        assert edited["poezdki.title"] in trips
        assert edited["poezdki.author_link"] in trips
        assert edited["footer.author"] in trips
        avtor_empty = client.get("/avtor").text
        assert edited["avtor.trips_empty"] in avtor_empty
        assert 'class="empty-state"' in avtor_empty
    finally:
        for key in edited:
            _save_text(client, key, "вернуть", action="reset")
        if published:
            with engine.begin() as conn:
                for trip_id in published:
                    conn.execute(text(
                        "UPDATE author_trips SET is_published = true WHERE id = :i"
                    ), {"i": trip_id})


def test_author_page_cards_keep_home_and_trips_pages(client):
    """/avtor берёт карточки статей, маршрутов и поездок. Главная и /poezdki не меняются."""
    home = client.get("/").text
    assert "author-hero" not in home
    assert "Мои поездки" not in home
    assert "Мои материалы" not in home
    poezdki = client.get("/poezdki").text
    assert "author-hero" not in poezdki
    assert 'class="hero"' not in poezdki
    css = client.get("/assets/site.css").text
    assert ".author-hero .hero-ctas { margin-top: 22px; }" in css
    assert ".author-hero .hero-ctas { margin-top: 18px; }" in css

    token = _uid()
    hidden = _save(client, title=f"Черновик выезда {token}", slug=f"chernovik-vyezda-{token}")
    assert f"Черновик выезда {token}" not in client.get("/avtor").text
    trip_id = int(re.search(r"/admin/poezdki/(\d+)", hidden).group(1))
    published = client.post("/admin/poezdki/save", data={
        "id": str(trip_id), "title": f"Живой выезд {token}", "trip_date": "2099-01-02",
        "slug": f"zhivoj-vyezd-{token}", "body": "Текст живой поездки автора.",
        "is_published": "1", "photo_url": "", "photo_alt": "",
    }, auth=AUTH, follow_redirects=False)
    assert published.status_code == 303, published.text

    article = client.post("/api/articles", json={
        "title": f"Материал автора {token}", "slug": f"material-avtora-{token}",
        "body": "<p>абзац</p>", "excerpt": f"Анонс материала {token}", "is_published": True,
    }, auth=AUTH)
    assert article.status_code == 201, article.text
    hidden_article = client.post("/api/articles", json={
        "title": f"Скрытая статья {token}", "slug": f"skrytaya-statya-{token}",
        "body": "<p>нет</p>", "is_published": False,
    }, auth=AUTH)
    assert hidden_article.status_code == 201, hidden_article.text
    route = client.post("/api/trails", json={
        "name": f"Маршрут автора {token}",
        "description": f"Описание маршрута автора {token}.",
        "slug": f"marshrut-avtora-{token}", "is_published": True, "is_paid": False,
    }, auth=AUTH)
    assert route.status_code == 201, route.text
    hidden_route = client.post("/api/trails", json={
        "name": f"Скрытый маршрут {token}", "slug": f"skrytyj-marshrut-{token}",
        "is_published": False, "is_paid": False,
    }, auth=AUTH)
    assert hidden_route.status_code == 201, hidden_route.text

    page = client.get("/avtor").text
    assert f"Живой выезд {token}" in page
    assert f'href="/poezdki/zhivoj-vyezd-{token}"' in page
    assert f"Черновик выезда {token}" not in page
    assert f"Материал автора {token}" in page
    assert f"Анонс материала {token}" in page
    assert f'/stati/{article.json()["slug"]}' in page
    assert f"Скрытая статья {token}" not in page
    assert f"Маршрут автора {token}" in page
    assert f"Описание маршрута автора {token}" in page
    assert route.json()["url"] in page
    assert f"Скрытый маршрут {token}" not in page
    assert "Пройдено лично" in page
    assert "пройдены лично" in page
    assert 'class="hero author-hero"' in page
    assert 'class="section-head"' in page
    assert 'class="grid"' in page

    # Список поездок остаётся своей страницей и по-прежнему показывает карточку.
    listing = client.get("/poezdki").text
    assert f"Живой выезд {token}" in listing
    assert "author-hero" not in listing
    assert 'class="hero"' not in listing


def test_author_trips_empty_and_capped_without_changing_list(client):
    with engine.begin() as conn:
        published_ids = conn.execute(text(
            "SELECT id FROM author_trips WHERE is_published"
        )).scalars().all()
        conn.execute(text("UPDATE author_trips SET is_published = false"))
    try:
        empty = client.get("/avtor").text
        assert "Мои поездки" in empty
        assert "empty-state" in empty
        assert "Поездок пока нет. Данила добавит их после следующих выездов." in empty
        bare = client.get("/poezdki").text
        assert "Поездок пока нет" in bare
        assert "author-hero" not in bare
        assert 'class="hero"' not in bare

        token = _uid()
        for i in range(7):
            _save(
                client,
                title=f"Пачка {token} {i}",
                trip_date=f"2026-06-{i + 1:02d}",
                slug=f"pachka-{token}-{i}",
                body=f"Текст пачки {i}.",
                is_published="1",
            )
        page = client.get("/avtor").text
        assert f"Пачка {token} 6" in page
        assert f"Пачка {token} 1" in page
        assert f"Пачка {token} 0" not in page
        assert "поездку ещё не увидели" in page
        assert f'href="/poezdki/pachka-{token}-6"' in page
        full = client.get("/poezdki").text
        assert f"Пачка {token} 0" in full
        assert f"Пачка {token} 6" in full
        assert "author-hero" not in full
    finally:
        if published_ids:
            with engine.begin() as conn:
                for trip_id in published_ids:
                    conn.execute(text(
                        "UPDATE author_trips SET is_published = true WHERE id = :i"
                    ), {"i": trip_id})


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


def test_admin_slug_change_redirects_old_trip_slug(client):
    token = _uid()
    loc = _save(client, title=f"Слаг {token}", is_published="1")
    trip_id = int(re.search(r"/admin/poezdki/(\d+)", loc).group(1))
    with SessionLocal() as db:
        first = db.execute(text("SELECT slug FROM author_trips WHERE id=:i"), {"i": trip_id}).scalar()

    def rename(slug):
        r = client.post("/admin/poezdki/save", data={
            "id": str(trip_id), "title": f"Слаг {token}", "trip_date": "2026-04-02",
            "slug": slug, "body": "Текст для проверки слага.", "is_published": "1",
            "photo_url": "", "photo_alt": "",
        }, auth=AUTH, follow_redirects=False)
        assert r.status_code == 303, r.text

    second = f"slag-dva-{token}"
    third = f"slag-tri-{token}"
    rename(second)
    with SessionLocal() as db:
        stored = db.execute(text(
            "SELECT entity_id FROM slug_redirects WHERE kind = 'trip' AND old_slug = :s"
        ), {"s": first}).scalar()
    assert stored == trip_id
    old = client.get(f"/poezdki/{first}", follow_redirects=False)
    assert old.status_code == 301 and old.headers["location"] == f"/poezdki/{second}"

    rename(third)
    for previous in (first, second):
        again = client.get(f"/poezdki/{previous}", follow_redirects=False)
        assert again.status_code == 301 and again.headers["location"] == f"/poezdki/{third}"
        with SessionLocal() as db:
            assert db.execute(text(
                "SELECT entity_id FROM slug_redirects WHERE kind = 'trip' AND old_slug = :s"
            ), {"s": previous}).scalar() == trip_id
    page = client.get(f"/poezdki/{third}", follow_redirects=False)
    assert page.status_code == 200
    assert f'<link rel="canonical" href="{SITE_URL}/poezdki/{third}">' in page.text
    locs = _locs(client.get("/sitemap.xml").text)
    assert SITE_URL + f"/poezdki/{third}" in locs
    assert SITE_URL + f"/poezdki/{first}" not in locs
    assert SITE_URL + f"/poezdki/{second}" not in locs


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
        lowered = desc.lower()
        # Цифры экскурсии из «Кубанских новостей» на карточку не переносим —
        # это вопрос владельцу, не факт карточки.
        for banned in ("3,4", "3.4", "три часа", "3 часа", "апрел", "октябр", "километр", "км"):
            assert banned not in lowered
        assert "₽" not in desc
        direct = client.get(f"/mesta/{row.slug}", follow_redirects=False)
        by_id = client.get(f"/mesta/{row.id}", follow_redirects=False)
        assert direct.status_code == 404 and by_id.status_code == 404
        assert "База Эльна" not in direct.text and "3,4" not in direct.text
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
