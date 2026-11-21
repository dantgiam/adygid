"""Запись лент в боевую базу. Сама не запускается.

Включается только переменной APPLY_ARTICLE_CAROUSELS=1 на время одного
деплоя. Строка меняется, если её текст всё ещё совпадает со снимком.
Если метка не встала, транзакция откатывается и сайт не падает.
Повторный запуск при уже стоящих метках ничего не переписывает.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("adygid.carousels")

_TABLE = {
    "article": ("articles", "body"),
    "trail": ("trails", "description"),
    "scenario": ("scenarios", "lead"),
}


def apply_if_enabled() -> dict:
    if os.getenv("APPLY_ARTICLE_CAROUSELS") != "1":
        return {"ran": False}
    try:
        stats = apply_live()
    except Exception:
        log.exception("article carousels apply failed, database left unchanged")
        return {"ran": True, "error": True}
    log.warning("article carousels applied: %s", stats)
    return {"ran": True, **stats}


def apply_live() -> dict:
    from sqlalchemy import text

    from app.database import engine
    from content.carousels_2026_11.apply import apply_all, load_before, load_places

    changed, _report = apply_all(load_before(), load_places())
    applied = 0
    already = 0
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(20261120)"))
        for row in changed:
            table, column = _TABLE[row["kind"]]
            result = conn.execute(
                text(
                    f"UPDATE {table} SET {column} = :body "
                    f"WHERE id = :id AND md5(convert_to(coalesce({column}, ''), 'UTF8')) = :md5"
                ),
                {"body": row["new_body"], "id": row["id"], "md5": row["md5"]},
            )
            marker = f"adygid-carousel:{row['kind']}:{row['id']}:"
            present = conn.execute(
                text(
                    f"SELECT position(:marker in coalesce({column}, '')) > 0 "
                    f"FROM {table} WHERE id = :id"
                ),
                {"marker": marker, "id": row["id"]},
            ).scalar()
            if not present:
                raise RuntimeError(f"лента не встала: {row['kind']} {row['id']}")
            if result.rowcount:
                applied += 1
            else:
                already += 1
    return {"applied": applied, "already": already, "texts": len(changed)}
