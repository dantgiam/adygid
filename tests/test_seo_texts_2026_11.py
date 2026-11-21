"""SEO-тексты 21.11.2026: данные, запись при старте, защита правок админки, откат.
И дописывание «Коротко для поездки» строке, перенесённой из кода без блока (место 30)."""
import json
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  — создаёт таблицы
from app.database import engine
from content.seo_texts_2026_11 import apply as seo_apply
from site_app import seo, trip_facts

ROOT = Path(__file__).resolve().parent.parent


def test_texts_are_63_unique_and_fit_lengths():
    rows = seo_apply.load_rows()
    assert len(rows) == 63
    assert Counter(r["kind"] for r in rows) == {"trail": 25, "article": 28, "scenario": 5, "district": 5}
    titles = [r["seo_title"].lower() for r in rows]
    assert len(set(titles)) == len(titles)
    for r in rows:
        assert len(r["seo_title"]) <= 60, r
        assert 120 <= len(r["seo_description"]) <= 160, r
        assert seo.normalize_seo_title(r["seo_title"]) == r["seo_title"]
        assert seo.normalize_seo_description(r["seo_description"]) == r["seo_description"]
        assert "бесплатн" not in (r["seo_title"] + r["seo_description"]).lower()
        assert r["seo_title"] != r["seo_title"].upper()


def test_rollback_sql_in_repo_matches_data():
    sql = (ROOT / "migrations" / "20261121_seo_texts_rollback.sql").read_text("utf-8")
    assert sql == seo_apply.sql_rollback()


def test_startup_switch_off(monkeypatch):
    monkeypatch.setenv("APPLY_SEO_TEXTS_2026_11", "0")
    monkeypatch.delenv("ROLLBACK_SEO_TEXTS_2026_11", raising=False)
    assert seo_apply.run_on_startup() == {"ran": False}


@pytest.fixture()
def shadow():
    """Временные копии таблиц в pg_temp: запись не выходит за транзакцию теста."""
    conn = engine.connect()
    tx = conn.begin()
    for t in ("articles", "trails", "scenarios", "districts", "admin_text_history"):
        conn.execute(text(f"CREATE TEMP TABLE {t} (LIKE public.{t} INCLUDING DEFAULTS)"))
    yield conn
    tx.rollback()
    conn.close()


def _rows():
    return [
        {"kind": "article", "table": "articles", "id": 1, "slug": "a", "old_seo_title": None,
         "old_seo_description": None, "seo_title": "Новый title статьи",
         "seo_description": "Новое описание статьи " * 4},
        {"kind": "scenario", "table": "scenarios", "id": 2, "slug": "s", "old_seo_title": None,
         "old_seo_description": "Старое описание сценария, которое было до правки, достаточно длинное.",
         "seo_title": "Новый title сценария", "seo_description": "Новое описание сценария " * 4},
        {"kind": "district", "table": "districts", "id": 3, "slug": "d", "old_seo_title": None,
         "old_seo_description": None, "seo_title": "Новый title округа",
         "seo_description": "Новое описание округа " * 4},
        {"kind": "trail", "table": "trails", "id": 4, "slug": "t", "old_seo_title": None,
         "old_seo_description": None, "seo_title": "Не тот slug", "seo_description": "Описание " * 10},
    ]


def _seed(conn):
    conn.execute(text("INSERT INTO articles (id, slug, seo_title, seo_description) VALUES (1, 'a', NULL, NULL)"))
    conn.execute(text("INSERT INTO scenarios (id, slug, seo_title, seo_description) VALUES "
                      "(2, 's', NULL, 'Старое описание сценария, которое было до правки, достаточно длинное.')"))
    # Округ уже поправили в админке: title не трогаем, пустое описание дописываем.
    conn.execute(text("INSERT INTO districts (id, slug, seo_title, seo_description) VALUES (3, 'd', 'Из админки', NULL)"))
    conn.execute(text("INSERT INTO trails (id, slug, seo_title, seo_description) VALUES (4, 'other', NULL, NULL)"))


def _get(conn, t, i):
    return tuple(conn.execute(text(f"SELECT seo_title, seo_description FROM {t} WHERE id = :i"), {"i": i}).one())


def _strip_not_null(conn):
    for t in ("articles", "trails", "scenarios", "districts"):
        cols = conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = :t "
            "AND table_schema LIKE 'pg_temp%' AND is_nullable = 'NO' AND column_name NOT IN ('id')"), {"t": t}).scalars()
        for c in cols:
            conn.execute(text(f'ALTER TABLE pg_temp.{t} ALTER COLUMN "{c}" DROP NOT NULL'))


