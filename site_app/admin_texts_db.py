"""Миграция и начальное наполнение текстов для админки «Тексты сайта».

Как и остальные миграции проекта (партнёры, подбор), выполняется при каждом
старте приложения из app/main.py: Railway собирает образ из Dockerfile и
запускает uvicorn — отдельного шага миграций нет. Поэтому всё здесь
повторяемое:
  1. migrations/20261119_admin_texts.sql — только CREATE … IF NOT EXISTS;
  2. «Коротко для поездки» из seo.PLACE_PRACTICAL — INSERT … ON CONFLICT DO
     NOTHING: запись появляется один раз, правки из админки не затираются;
  3. плашка «Новогодние каникулы» — один раз (метка seed в admin_text_history),
     чтобы удалённая в админке плашка не возвращалась после перезапуска.
Всё в одной транзакции под advisory-lock: два процесса, стартующие разом,
не наполнят таблицы дважды. Ошибка не роняет сайт — он рисует тексты из кода.
"""
import logging
import os

from sqlalchemy import text

from app.database import engine

log = logging.getLogger("adygid.admin_texts")
MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261119_admin_texts.sql")
_LOCK_KEY = 20261119


def _statements(raw: str) -> list:
    out = []
    for chunk in raw.split(";"):
        lines = [ln for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        if lines:
            out.append("\n".join(lines))
    return out


def ensure_admin_text_tables() -> dict:
    from site_app import trip_facts, travel_notices, site_texts
    stats = {"blocks": 0, "notices": 0}
    try:
        raw = open(MIGRATION, encoding="utf-8").read()
    except OSError:
        log.warning("admin texts migration missing")
        return stats
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
            for stmt in _statements(raw):
                conn.execute(text(stmt))
            stats["blocks"] = trip_facts.seed_from_code(conn)
            marker = conn.execute(text(
                "SELECT 1 FROM admin_text_history WHERE entity = 'seed' AND entity_key = 'site_notices'"
            )).first()
            if not marker:
                stats["notices"] = travel_notices.seed(conn)
                conn.execute(text(
                    "INSERT INTO admin_text_history (entity, entity_key, new_value, author) "
                    "VALUES ('seed', 'site_notices', '{}'::jsonb, 'перенос из кода')"
                ))
    except Exception:
        log.exception("admin texts migration failed")
    trip_facts.invalidate()
    travel_notices.invalidate()
    site_texts.invalidate()
    if stats["blocks"] or stats["notices"]:
        log.warning("admin texts seeded: %s", stats)
    return stats
