"""Title районов: «Даховская: что посмотреть».

Живой title берётся из districts.seo_title. Проход 21.11.2026 записал туда
длинные формулировки, и словарь в site_app/seo.py их больше не перекрывает.
Здесь меняется только seo_title пяти районов.

Запись идёт при старте один раз:
  * строка ищется по id и slug;
  * поле пишется, только если оно пустое или в нём ещё старый автоматический
    title (снимок живой выдачи после SEO-текстов либо прежний словарь).
    Текст, который поправили в админке, не трогаем;
  * что стояло в поле до записи, кладётся в admin_text_history.old_value;
  * после прохода ставится метка (entity='seed',
    entity_key='district-look-titles-2026-11'). С меткой запись больше не
    запускается, поэтому откат не перетрётся следующим деплоем.
Откат: ROLLBACK_DISTRICT_LOOK_TITLES=1 на один деплой или
scripts/rollback_district_look_titles.sh с DATABASE_URL. Возвращает прежнее
значение только там, где ещё стоит наш текст. Описание района не меняется.
Ошибка записи сайт не роняет: транзакция откатывается, в лог уходит трейс.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("adygid.district_look")

MARKER = "district-look-titles-2026-11"
AUTHOR = "Заголовки районов 2026-11"
_LOCK = 20261122

# replace — значения, которые можно сменить. Пустая строка покрывает NULL.
# restore_title — что было в живой выдаче 21.11.2026 после SEO-текстов.
# Его пишет SQL-откат. Откат из кода берёт фактическое значение из метки.
ROWS = [
    {
        "id": 1,
        "slug": "maikop",
        "new_title": "Майкоп и окрестности: что посмотреть",
        "restore_title": "Майкоп и окрестности: что посмотреть и где термы",
        "replace": [
            "",
            "Майкоп и окрестности: что посмотреть и где термы",
            "Майкоп и окрестности: что посмотреть за день — АдыГид",
        ],
    },
    {
        "id": 2,
        "slug": "khadzhokh",
        "new_title": "Хаджох (Каменномостский): что посмотреть",
        "restore_title": "Каменномостский (Хаджох): что посмотреть рядом",
        "replace": [
            "",
            "Каменномостский (Хаджох): что посмотреть рядом",
            "Каменномостский (Хаджох): что посмотреть — АдыГид",
        ],
    },
    {
        "id": 3,
        "slug": "dakhovskaya",
        "new_title": "Даховская: что посмотреть",
        "restore_title": "Даховская: что посмотреть и куда съездить",
        "replace": [
            "",
            "Даховская: что посмотреть и куда съездить",
            "Даховская: что посмотреть и куда съездить — АдыГид",
        ],
    },
    {
        "id": 4,
        "slug": "lagonaki",
        "new_title": "Плато Лаго-Наки: что посмотреть",
        "restore_title": "Лаго-Наки: как доехать, смотровые и прогулки",
        "replace": [
            "",
            "Лаго-Наки: как доехать, смотровые и прогулки",
            "Лаго-Наки: дорога, смотровые и прогулки — АдыГид",
        ],
    },
    {
        "id": 5,
        "slug": "guzeripl",
        "new_title": "Гузерипль: что посмотреть",
        "restore_title": "Гузерипль: что посмотреть у входа в заповедник",
        "replace": [
            "",
            "Гузерипль: что посмотреть у входа в заповедник",
            "Гузерипль: достопримечательности и прогулки — АдыГид",
        ],
    },
]


def _check(rows: list[dict]) -> None:
    from site_app import seo
    seen = set()
    for r in rows:
        seo.normalize_seo_title(r["new_title"])
        assert r["new_title"] == seo.district_look(seo.DISTRICT_DISPLAY[r["slug"]])
        assert (r["id"], r["slug"]) not in seen
        seen.add((r["id"], r["slug"]))


def _backup_from_history(conn):
    from sqlalchemy import text
    raw = conn.execute(text(
        "SELECT old_value FROM admin_text_history "
        "WHERE entity = 'seed' AND entity_key = :m AND old_value IS NOT NULL "
        "ORDER BY id DESC LIMIT 1"
    ), {"m": MARKER}).scalar()
    if isinstance(raw, list) and raw:
        return raw
    return None


def apply(conn, rows: list[dict] | None = None) -> dict:
    """Пишет title в открытой транзакции conn. Повторный вызов с меткой — no-op."""
    from sqlalchemy import text
    rows = rows if rows is not None else ROWS
    _check(rows)
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    if conn.execute(text(
        "SELECT 1 FROM admin_text_history WHERE entity = 'seed' AND entity_key = :m"
    ), {"m": MARKER}).first():
        return {"skipped": "marker", "applied": 0}
    applied, kept, missing, backup = 0, [], [], []
    for r in rows:
        found = conn.execute(text(
            "SELECT seo_title FROM districts WHERE id = :id AND slug = :slug"
        ), {"id": r["id"], "slug": r["slug"]}).first()
        if not found:
            missing.append(f"district:{r['id']}")
            continue
        current = found[0]
        if (current or "") not in r["replace"]:
            kept.append(f"district:{r['id']}")
            continue
        names = {f"old{i}": value for i, value in enumerate(r["replace"])}
        placeholders = ", ".join(f":old{i}" for i in range(len(r["replace"])))
        res = conn.execute(text(
            "UPDATE districts SET seo_title = :new "
            f"WHERE id = :id AND slug = :slug AND coalesce(seo_title, '') IN ({placeholders})"
        ), {"id": r["id"], "slug": r["slug"], "new": r["new_title"], **names})
        if not res.rowcount:
            kept.append(f"district:{r['id']}")
            continue
        applied += 1
        backup.append({
            "id": r["id"], "slug": r["slug"],
            "seo_title": current, "new_title": r["new_title"],
        })
    conn.execute(text(
        "INSERT INTO admin_text_history (entity, entity_key, old_value, new_value, author) "
        "VALUES ('seed', :m, CAST(:old AS jsonb), CAST(:new AS jsonb), :author)"
    ), {
        "m": MARKER,
        "old": json.dumps(backup, ensure_ascii=False),
        "new": json.dumps({"applied": applied, "kept": kept, "missing": missing}, ensure_ascii=False),
        "author": AUTHOR,
    })
    return {"applied": applied, "kept_admin": len(kept), "missing": missing, "total": len(rows)}


def rollback(conn, rows: list[dict] | None = None) -> dict:
    """Возвращает прежний title там, где ещё стоит наш. Метку не снимает."""
    from sqlalchemy import text
    rows = rows if rows is not None else ROWS
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    items = _backup_from_history(conn)
    if items is None:
        items = [
            {"id": r["id"], "slug": r["slug"], "seo_title": r["restore_title"], "new_title": r["new_title"]}
            for r in rows
        ]
    n = 0
    for item in items:
        n += conn.execute(text(
            "UPDATE districts SET seo_title = :old "
            "WHERE id = :id AND slug = :slug AND seo_title = :new"
        ), {
            "old": item.get("seo_title"), "id": item["id"], "slug": item["slug"],
            "new": item["new_title"],
        }).rowcount or 0
    conn.execute(text(
        "INSERT INTO admin_text_history (entity, entity_key, new_value, author) "
        "VALUES ('seed', :m, CAST(:v AS jsonb), :author)"
    ), {"m": MARKER + ":rollback", "v": json.dumps({"rolled_back": n}), "author": AUTHOR})
    return {"rolled_back": n}


def sql_rollback(rows: list[dict] | None = None) -> str:
    """Тот же откат одним SQL-файлом для psql. Возвращает живые title 21.11.2026."""
    rows = rows if rows is not None else ROWS
    q = lambda s: "NULL" if s is None else "'" + s.replace("'", "''") + "'"
    out = [
        "-- Откат заголовков районов «что посмотреть».",
        "-- Трогает seo_title, только если там ещё наш текст. Описание не меняет.",
        "BEGIN;",
    ]
    for r in rows:
        out.append(
            "UPDATE districts SET "
            f"seo_title = CASE WHEN seo_title = {q(r['new_title'])} THEN {q(r['restore_title'])} ELSE seo_title END "
            f"WHERE id = {r['id']} AND slug = {q(r['slug'])};"
        )
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def run_on_startup() -> dict:
    """Вызов из app/main.py. Выключатель: APPLY_DISTRICT_LOOK_TITLES=0."""
    from app.database import engine
    try:
        if os.getenv("ROLLBACK_DISTRICT_LOOK_TITLES") == "1":
            with engine.begin() as conn:
                stats = rollback(conn)
            log.warning("district look titles rolled back: %s", stats)
            return {"ran": "rollback", **stats}
        if os.getenv("APPLY_DISTRICT_LOOK_TITLES") == "0":
            return {"ran": False}
        with engine.begin() as conn:
            stats = apply(conn)
    except Exception:
        log.exception("district look titles apply failed, database left unchanged")
        return {"ran": True, "error": True}
    if stats.get("skipped") != "marker":
        log.warning("district look titles applied: %s", stats)
    return {"ran": True, **stats}