def test_apply_once_keeps_admin_edits_and_rolls_back(shadow):
    conn = shadow
    _strip_not_null(conn)
    _seed(conn)
    rows = _rows()
    stats = seo_apply.apply(conn, rows)
    assert stats["applied"] == 3 and stats["missing"] == ["trail:4"]
    assert _get(conn, "articles", 1) == (rows[0]["seo_title"], rows[0]["seo_description"])
    assert _get(conn, "scenarios", 2) == (rows[1]["seo_title"], rows[1]["seo_description"])
    assert _get(conn, "districts", 3) == ("Из админки", rows[2]["seo_description"])
    assert _get(conn, "trails", 4) == (None, None)

    # Метка стоит: второй старт ничего не пишет, даже если поле потом очистили.
    conn.execute(text("UPDATE articles SET seo_title = NULL WHERE id = 1"))
    assert seo_apply.apply(conn, rows) == {"skipped": "marker", "applied": 0}
    assert _get(conn, "articles", 1)[0] is None

    # Правка в админке после записи переживает откат.
    conn.execute(text("UPDATE articles SET seo_title = 'Правка после' WHERE id = 1"))
    back = seo_apply.rollback(conn, rows)
    assert back["rolled_back"] == 3
    assert _get(conn, "articles", 1) == ("Правка после", None)
    assert _get(conn, "scenarios", 2) == (None, rows[1]["old_seo_description"])
    assert _get(conn, "districts", 3) == ("Из админки", None)

    # После отката повторный старт тексты не возвращает.
    assert seo_apply.apply(conn, rows)["skipped"] == "marker"


def test_rollback_sql_restores_old_values(shadow):
    conn = shadow
    _strip_not_null(conn)
    _seed(conn)
    rows = _rows()
    seo_apply.apply(conn, rows)
    for stmt in seo_apply.sql_rollback(rows).split(";\n"):
        s = "\n".join(ln for ln in stmt.splitlines() if not ln.startswith("--")).strip()
        if s and s not in ("BEGIN", "COMMIT", "COMMIT;"):
            conn.execute(text(s.replace(":", r"\:")))
    assert _get(conn, "scenarios", 2) == (None, rows[1]["old_seo_description"])
    assert _get(conn, "articles", 1) == (None, None)


@pytest.fixture()
def blocks():
    conn = engine.connect()
    tx = conn.begin()
    conn.execute(text("CREATE TEMP TABLE place_trip_blocks (LIKE public.place_trip_blocks INCLUDING ALL)"))
    yield conn
    tx.rollback()
    conn.close()


def _pre_row(conn, author):
    conn.execute(text(
        "INSERT INTO place_trip_blocks (place_id, enabled, seo_title, rows, combine_ids, auto_visit, "
        "search_facts, sources, updated_at, updated_by) "
        "VALUES (30, FALSE, 'title из кода', '[]'::jsonb, '[]'::jsonb, TRUE, '{}'::jsonb, '[]'::jsonb, now(), :a)"), {"a": author})


def test_seed_fills_block_for_row_moved_without_it(blocks):
    """Место 30 перенесли в базу, когда в коде был только title. Блок из PR #36 дописывается."""
    assert trip_facts.block_from_code(30)["rows"]
    _pre_row(blocks, "перенос из кода")
    trip_facts.seed_from_code(blocks)
    enabled, rows, comb, st = blocks.execute(text(
        "SELECT enabled, rows, combine_ids, seo_title FROM place_trip_blocks WHERE place_id = 30")).one()
    assert enabled is True and rows and comb == [46] and st == "title из кода"
    # Повторный старт ничего не меняет.
    before = blocks.execute(text("SELECT rows FROM place_trip_blocks WHERE place_id = 30")).scalar()
    trip_facts.seed_from_code(blocks)
    assert blocks.execute(text("SELECT rows FROM place_trip_blocks WHERE place_id = 30")).scalar() == before


def test_seed_keeps_row_edited_in_admin(blocks):
    _pre_row(blocks, "admin")
    trip_facts.seed_from_code(blocks)
    enabled, rows = blocks.execute(text("SELECT enabled, rows FROM place_trip_blocks WHERE place_id = 30")).one()
    assert enabled is False and rows == []
