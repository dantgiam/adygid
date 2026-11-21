"""Источники #39 в «Коротко для поездки»: запись при старте, защита правок админки, откат.

Сид 19.11 копирует блок один раз. Эти тесты проверяют, что повторный старт
переписывает rows ровно у семи карточек и только пока updated_by = «перенос из кода».
"""
import json
import logging

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  — создаёт таблицы
from app.database import engine
from content.trip_sources_39 import apply as sources
from site_app import trip_facts

# Семнадцать новых адресов: по одному на карточку, даже если ссылка стоит
# на нескольких строках. У 29, 61 и 66 две ссылки (закрытие и плата) уже были.
NEW_LINKS = {
    52: ["https://pokolenie.adygheya.gov.ru/tourism/granitnyy-kanon-reki-beloy/"],
    45: [
        "https://belovodje.ru/contacts/",
        "https://belovodje.ru/museum/museum-excursions/",
    ],
    29: [
        "https://www.kavkazzapoved.ru/news/pochti-vse-letnie-marshruty-kavkazskogo-zapovednika-gde-pogoda-esche-pozvolyaet-sdelat",
        "https://www.kavkazzapoved.ru/punkty-vydachi-propuskov",
        "https://www.kavkazzapoved.ru/pravila",
        "https://www.kavkazzapoved.ru/routes/no30-v-k-priyutu-fisht-cherez-ozero-psenodakh",
    ],
    50: ["https://pokolenie.adygheya.gov.ru/tourism/savranskaya-kanatnaya-doroga/"],
    61: [
        "https://www.kavkazzapoved.ru/news/pochti-vse-letnie-marshruty-kavkazskogo-zapovednika-gde-pogoda-esche-pozvolyaet-sdelat",
        "https://pokolenie.adygheya.gov.ru/tourism/gora-oshten/",
        "https://www.kavkazzapoved.ru/punkty-vydachi-propuskov",
        "https://www.kavkazzapoved.ru/pravila",
    ],
    66: [
        "https://www.kavkazzapoved.ru/news/pochti-vse-letnie-marshruty-kavkazskogo-zapovednika-gde-pogoda-esche-pozvolyaet-sdelat",
        "https://www.kavkazzapoved.ru/routes/no30-v-k-priyutu-fisht-cherez-ozero-psenodakh",
        "https://www.kavkazzapoved.ru/punkty-vydachi-propuskov",
        "https://www.kavkazzapoved.ru/pravila",
    ],
    75: ["https://pokolenie.adygheya.gov.ru/tourism/posyelok-ust-sakhray/"],
}
ALREADY = {
    29: [
        "https://www.kavkazzapoved.ru/news/s-27-oktyabrya-zakryvaetsya-chast-letnikh-turisticheskikh-marshrutov",
        "https://www.kavkazzapoved.ru/news/s-15-avgusta-v-kavkazskom-zapovednike-menyaetsya-stoimost-posescheniya-rekreacionnykh-obektov",
    ],
    61: [
        "https://www.kavkazzapoved.ru/news/s-27-oktyabrya-zakryvaetsya-chast-letnikh-turisticheskikh-marshrutov",
        "https://www.kavkazzapoved.ru/news/s-15-avgusta-v-kavkazskom-zapovednike-menyaetsya-stoimost-posescheniya-rekreacionnykh-obektov",
    ],
    66: [
        "https://www.kavkazzapoved.ru/news/s-27-oktyabrya-zakryvaetsya-chast-letnikh-turisticheskikh-marshrutov",
        "https://www.kavkazzapoved.ru/news/s-15-avgusta-v-kavkazskom-zapovednike-menyaetsya-stoimost-posescheniya-rekreacionnykh-obektov",
    ],
}

OLD_ROWS = [{
    "key": "hours", "label": "Часы работы", "text": "старый текст без ссылки",
    "verified": False, "checked_on": "", "source_url": "", "ld": {},
}]
ADMIN_ROWS = [{
    "key": "hours", "label": "Часы работы", "text": "правка админа",
    "verified": False, "checked_on": "", "source_url": "https://example.org/admin", "ld": {},
}]


def _urls(place_id: int) -> set:
    return {row["source_url"] for row in trip_facts.block_from_code(place_id)["rows"] if row.get("source_url")}


