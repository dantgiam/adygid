"""Заголовки районов «{район}: что посмотреть»: страница, карточка, запись в базу."""
import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main  # noqa: F401  — создаёт таблицы
from app.database import engine
from app.main import app
from content.district_look_2026_11 import apply as look
from site_app import seo
from site_app.router import _DISTRICT_CACHE

ROOT = Path(__file__).resolve().parent.parent
AUTH = (os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])


def _ld_blocks(html: str) -> list:
    return [json.loads(b) for b in re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


def test_titles_match_display_names_and_stay_short():
    assert look.MARKER == "district-look-titles-2026-11"
    assert {r["slug"] for r in look.ROWS} == set(seo.DISTRICT_DISPLAY)
    for r in look.ROWS:
        title = r["new_title"]
        assert title == seo.DISTRICT_TITLES[r["slug"]]
        assert seo.normalize_seo_title(title) == title
        assert len(title) <= 60
        assert "—" not in title
        assert r["restore_title"] not in ("", title)
        assert "" in r["replace"] and r["restore_title"] in r["replace"]
    assert seo.district_look("Даховская: что посмотреть") == "Даховская: что посмотреть"
    assert seo.district_look("  Даховская  ") == "Даховская: что посмотреть"
    assert seo.district_look("") == "Что посмотреть"


def test_rollback_sql_in_repo_matches_data():
    sql = (ROOT / "migrations" / "20261121_district_look_titles_rollback.sql").read_text("utf-8")
    assert sql == look.sql_rollback()
    assert "seo_description" not in sql


def test_startup_switch_off(monkeypatch):
    monkeypatch.setenv("APPLY_DISTRICT_LOOK_TITLES", "0")
    monkeypatch.delenv("ROLLBACK_DISTRICT_LOOK_TITLES", raising=False)
    assert look.run_on_startup() == {"ran": False}


@pytest.fixture()
def client():
    return TestClient(app)


def test_pages_cards_keep_short_names_in_nav_and_crumbs(client):
    _DISTRICT_CACHE["value"] = None
    with engine.connect() as conn:
        stored = dict(conn.execute(text("SELECT slug, name FROM districts")).all())
    listing = client.get("/okrugi").text
    assert ">Районы<" in listing
    assert 'class="grid districts-grid"' in listing
    places = client.get("/mesta").text
    for slug in seo.DISTRICT_DISPLAY:
        label = seo.district_display(slug, stored[slug])
        phrase = seo.district_look(label)
        # Пустое поле в базе: вкладка берётся из словаря. На проде имя
        # совпадает со словарём; в тестовом сиде у Лаго-Наки старая строка.
        assert f"<h3>{phrase}</h3>" in listing
        html = client.get(f"/okrugi/{slug}").text
        assert f"<title>{seo.DISTRICT_TITLES[slug]}</title>" in html
        assert f'<meta property="og:title" content="{seo.DISTRICT_TITLES[slug]}">' in html
        assert f'<h1 class="page-title">{phrase}</h1>' in html
        assert '<p class="eyebrow"><a href="/okrugi" style="color:inherit">Районы</a></p>' in html
        blocks = _ld_blocks(html)
        place = next(b for b in blocks if b.get("@type") == "Place")
        assert place["name"] == label
        crumbs = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
        assert crumbs["itemListElement"][-1]["name"] == label
        assert f">{label}</option>" in places
        assert f">{phrase}</option>" not in places


@pytest.fixture()
def shadow():
    """Временные копии таблиц в pg_temp: запись не выходит за транзакцию теста."""
    conn = engine.connect()
    tx = conn.begin()
    for t in ("districts", "admin_text_history"):
        conn.execute(text(f"CREATE TEMP TABLE {t} (LIKE public.{t} INCLUDING DEFAULTS)"))
    cols = conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'districts' "
        "AND table_schema LIKE 'pg_temp%' AND is_nullable = 'NO' AND column_name NOT IN ('id')"
    )).scalars()
    for c in cols:
        conn.execute(text(f'ALTER TABLE pg_temp.districts ALTER COLUMN "{c}" DROP NOT NULL'))
    yield conn
    tx.rollback()
    conn.close()


