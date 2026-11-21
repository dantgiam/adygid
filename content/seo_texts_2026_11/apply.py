"""SEO title/description для 63 страниц: 25 маршрутов, 28 статей, 5 сценариев, 5 округов.

Тексты лежат в texts.json рядом. Там же старые значения колонок (снимок
21.11.2026), по ним работает и защита, и откат.

Запись идёт при старте сайта один раз:
  * строка ищется по id и slug;
  * поле пишется, только если в базе пусто или стоит старое значение из
    снимка. Текст, который успели поправить в админке, не трогаем;
  * после прохода ставится метка в admin_text_history
    (entity='seed', entity_key='seo-texts-2026-11'). С меткой запись больше не
    запускается, поэтому откат не перетрётся следующим деплоем.
Откат: ROLLBACK_SEO_TEXTS_2026_11=1 на один деплой или
scripts/rollback_seo_texts.sh с DATABASE_URL. Возвращает старые значения
только там, где ещё стоит наш текст.
Ошибка записи сайт не роняет: транзакция откатывается, в лог уходит трейс.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger("adygid.seo_texts")

MARKER = "seo-texts-2026-11"
TABLES = {"article": "articles", "trail": "trails", "scenario": "scenarios", "district": "districts"}
_LOCK = 20261121
_DIR = Path(__file__).resolve().parent


def load_rows() -> list[dict]:
    return json.loads((_DIR / "texts.json").read_text("utf-8"))


def _check(rows: list[dict]) -> None:
    from site_app import seo
    seen = set()
    for r in rows:
        assert r["table"] == TABLES[r["kind"]]
        seo.normalize_seo_title(r["seo_title"])          # бросает ValueError, если длина не та
        seo.normalize_seo_description(r["seo_description"])
        assert (r["kind"], r["id"]) not in seen
        seen.add((r["kind"], r["id"]))


_FORWARD = (
    "UPDATE {t} SET "
    " seo_title = CASE WHEN coalesce(seo_title, '') IN ('', :old_t) THEN :new_t ELSE seo_title END,"
    " seo_description = CASE WHEN coalesce(seo_description, '') IN ('', :old_d) THEN :new_d ELSE seo_description END "
    "WHERE id = :id AND slug = :slug "
    " AND (coalesce(seo_title, '') IN ('', :old_t) OR coalesce(seo_description, '') IN ('', :old_d))"
)
_BACK = (
    "UPDATE {t} SET "
    " seo_title = CASE WHEN seo_title = :new_t THEN :old_t_null ELSE seo_title END,"
    " seo_description = CASE WHEN seo_description = :new_d THEN :old_d_null ELSE seo_description END "
    "WHERE id = :id AND slug = :slug AND (seo_title = :new_t OR seo_description = :new_d)"
)


def _params(r: dict) -> dict:
    return {"id": r["id"], "slug": r["slug"], "new_t": r["seo_title"], "new_d": r["seo_description"],
            "old_t": r["old_seo_title"] or "", "old_d": r["old_seo_description"] or "",
            "old_t_null": r["old_seo_title"], "old_d_null": r["old_seo_description"]}


def apply(conn, rows: list[dict] | None = None, force: bool = False) -> dict:
    """Пишет тексты в открытой транзакции conn. Повторный вызов с меткой — no-op."""
    from sqlalchemy import text
    rows = rows if rows is not None else load_rows()
    _check(rows)
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    if not force and conn.execute(text(
        "SELECT 1 FROM admin_text_history WHERE entity = 'seed' AND entity_key = :m"), {"m": MARKER}).first():
        return {"skipped": "marker", "applied": 0}
    applied, kept, missing = 0, [], []
    for r in rows:
        res = conn.execute(text(_FORWARD.format(t=r["table"])), _params(r))
        if res.rowcount:
            applied += 1
        else:
            exists = conn.execute(text(f"SELECT 1 FROM {r['table']} WHERE id = :id AND slug = :slug"),
                                  {"id": r["id"], "slug": r["slug"]}).first()
            (kept if exists else missing).append(f"{r['kind']}:{r['id']}")
    conn.execute(text(
        "INSERT INTO admin_text_history (entity, entity_key, new_value, author) "
        "VALUES ('seed', :m, CAST(:v AS jsonb), 'SEO-тексты 2026-11')"),
        {"m": MARKER, "v": json.dumps({"applied": applied, "kept": kept, "missing": missing}, ensure_ascii=False)})
    return {"applied": applied, "kept_admin": len(kept), "missing": missing, "total": len(rows)}


def rollback(conn, rows: list[dict] | None = None) -> dict:
    """Возвращает старые значения там, где ещё стоит наш текст. Метку не снимает."""
    from sqlalchemy import text
    rows = rows if rows is not None else load_rows()
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    n = 0
    for r in rows:
        n += conn.execute(text(_BACK.format(t=r["table"])), _params(r)).rowcount or 0
    conn.execute(text(
        "INSERT INTO admin_text_history (entity, entity_key, new_value, author) "
        "VALUES ('seed', :m, CAST(:v AS jsonb), 'SEO-тексты 2026-11')"),
        {"m": MARKER + ":rollback", "v": json.dumps({"rolled_back": n})})
    return {"rolled_back": n}


def sql_rollback(rows: list[dict] | None = None) -> str:
    """Тот же откат одним SQL-файлом для psql."""
    rows = rows if rows is not None else load_rows()
    q = lambda s: "NULL" if s is None else "'" + s.replace("'", "''") + "'"
    out = ["-- Откат SEO-текстов 2026-11. Трогает поле, только если там ещё наш текст.", "BEGIN;"]
    for r in rows:
        out.append(
            f"UPDATE {r['table']} SET "
            f"seo_title = CASE WHEN seo_title = {q(r['seo_title'])} THEN {q(r['old_seo_title'])} ELSE seo_title END, "
            f"seo_description = CASE WHEN seo_description = {q(r['seo_description'])} THEN {q(r['old_seo_description'])} ELSE seo_description END "
            f"WHERE id = {r['id']} AND slug = {q(r['slug'])};")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def run_on_startup() -> dict:
    """Вызов из app/main.py. Выключатель: APPLY_SEO_TEXTS_2026_11=0."""
    from app.database import engine
    try:
        if os.getenv("ROLLBACK_SEO_TEXTS_2026_11") == "1":
            with engine.begin() as conn:
                stats = rollback(conn)
            log.warning("seo texts rolled back: %s", stats)
            return {"ran": "rollback", **stats}
        if os.getenv("APPLY_SEO_TEXTS_2026_11") == "0":
            return {"ran": False}
        with engine.begin() as conn:
            stats = apply(conn)
    except Exception:
        log.exception("seo texts apply failed, database left unchanged")
        return {"ran": True, "error": True}
    if stats.get("skipped") != "marker":
        log.warning("seo texts applied: %s", stats)
    return {"ran": True, **stats}