def test_code_has_seventeen_new_links_for_these_seven_places():
    assert sources.PLACE_IDS == (52, 45, 29, 50, 61, 66, 75)
    assert sources.MARKER == "trip-sources-39"
    assert sum(len(urls) for urls in NEW_LINKS.values()) == 17
    for pid, urls in NEW_LINKS.items():
        found = _urls(pid)
        assert set(urls) <= found, pid
        for url in ALREADY.get(pid, []):
            assert url in found, pid
    assert "winter" not in {row["key"] for row in trip_facts.block_from_code(75)["rows"]}


def test_startup_switch_off(monkeypatch):
    monkeypatch.setenv("APPLY_TRIP_SOURCES_39", "0")
    monkeypatch.delenv("ROLLBACK_TRIP_SOURCES_39", raising=False)
    assert sources.run_on_startup() == {"ran": False}


def test_startup_logs_summary_and_rollback_wins_over_switch(monkeypatch, caplog):
    monkeypatch.setenv("APPLY_TRIP_SOURCES_39", "0")
    monkeypatch.setenv("ROLLBACK_TRIP_SOURCES_39", "1")

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Eng:
        def begin(self):
            return Conn()

    monkeypatch.setattr("app.database.engine", Eng())
    monkeypatch.setattr(sources, "rollback", lambda conn: {"rolled_back": 4})
    invalidated = []
    monkeypatch.setattr(trip_facts, "invalidate", lambda: invalidated.append(1))
    with caplog.at_level(logging.WARNING, logger="adygid.trip_sources"):
        result = sources.run_on_startup()
    assert result == {"ran": "rollback", "rolled_back": 4}
    assert invalidated == [1]
    assert any("trip sources #39 rolled back" in rec.message for rec in caplog.records)

    monkeypatch.delenv("ROLLBACK_TRIP_SOURCES_39")
    monkeypatch.delenv("APPLY_TRIP_SOURCES_39")
    monkeypatch.setattr(sources, "apply", lambda conn: {
        "applied": 4, "kept_admin": 2, "missing": [75], "unchanged": 0, "total": 7,
    })
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="adygid.trip_sources"):
        applied = sources.run_on_startup()
    assert applied["ran"] is True and applied["applied"] == 4
    assert any("trip sources #39 applied" in rec.message for rec in caplog.records)

    monkeypatch.setattr(sources, "apply", lambda conn: {"skipped": "marker", "applied": 0})
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="adygid.trip_sources"):
        assert sources.run_on_startup()["skipped"] == "marker"
    assert not caplog.records


def test_startup_error_leaves_the_site_up(monkeypatch):
    monkeypatch.delenv("APPLY_TRIP_SOURCES_39", raising=False)
    monkeypatch.delenv("ROLLBACK_TRIP_SOURCES_39", raising=False)

    class Eng:
        def begin(self):
            raise RuntimeError("db down")

    monkeypatch.setattr("app.database.engine", Eng())
    assert sources.run_on_startup() == {"ran": True, "error": True}


