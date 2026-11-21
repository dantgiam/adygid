"""Ссылки «источник» в «Коротко для поездки» у семи карточек из #39.

#39 обновил строки seo.PLACE_PRACTICAL (52, 45, 29, 50, 61, 66, 75).
С 19.11 блок живёт в place_trip_blocks: сид копирует код один раз
(ON CONFLICT DO NOTHING), и правка в коде на уже залитую строку не
попадает. На живых страницах нет новых ссылок.

Запись идёт при старте один раз, после сида:
  * только эти семь place_id, только колонка rows (текст строки и
    source_url). title, «с чем совместить» и список под таблицей не
    трогаем;
  * строку пишем, только если её не правили в админке: updated_by всё
    ещё «перенос из кода». Чужое имя автора — строка остаётся как есть;
  * прежние rows кладутся в admin_text_history.old_value;
  * после прохода ставится метка (entity='seed',
    entity_key='trip-sources-39'). С меткой запись больше не
    запускается, поэтому откат не перетрётся следующим деплоем.
Откат: ROLLBACK_TRIP_SOURCES_39=1 на один деплой. Возвращает сохранённые
rows только там, где всё ещё стоит наш текст и updated_by не менялся.
Ошибка записи сайт не роняет: транзакция откатывается, в лог уходит трейс.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("adygid.trip_sources")

MARKER = "trip-sources-39"
AUTHOR = "источники #39"
SEEDED_BY = "перенос из кода"
# Порядок — как в задаче: ровно эти карточки, никакие другие.
PLACE_IDS = (52, 45, 29, 50, 61, 66, 75)
_LOCK = 20261139


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _norm(rows) -> str:
    return json.dumps(rows or [], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _check(place_ids: list[int]) -> None:
    from site_app import trip_facts
    assert list(place_ids) == list(PLACE_IDS)
    for pid in place_ids:
        block = trip_facts.block_from_code(pid)
        assert block and any(
            (row.get("source_url") or "").startswith("https://") for row in block["rows"]
        ), pid


def _code_rows(place_id: int) -> list:
    from site_app import trip_facts
    return trip_facts.block_from_code(place_id)["rows"]


def _backup_from_history(conn):
    from sqlalchemy import text
    raw = conn.execute(text(
        "SELECT old_value FROM admin_text_history "
        "WHERE entity = 'seed' AND entity_key = :m AND old_value IS NOT NULL "
        "ORDER BY id DESC LIMIT 1"
    ), {"m": MARKER}).scalar()
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, list):
        return raw
    return None


def apply(conn, place_ids: list[int] | None = None) -> dict:
    """Пишет rows в открытой транзакции conn. Повторный вызов с меткой — no-op."""
    from sqlalchemy import text
    ids = list(place_ids if place_ids is not None else PLACE_IDS)
    _check(ids)
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    if conn.execute(text(
        "SELECT 1 FROM admin_text_history WHERE entity = 'seed' AND entity_key = :m"
    ), {"m": MARKER}).first():
        return {"skipped": "marker", "applied": 0}
    applied, kept, missing, unchanged, backup = [], [], [], [], []
    for pid in ids:
        new_rows = _code_rows(pid)
        found = conn.execute(text(
            "SELECT rows, updated_by FROM place_trip_blocks WHERE place_id = :pid"
        ), {"pid": pid}).first()
        if not found:
            missing.append(pid)
            continue
        current, author = found[0], found[1]
        if author != SEEDED_BY:
            kept.append(pid)
            continue
        if _norm(current) == _norm(new_rows):
            unchanged.append(pid)
            continue
        res = conn.execute(text(
            "UPDATE place_trip_blocks SET rows = CAST(:rows AS jsonb), updated_at = now() "
            "WHERE place_id = :pid AND updated_by = :by"
        ), {"pid": pid, "by": SEEDED_BY, "rows": _dumps(new_rows)})
        if not res.rowcount:
            kept.append(pid)
            continue
        applied.append(pid)
        backup.append({"place_id": pid, "rows": current or [], "new_rows": new_rows})
    stats = {
        "applied": len(applied),
        "applied_ids": applied,
        "kept_admin": len(kept),
        "kept_ids": kept,
        "missing": missing,
        "unchanged": len(unchanged),
        "unchanged_ids": unchanged,
        "total": len(ids),
    }
    conn.execute(text(
        "INSERT INTO admin_text_history (entity, entity_key, old_value, new_value, author) "
        "VALUES ('seed', :m, CAST(:old AS jsonb), CAST(:new AS jsonb), :author)"
    ), {"m": MARKER, "old": _dumps(backup), "new": _dumps(stats), "author": AUTHOR})
    return stats


def rollback(conn) -> dict:
    """Возвращает сохранённые rows там, где ещё стоит наш текст. Метку не снимает."""
    from sqlalchemy import text
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    items = _backup_from_history(conn) or []
    n = 0
    for item in items:
        n += conn.execute(text(
            "UPDATE place_trip_blocks SET rows = CAST(:old AS jsonb), updated_at = now() "
            "WHERE place_id = :pid AND updated_by = :by AND rows = CAST(:new AS jsonb)"
        ), {
            "pid": item["place_id"],
            "by": SEEDED_BY,
            "old": _dumps(item.get("rows") or []),
            "new": _dumps(item.get("new_rows") or []),
        }).rowcount or 0
    conn.execute(text(
        "INSERT INTO admin_text_history (entity, entity_key, new_value, author) "
        "VALUES ('seed', :m, CAST(:v AS jsonb), :author)"
    ), {"m": MARKER + ":rollback", "v": _dumps({"rolled_back": n}), "author": AUTHOR})
    return {"rolled_back": n}


def run_on_startup() -> dict:
    """Вызов из app/main.py. Выключатель: APPLY_TRIP_SOURCES_39=0.

    Откат важнее выключателя: ROLLBACK_TRIP_SOURCES_39=1 возвращает
    сохранённые строки даже если запись выключена.
    """
    from app.database import engine
    try:
        if os.getenv("ROLLBACK_TRIP_SOURCES_39") == "1":
            with engine.begin() as conn:
                stats = rollback(conn)
            log.warning("trip sources #39 rolled back: %s", stats)
            from site_app import trip_facts
            trip_facts.invalidate()
            return {"ran": "rollback", **stats}
        if os.getenv("APPLY_TRIP_SOURCES_39") == "0":
            return {"ran": False}
        with engine.begin() as conn:
            stats = apply(conn)
    except Exception:
        log.exception("trip sources #39 apply failed, database left unchanged")
        return {"ran": True, "error": True}
    if stats.get("skipped") != "marker":
        log.warning("trip sources #39 applied: %s", stats)
        from site_app import trip_facts
        trip_facts.invalidate()
    return {"ran": True, **stats}
