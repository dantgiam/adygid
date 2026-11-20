"""Снимок, SQL и предпросмотр лент. К живой базе не подключается.

  python scripts/article_carousels.py snapshot /tmp/adygid-content
  python scripts/article_carousels.py sql
  python scripts/article_carousels.py preview /tmp/carousel-preview

snapshot читает выгрузку публичного API (articles.json, trails.json,
scenarios.json, checkpoints.json) и кладёт снимок текстов и нужных фото.
sql пишет миграцию и откат. preview собирает HTML страниц «после».
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content.carousels_2026_11.apply import (  # noqa: E402
    BEFORE, PLACES, apply_all, body_md5, load_before, load_places, sql_forward, sql_rollback,
)
from content.carousels_2026_11.plan import PLAN  # noqa: E402
from site_app.galleries import render_article_gallery  # noqa: E402

MIGRATION = ROOT / "migrations" / "20261120_article_carousels.sql"
ROLLBACK = ROOT / "migrations" / "20261120_article_carousels_rollback.sql"
MANIFEST = ROOT / "content" / "carousels_2026_11" / "manifest.json"


def _rows_from_dump(folder: Path) -> list[dict]:
    articles = {row["id"]: row for row in json.loads((folder / "articles.json").read_text(encoding="utf-8"))}
    trails = {row["id"]: row for row in json.loads((folder / "trails.json").read_text(encoding="utf-8"))}
    scenarios = {row["id"]: row for row in json.loads((folder / "scenarios.json").read_text(encoding="utf-8"))}
    rows = []
    for kind, item_id, _carousels in PLAN:
        if kind == "article":
            src = articles[item_id]
            body, title, slug = src["body"], src["title"], src["slug"]
        elif kind == "trail":
            src = trails[item_id]
            body, title, slug = src.get("description") or "", src["name"], src.get("slug") or ""
        else:
            src = scenarios[item_id]
            body, title, slug = src.get("lead") or "", src["title"], src["slug"]
        rows.append({
            "kind": kind, "id": item_id, "slug": slug, "title": title,
            "body": body, "md5": body_md5(body),
        })
    return rows


def _places_from_dump(folder: Path) -> list[dict]:
    needed = {pid for _k, _i, carousels in PLAN for _h, ids in carousels for pid in ids}
    raw = json.loads((folder / "checkpoints.json").read_text(encoding="utf-8"))
    out = []
    for row in raw:
        if row["id"] not in needed:
            continue
        out.append({
            "id": row["id"],
            "name": row["name"],
            "photos": [
                {"url": photo.get("url") or "", "caption": photo.get("caption") or ""}
                for photo in (row.get("photos") or [])
            ],
        })
    missing = needed - {row["id"] for row in out}
    if missing:
        raise SystemExit(f"в выгрузке нет мест {sorted(missing)}")
    return out


def snapshot(folder: Path) -> None:
    rows = _rows_from_dump(folder)
    places = _places_from_dump(folder)
    BEFORE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    PLACES.write_text(json.dumps(places, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"снимок: {len(rows)} текстов, {len(places)} мест")


def build():
    changed, report = apply_all(load_before(), load_places())
    return changed, report


def write_sql() -> None:
    changed, report = build()
    MIGRATION.write_text(sql_forward(changed), encoding="utf-8")
    ROLLBACK.write_text(sql_rollback(changed), encoding="utf-8")
    MANIFEST.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(len(item["carousels"]) for item in report)
    photos = sum(block.get("count", 0) for item in report for block in item["carousels"])
    print(f"sql: {len(changed)} текстов, {n} лент, {photos} кадров")


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/site_app/static/site.css">
<title>{title}</title></head><body>
<main><section class="section" style="padding-top:28px"><div class="wrap">
<p class="eyebrow">{eyebrow}</p>
<h1 class="article-title">{title}</h1>
<div class="article-layout"><div class="article-main"><div class="{body_class}">{body}</div></div></div>
</div></section></main></body></html>
"""


def preview(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    changed, _report = build()
    by_key = {(row["kind"], row["id"]): row for row in changed}
    picks = [
        ("article", 15, "article-body", "Статья"),
        ("article", 7, "article-body", "Статья"),
        ("article", 2, "article-body", "Статья"),
        ("scenario", 4, "article-body", "Подборка"),
        ("trail", 18, "detail-body", "Маршрут"),
    ]
    for kind, item_id, body_class, eyebrow in picks:
        row = by_key[(kind, item_id)]
        for label, source in (("before", row["body"]), ("after", row["new_body"])):
            rendered = render_article_gallery(source)
            html = PAGE.format(
                title=row["title"], eyebrow=eyebrow, body_class=body_class, body=rendered,
            )
            (folder / f"{kind}-{item_id}-{label}.html").write_text(html, encoding="utf-8")
    print(f"preview: {folder}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("нужна команда: snapshot | sql | preview")
    cmd = sys.argv[1]
    if cmd == "snapshot":
        snapshot(Path(sys.argv[2]))
    elif cmd == "sql":
        write_sql()
    elif cmd == "preview":
        preview(Path(sys.argv[2]))
    else:
        raise SystemExit(f"неизвестная команда {cmd}")


if __name__ == "__main__":
    main()