@pytest.fixture()
def shadow():
    """Временные копии таблиц в pg_temp: запись не выходит за транзакцию теста."""
    conn = engine.connect()
    tx = conn.begin()
    for table in ("place_trip_blocks", "admin_text_history"):
        conn.execute(text(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"))
    yield conn
    tx.rollback()
    conn.close()


def _insert(conn, place_id, rows, author, seo_title="title из кода"):
    conn.execute(text(
        "INSERT INTO place_trip_blocks (place_id, enabled, seo_title, rows, combine_ids, auto_visit, "
        "search_facts, sources, updated_at, updated_by) "
        "VALUES (:pid, TRUE, :title, CAST(:rows AS jsonb), '[62]'::jsonb, TRUE, "
        "'{}'::jsonb, CAST(:src AS jsonb), now(), :author)"
    ), {
        "pid": place_id,
        "title": seo_title,
        "rows": json.dumps(rows, ensure_ascii=False),
        "src": json.dumps([{"title": "старый список", "url": "https://example.org/footer"}], ensure_ascii=False),
        "author": author,
    })


def _rows(conn, place_id):
    return conn.execute(text(
        "SELECT rows, updated_by, seo_title, sources, combine_ids FROM place_trip_blocks WHERE place_id = :pid"
    ), {"pid": place_id}).one()


def test_apply_once_keeps_admin_edits_and_rolls_back(shadow):
    conn = shadow
    for pid in (52, 29, 50, 66):
        _insert(conn, pid, OLD_ROWS, sources.SEEDED_BY)
    _insert(conn, 45, ADMIN_ROWS, "редактор")
    _insert(conn, 61, OLD_ROWS, None)
    _insert(conn, 24, OLD_ROWS, sources.SEEDED_BY, seo_title="чужая карточка")

    stats = sources.apply(conn)
    assert stats["applied"] == 4
    assert stats["applied_ids"] == [52, 29, 50, 66]
    assert stats["kept_admin"] == 2 and stats["kept_ids"] == [45, 61]
    assert stats["missing"] == [75]
    assert stats["unchanged"] == 0 and stats["total"] == 7

    for pid in (52, 29, 50, 66):
        rows, author, title, footer, combine = _rows(conn, pid)
        assert rows == trip_facts.block_from_code(pid)["rows"]
        assert author == sources.SEEDED_BY
        assert title == "title из кода"
        assert footer == [{"title": "старый список", "url": "https://example.org/footer"}]
        assert combine == [62]
        for url in NEW_LINKS[pid]:
            assert url in json.dumps(rows, ensure_ascii=False)
    assert _rows(conn, 45)[0] == ADMIN_ROWS
    assert _rows(conn, 61)[0] == OLD_ROWS and _rows(conn, 61)[1] is None
    assert _rows(conn, 24)[0] == OLD_ROWS and _rows(conn, 24)[2] == "чужая карточка"

    old_value, new_value = conn.execute(text(
        "SELECT old_value, new_value FROM admin_text_history "
        "WHERE entity = 'seed' AND entity_key = :m"
    ), {"m": sources.MARKER}).one()
    assert [item["place_id"] for item in old_value] == [52, 29, 50, 66]
    assert old_value[0]["rows"] == OLD_ROWS
    assert old_value[0]["new_rows"] == trip_facts.block_from_code(52)["rows"]
    assert new_value["applied_ids"] == [52, 29, 50, 66]

    # Метка стоит: очищенное поле следующий старт не заполняет заново.
    conn.execute(text("UPDATE place_trip_blocks SET rows = '[]'::jsonb WHERE place_id = 52"))
    assert sources.apply(conn) == {"skipped": "marker", "applied": 0}
    assert _rows(conn, 52)[0] == []

    # Правка после записи переживает откат. Остальные четыре возвращаются к снимку.
    conn.execute(text(
        "UPDATE place_trip_blocks SET rows = CAST(:rows AS jsonb) WHERE place_id = 52"
    ), {"rows": json.dumps(ADMIN_ROWS, ensure_ascii=False)})
    assert sources.rollback(conn) == {"rolled_back": 3}
    assert _rows(conn, 52)[0] == ADMIN_ROWS
    for pid in (29, 50, 66):
        assert _rows(conn, pid)[0] == OLD_ROWS
    assert _rows(conn, 45)[0] == ADMIN_ROWS
    assert _rows(conn, 24)[0] == OLD_ROWS
    assert sources.apply(conn)["skipped"] == "marker"


def test_already_current_rows_are_not_backed_up(shadow):
    conn = shadow
    for pid in sources.PLACE_IDS:
        _insert(conn, pid, trip_facts.block_from_code(pid)["rows"], sources.SEEDED_BY)
    stats = sources.apply(conn)
    assert stats["applied"] == 0 and stats["unchanged"] == 7 and stats["missing"] == []
    assert sources.rollback(conn) == {"rolled_back": 0}
    for pid in sources.PLACE_IDS:
        assert _rows(conn, pid)[0] == trip_facts.block_from_code(pid)["rows"]


def test_rollback_before_apply_does_not_block_the_sync(shadow):
    conn = shadow
    for pid in sources.PLACE_IDS:
        _insert(conn, pid, OLD_ROWS, sources.SEEDED_BY)
    assert sources.rollback(conn) == {"rolled_back": 0}
    stats = sources.apply(conn)
    assert stats["applied"] == 7
    assert _rows(conn, 52)[0] == trip_facts.block_from_code(52)["rows"]
