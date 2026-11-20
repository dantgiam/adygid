"""SEO-тексты статей, маршрутов, округов и сценариев правятся в админке.

Приоритет: поле из админки, затем словарь в site_app/seo.py, затем формула
шаблона. Длины как у мест: title до 80 (рекомендуем 60), description
от 60 до 230 (рекомендуем 160). Пустое поле — не ошибка.
"""
import json
import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from site_app import seo
from site_app.router import SITE_URL, _DISTRICT_CACHE

AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])


@pytest.fixture()
def client():
    return TestClient(app)


def _mark():
    return uuid.uuid4().hex[:8]


def _text(n):
    """Ровно n знаков без пробелов по краям: нормализация длины их не съест."""
    return ("Адыгея" * ((n // 6) + 2))[:n]


def _title(n):
    return _text(n)


def _desc(n):
    return _text(n)


def _meta(html):
    def one(pattern):
        m = re.search(pattern, html)
        assert m, pattern
        return m.group(1)

    return {
        "title": one(r"<title>(.*?)</title>"),
        "description": one(r'<meta name="description" content="([^"]*)"'),
        "og_title": one(r'<meta property="og:title" content="([^"]*)"'),
        "og_description": one(r'<meta property="og:description" content="([^"]*)"'),
        "canonical": one(r'<link rel="canonical" href="([^"]*)"'),
        "og_url": one(r'<meta property="og:url" content="([^"]*)"'),
    }


def _create(client, kind, **extra):
    mark = _mark()
    if kind == "article":
        body = {
            "title": f"Статья {mark}",
            "slug": f"seo-a-{mark}",
            "excerpt": "Анонс статьи для карточки.",
            "body": "<p>Текст статьи для запасного описания.</p>",
        }
        path = "/api/articles"
        page = f"/stati/seo-a-{mark}"
    elif kind == "trail":
        body = {
            "name": f"Маршрут {mark}",
            "description": "<p>Описание маршрута для запасного текста.</p>",
            "duration_minutes": 90,
            "is_paid": False,
        }
        path = "/api/trails"
        page = None
    elif kind == "district":
        body = {
            "name": f"Район {mark}",
            "slug": f"seo-d-{mark}",
            "lead": "Вступление района для запасного описания.",
        }
        path = "/api/districts"
        page = f"/okrugi/seo-d-{mark}"
    else:
        body = {
            "door": f"Дверь {mark}",
            "title": f"Сценарий {mark}",
            "slug": f"seo-s-{mark}",
            "lead": "<p>Текст сценария для запасного описания.</p>",
        }
        path = "/api/scenarios"
        page = f"/kuda/seo-s-{mark}"
    body.update(extra)
    r = client.post(path, json=body, auth=AUTH)
    return r, path, page, body


def test_length_constants_match_places():
    assert seo.SEO_TITLE_RECOMMENDED == 60
    assert seo.SEO_TITLE_MAX == 80
    assert seo.SEO_DESC_RECOMMENDED == 160
    assert seo.SEO_DESC_MIN == 60
    assert seo.SEO_DESC_MAX == 230
    assert seo.normalize_seo_title("  Мой   заголовок ") == "Мой заголовок"
    assert seo.normalize_seo_title("   ") is None
    assert seo.normalize_seo_title(_title(80)) == _title(80)
    with pytest.raises(ValueError):
        seo.normalize_seo_title(_title(81))
    assert seo.normalize_seo_description(_desc(60)) == _desc(60)
    assert seo.normalize_seo_description(_desc(230)) == _desc(230)
    assert seo.normalize_seo_description("  \n ") is None
    for bad in (59, 231):
        with pytest.raises(ValueError):
            seo.normalize_seo_description(_desc(bad))


def test_dictionaries_stay_in_code():
    assert "khadzhokh" in seo.DISTRICT_TITLES
    assert "tuman-na-lago-naki-kuda-ehat" in seo.ARTICLE_TITLES
    assert "bez-mashiny" in seo.SCENARIO_TITLES
    assert "zimoy" in seo.SCENARIO_TITLES


@pytest.mark.parametrize("kind", ["article", "trail", "district", "scenario"])
def test_api_rejects_title_and_description_outside_limits(client, kind):
    too_long, path, _, _ = _create(client, kind, seo_title=_title(81))
    assert too_long.status_code == 400, too_long.text
    assert "80" in too_long.text

    short, _, _, _ = _create(client, kind, seo_description=_desc(59))
    assert short.status_code == 400, short.text
    long, _, _, _ = _create(client, kind, seo_description=_desc(231))
    assert long.status_code == 400, long.text

    # Длиннее рекомендации, но в потолке — сохраняется.
    ok, _, _, _ = _create(client, kind, seo_title=_title(61), seo_description=_desc(161))
    assert ok.status_code == 201, ok.text
    saved = ok.json()
    assert saved["seo_title"] == _title(61)
    assert saved["seo_description"] == _desc(161)

    edges, _, _, _ = _create(client, kind, seo_title=_title(80), seo_description=_desc(60))
    assert edges.status_code == 201, edges.text
    top, _, _, _ = _create(client, kind, seo_description=_desc(230))
    assert top.status_code == 201, top.text

    empty, _, _, _ = _create(client, kind, seo_title="   ", seo_description="")
    assert empty.status_code == 201, empty.text
    assert empty.json()["seo_title"] is None
    assert empty.json()["seo_description"] is None


@pytest.mark.parametrize("kind,patch_key", [
    ("article", "/api/articles/{id}"),
    ("trail", "/api/trails/{id}"),
    ("district", "/api/districts/{id}"),
])
def test_patch_keeps_seo_when_key_omitted_and_clears_on_blank(client, kind, patch_key):
    created, _, _, _ = _create(client, kind, seo_title=_title(40), seo_description=_desc(80))
    assert created.status_code == 201, created.text
    obj = created.json()
    url = patch_key.format(id=obj["id"])

    kept = client.patch(url, json={"is_published": True}, auth=AUTH)
    assert kept.status_code == 200, kept.text
    assert kept.json()["seo_title"] == _title(40)
    assert kept.json()["seo_description"] == _desc(80)

    folded = client.patch(url, json={"seo_title": "  Свой   заголовок  "}, auth=AUTH)
    assert folded.status_code == 200, folded.text
    assert folded.json()["seo_title"] == "Свой заголовок"
    assert folded.json()["seo_description"] == _desc(80)

    cleared = client.patch(url, json={"seo_title": "", "seo_description": "   "}, auth=AUTH)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["seo_title"] is None
    assert cleared.json()["seo_description"] is None


def test_scenario_patch_keeps_title_when_key_omitted(client):
    created, _, _, body = _create(client, "scenario", seo_title=_title(40), seo_description=_desc(90))
    assert created.status_code == 201, created.text
    obj = created.json()
    # Форма сценария перезаписывает description всегда, а title — только
    # если ключ прислали: скрипт публикации его не знает.
    kept = client.patch(f"/api/scenarios/{obj['id']}", json={
        "door": body["door"], "title": body["title"], "slug": body["slug"],
        "lead": body["lead"], "seo_description": _desc(90),
    }, auth=AUTH)
    assert kept.status_code == 200, kept.text
    assert kept.json()["seo_title"] == _title(40)
    assert kept.json()["seo_description"] == _desc(90)

    cleared = client.patch(f"/api/scenarios/{obj['id']}", json={
        "door": body["door"], "title": body["title"], "seo_title": None,
    }, auth=AUTH)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["seo_title"] is None


def _assert_og_and_canonical(html, path):
    meta = _meta(html)
    assert meta["og_title"] == meta["title"]
    assert meta["og_description"] == meta["description"]
    assert meta["canonical"] == SITE_URL + path
    assert meta["og_url"] == meta["canonical"]
    return meta


def test_article_priority_admin_then_dictionary_then_template(client, monkeypatch):
    mark = _mark()
    slug = f"seo-a-{mark}"
    dict_title = "Словарь статьи: что посмотреть"
    monkeypatch.setitem(seo.ARTICLE_TITLES, slug, dict_title)
    title = f"Статья {mark}"
    excerpt = "Анонс статьи для карточки."
    r = client.post("/api/articles", json={
        "title": title, "slug": slug, "excerpt": excerpt, "body": "<p>Текст.</p>",
    }, auth=AUTH)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    path = f"/stati/{slug}"

    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == dict_title
    assert meta["description"] == excerpt
    assert f'<h1 class="article-title">{title}</h1>' in client.get(path).text

    custom_title = _title(50)
    custom_desc = _desc(100)
    saved = client.patch(f"/api/articles/{aid}", json={
        "seo_title": custom_title, "seo_description": custom_desc,
    }, auth=AUTH)
    assert saved.status_code == 200, saved.text
    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == custom_title
    assert meta["description"] == custom_desc
    assert title in client.get(path).text

    client.patch(f"/api/articles/{aid}", json={"seo_title": None, "seo_description": None}, auth=AUTH)
    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == dict_title
    assert meta["description"] == excerpt

    plain = f"seo-plain-{mark}"
    r = client.post("/api/articles", json={
        "title": title, "slug": plain, "body": "<p>Только текст статьи без анонса.</p>",
    }, auth=AUTH)
    assert r.status_code == 201, r.text
    html = client.get(f"/stati/{plain}").text
    meta = _assert_og_and_canonical(html, f"/stati/{plain}")
    assert meta["title"] == f"{title} — АдыГид"
    assert meta["description"] == "Только текст статьи без анонса."
    xml = client.get("/sitemap.xml").text
    assert f"{SITE_URL}/stati/{slug}" in xml
    assert custom_title not in xml


def test_district_priority_admin_then_dictionary_then_template(client, monkeypatch):
    mark = _mark()
    slug = f"seo-d-{mark}"
    name = f"Район {mark}"
    lead = "Вступление района для запасного описания."
    dict_title = "Словарь округа: что посмотреть"
    monkeypatch.setitem(seo.DISTRICT_TITLES, slug, dict_title)
    r = client.post("/api/districts", json={"name": name, "slug": slug, "lead": lead}, auth=AUTH)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    path = f"/okrugi/{slug}"
    _DISTRICT_CACHE["value"] = None

    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == dict_title
    assert meta["description"] == lead
    assert f'<h1 class="page-title">{name}</h1>' in client.get(path).text

    custom_title = _title(45)
    custom_desc = _desc(90)
    saved = client.patch(f"/api/districts/{did}", json={
        "seo_title": custom_title, "seo_description": custom_desc,
    }, auth=AUTH)
    assert saved.status_code == 200, saved.text
    _DISTRICT_CACHE["value"] = None
    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == custom_title
    assert meta["description"] == custom_desc

    client.patch(f"/api/districts/{did}", json={"seo_title": "", "seo_description": None}, auth=AUTH)
    _DISTRICT_CACHE["value"] = None
    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == dict_title
    assert meta["description"] == lead

    plain = f"seo-d-plain-{mark}"
    plain_name = f"Поляна {mark}"
    r = client.post("/api/districts", json={
        "name": plain_name, "slug": plain, "lead": lead,
    }, auth=AUTH)
    assert r.status_code == 201, r.text
    _DISTRICT_CACHE["value"] = None
    meta = _assert_og_and_canonical(client.get(f"/okrugi/{plain}").text, f"/okrugi/{plain}")
    assert meta["title"] == f"{plain_name} — что посмотреть и какие маршруты рядом"
    assert meta["description"] == lead

    # Уже засеянный округ без поля в админке остаётся на словаре.
    _DISTRICT_CACHE["value"] = None
    html = client.get("/okrugi/khadzhokh").text
    assert f"<title>{seo.DISTRICT_TITLES['khadzhokh']}</title>" in html


def test_scenario_priority_admin_then_dictionary_then_template(client, monkeypatch):
    mark = _mark()
    slug = f"seo-s-{mark}"
    title = f"Сценарий {mark}"
    dict_title = "Словарь сценария: куда поехать"
    monkeypatch.setitem(seo.SCENARIO_TITLES, slug, dict_title)
    lead = "<p>Текст сценария для запасного описания.</p>"
    r = client.post("/api/scenarios", json={
        "door": f"Дверь {mark}", "title": title, "slug": slug, "lead": lead,
    }, auth=AUTH)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    path = f"/kuda/{slug}"

    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == dict_title
    assert meta["description"] == "Текст сценария для запасного описания."
    assert f'<h1 class="page-title">{title}</h1>' in client.get(path).text

    custom_title = _title(42)
    custom_desc = _desc(110)
    saved = client.patch(f"/api/scenarios/{sid}", json={
        "door": f"Дверь {mark}", "title": title, "slug": slug, "lead": lead,
        "seo_title": custom_title, "seo_description": custom_desc,
    }, auth=AUTH)
    assert saved.status_code == 200, saved.text
    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == custom_title
    assert meta["description"] == custom_desc

    client.patch(f"/api/scenarios/{sid}", json={
        "door": f"Дверь {mark}", "title": title, "slug": slug, "lead": lead,
        "seo_title": None, "seo_description": None,
    }, auth=AUTH)
    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == dict_title
    assert meta["description"] == "Текст сценария для запасного описания."

    plain = f"seo-s-plain-{mark}"
    r = client.post("/api/scenarios", json={
        "door": "Дверь", "title": title, "slug": plain, "lead": lead,
    }, auth=AUTH)
    assert r.status_code == 201, r.text
    meta = _assert_og_and_canonical(client.get(f"/kuda/{plain}").text, f"/kuda/{plain}")
    assert meta["title"] == f"{title} — АдыГид"


def test_route_priority_admin_then_template(client):
    mark = _mark()
    name = f"Маршрут {mark}"
    r = client.post("/api/trails", json={
        "name": name,
        "description": "<p>Описание маршрута для запасного текста.</p>",
        "duration_minutes": 90,
        "is_paid": False,
    }, auth=AUTH)
    assert r.status_code == 201, r.text
    trail = r.json()
    path = trail["url"]
    fallback = f"{name} — 1 ч 30 мин, маршрут по Адыгее"
    excerpt = "Описание маршрута для запасного текста."

    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == fallback
    assert meta["description"] == excerpt
    assert f'<h1 class="page-title">{name}</h1>' in client.get(path).text

    custom_title = _title(48)
    custom_desc = _desc(120)
    saved = client.patch(f"/api/trails/{trail['id']}", json={
        "seo_title": custom_title, "seo_description": custom_desc,
    }, auth=AUTH)
    assert saved.status_code == 200, saved.text
    html = client.get(path).text
    meta = _assert_og_and_canonical(html, path)
    assert meta["title"] == custom_title
    assert meta["description"] == custom_desc
    assert fallback not in html
    # Разметка тура берёт то же описание, имя маршрута не подменяется title.
    blocks = [json.loads(b) for b in re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]
    trip = next(b for b in blocks if b.get("@type") == "TouristTrip")
    assert trip["name"] == name
    assert trip["description"] == custom_desc

    client.patch(f"/api/trails/{trail['id']}", json={"seo_title": None, "seo_description": None}, auth=AUTH)
    meta = _assert_og_and_canonical(client.get(path).text, path)
    assert meta["title"] == fallback
    assert meta["description"] == excerpt

    xml = client.get("/sitemap.xml").text
    assert f"{SITE_URL}{path}" in xml
    assert custom_title not in xml


def test_publish_script_does_not_overwrite_manual_seo():
    import importlib.util
    spec = importlib.util.spec_from_file_location("seo_publish_manual", "scripts/seo_content_publish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    manual_title = "Ручной title сценария"
    manual_desc = "О" * 90
    current = {
        "slug": "zimoy", "icon": "❄️", "door": "Зимой", "title": "Зимой", "lead": "старый",
        "seo_title": manual_title, "seo_description": manual_desc, "is_published": True,
    }
    payload = mod.scenario_payload(
        current, lead="новый", seo_title="Черновик скрипта", seo_description="Ч" * 90,
    )
    assert payload["lead"] == "новый"
    assert payload["seo_title"] == manual_title
    assert payload["seo_description"] == manual_desc
    # Пустое поле скрипт заполняет.
    empty = dict(current, seo_title="", seo_description=None)
    filled = mod.scenario_payload(empty, seo_title="Новый title", seo_description="Н" * 70)
    assert filled["seo_title"] == "Новый title"
    assert filled["seo_description"] == "Н" * 70
    # Статья: ключ в черновике заменяется ручным, отсутствующий ключ не появляется.
    article = mod.respect_manual_seo(
        {"title": "Черновик", "seo_description": "Д" * 80},
        {"seo_title": "Ручной title статьи", "seo_description": "Р" * 80},
    )
    assert article["seo_description"] == "Р" * 80
    assert "seo_title" not in article
    assert mod.keep_manual_seo("  уже в админке  ", "из черновика") == "  уже в админке  "
    assert mod.keep_manual_seo("   ", "из черновика") == "из черновика"


def test_legacy_scenario_description_warns_without_blocking_other_edits(client):
    created, _, _, body = _create(client, "scenario", seo_description=_desc(90))
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    legacy = "Коротко"
    from sqlalchemy import text
    from app.database import engine
    with engine.begin() as conn:
        conn.execute(text("UPDATE scenarios SET seo_description = :d WHERE id = :id"), {"d": legacy, "id": sid})

    kept = client.patch(f"/api/scenarios/{sid}", json={
        "door": "Новая дверь", "title": body["title"], "lead": body["lead"],
        "seo_description": "  Коротко  ",
    }, auth=AUTH)
    assert kept.status_code == 200, kept.text
    assert kept.json()["door"] == "Новая дверь"
    assert kept.json()["seo_description"] == legacy
    assert "60" in kept.json()["seo_warning"] and "230" in kept.json()["seo_warning"]

    omitted = client.patch(f"/api/scenarios/{sid}", json={
        "door": "Ещё дверь", "title": body["title"], "lead": body["lead"],
    }, auth=AUTH)
    assert omitted.status_code == 200, omitted.text
    assert omitted.json()["seo_description"] == legacy
    assert omitted.json()["seo_warning"]

    changed = client.patch(f"/api/scenarios/{sid}", json={
        "door": "Ещё дверь", "title": body["title"], "lead": body["lead"],
        "seo_description": "Другой короткий текст",
    }, auth=AUTH)
    assert changed.status_code == 400, changed.text
    still = client.get("/api/scenarios", auth=AUTH).json()
    row = next(s for s in still if s["id"] == sid)
    assert row["seo_description"] == legacy

    ok = client.patch(f"/api/scenarios/{sid}", json={
        "door": "Ещё дверь", "title": body["title"], "lead": body["lead"],
        "seo_description": _desc(80),
    }, auth=AUTH)
    assert ok.status_code == 200, ok.text
    assert ok.json()["seo_description"] == _desc(80)
    assert "seo_warning" not in ok.json()


def test_admin_form_shows_live_counter_and_60_160_hint():
    html = open("static/admin.html", encoding="utf-8").read()
    js = open("static/admin.js", encoding="utf-8").read()
    assert html.count("Рекомендуем 60 знаков") >= 3
    assert html.count("Рекомендуем 160 знаков") >= 3
    assert "paintSeoCounts" in js and "SEO_TITLE_REC = 60" in js and "SEO_DESC_REC = 160" in js
    assert "n / ${rec}" in js or "`· ${n} / ${rec}`" in js
    assert 'id="sc-seo-warn"' in html