def _title(conn, slug):
    return conn.execute(
        text("SELECT seo_title, seo_description FROM districts WHERE slug = :s"), {"s": slug}
    ).one()


def test_apply_once_keeps_admin_edits_and_rolls_back(shadow):
    conn = shadow
    by_slug = {r["slug"]: r for r in look.ROWS}
    conn.execute(text(
        "INSERT INTO districts (id, slug, name, seo_title, seo_description) VALUES "
        "(1, 'maikop', 'Округ Майкопа', :live, 'описание майкопа'), "
        "(2, 'other', 'чужой', NULL, NULL), "
        "(3, 'dakhovskaya', 'Округ Даховской', NULL, 'описание даховской'), "
        "(4, 'lagonaki', 'Плато Лаго-Наки', 'Из админки', 'описание плато'), "
        "(5, 'guzeripl', 'Округ Гузерипля', :old_dict, 'описание гузерипля')"
    ), {
        "live": by_slug["maikop"]["restore_title"],
        "old_dict": "Гузерипль: достопримечательности и прогулки — АдыГид",
    })
    stats = look.apply(conn)
    assert stats["applied"] == 3
    assert stats["missing"] == ["district:2"]
    assert stats["kept_admin"] == 1
    assert _title(conn, "maikop") == (by_slug["maikop"]["new_title"], "описание майкопа")
    assert _title(conn, "dakhovskaya") == (by_slug["dakhovskaya"]["new_title"], "описание даховской")
    assert _title(conn, "guzeripl") == (by_slug["guzeripl"]["new_title"], "описание гузерипля")
    assert _title(conn, "lagonaki") == ("Из админки", "описание плато")
    assert _title(conn, "other") == (None, None)

    conn.execute(text("UPDATE districts SET seo_title = NULL WHERE slug = 'maikop'"))
    assert look.apply(conn) == {"skipped": "marker", "applied": 0}
    assert _title(conn, "maikop")[0] is None

    # Правка после записи переживает откат. Пустое поле и старый словарь возвращаются.
    conn.execute(text("UPDATE districts SET seo_title = 'Правка после' WHERE slug = 'maikop'"))
    back = look.rollback(conn)
    assert back["rolled_back"] == 2
    assert _title(conn, "maikop") == ("Правка после", "описание майкопа")
    assert _title(conn, "dakhovskaya") == (None, "описание даховской")
    assert _title(conn, "guzeripl") == (
        "Гузерипль: достопримечательности и прогулки — АдыГид", "описание гузерипля")
    assert _title(conn, "lagonaki") == ("Из админки", "описание плато")
    assert look.apply(conn)["skipped"] == "marker"


def test_rollback_sql_restores_live_titles(shadow):
    conn = shadow
    by_slug = {r["slug"]: r for r in look.ROWS}
    conn.execute(text(
        "INSERT INTO districts (id, slug, name, seo_title, seo_description) VALUES "
        "(1, 'maikop', 'Округ Майкопа', :live, 'описание'), "
        "(3, 'dakhovskaya', 'Округ Даховской', 'Из админки', 'описание')"
    ), {"live": by_slug["maikop"]["restore_title"]})
    look.apply(conn)
    for stmt in look.sql_rollback().split(";\n"):
        s = "\n".join(ln for ln in stmt.splitlines() if not ln.startswith("--")).strip()
        if s and s not in ("BEGIN", "COMMIT", "COMMIT;"):
            conn.execute(text(s.replace(":", r"\:")))
    assert _title(conn, "maikop") == (by_slug["maikop"]["restore_title"], "описание")
    assert _title(conn, "dakhovskaya") == ("Из админки", "описание")
