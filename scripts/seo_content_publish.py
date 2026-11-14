"""Публикация черновиков SEO-потока (content/seo-2026-11/content.json).

По умолчанию — сухой прогон: печатает, что будет создано или изменено.
  python scripts/seo_content_publish.py                     # что изменится
  python scripts/seo_content_publish.py --live              # записать через админ-API
  python scripts/seo_content_publish.py --db                # записать прямо в DATABASE_URL (локальное превью)

Для --live нужны переменные окружения ADYGID_API (например,
https://www.adygid.ru/api), ADMIN_USER и ADMIN_PASSWORD. Маршрут 11 и место 50
скрипт не трогает: он работает только со статьями, наборами вопросов и
сценарием zimoy.
"""
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "content" / "seo-2026-11"
# content.json собирается из build.py (там тексты и источники) и в git не хранится.
import runpy  # noqa: E402
runpy.run_path(str(_DIR / "build.py"))
CONTENT = json.loads((_DIR / "content.json").read_text("utf-8"))
LIVE = "--live" in sys.argv
DB = "--db" in sys.argv


def api(method, path, data=None):
    base = os.environ["ADYGID_API"].rstrip("/")
    token = base64.b64encode(f"{os.environ['ADMIN_USER']}:{os.environ['ADMIN_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(data, ensure_ascii=False).encode() if data is not None else None,
        headers={"Authorization": "Basic " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def via_api():
    articles = {a["slug"]: a for a in api("GET", "/articles")}
    for a in CONTENT["articles"]:
        payload = {k: a[k] for k in ("slug", "title", "excerpt", "cover_url", "body", "faq", "district",
                                     "featured_checkpoint_ids", "featured_trail_ids")}
        payload["is_published"] = True
        if a["slug"] in articles:
            print("PATCH article", a["slug"]); LIVE and api("PATCH", f"/articles/{articles[a['slug']]['id']}", payload)
        else:
            print("POST  article", a["slug"]); LIVE and api("POST", "/articles", payload)
    sets = {f["slug"]: f for f in api("GET", "/faq-sets")}
    for f in CONTENT["faq_sets"]:
        payload = dict(f, is_published=True)
        if f["slug"] in sets:
            print("PATCH faq-set", f["slug"]); LIVE and api("PATCH", f"/faq-sets/{sets[f['slug']]['id']}", payload)
        else:
            print("POST  faq-set", f["slug"]); LIVE and api("POST", "/faq-sets", payload)
    articles = {a["slug"]: a for a in api("GET", "/articles")}
    sc = next(s for s in api("GET", "/scenarios") if s["slug"] == "zimoy")
    z = CONTENT["scenario_zimoy"]
    payload = {k: z[k] for k in ("title", "door", "hint", "seo_description", "lead", "cover_url", "tile_cover_url", "tile_cover_focus", "is_published")}
    payload["featured_article_ids"] = [articles[s]["id"] for s in z["featured_article_slugs"] if s in articles]
    print("PATCH scenario zimoy", sc["id"]); LIVE and api("PATCH", f"/scenarios/{sc['id']}", payload)


def via_db():
    sys.path.insert(0, os.getcwd())
    import app.main  # noqa: F401 — лёгкая миграция колонок при импорте
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Article, FaqSet, Scenario
    db = SessionLocal()
    for a in CONTENT["articles"]:
        row = db.execute(select(Article).where(Article.slug == a["slug"])).scalars().first() or Article(slug=a["slug"])
        for k in ("title", "excerpt", "cover_url", "body", "faq", "district", "featured_checkpoint_ids", "featured_trail_ids"):
            setattr(row, k, a[k])
        row.is_published = True
        db.add(row)
    for f in CONTENT["faq_sets"]:
        row = db.execute(select(FaqSet).where(FaqSet.slug == f["slug"])).scalars().first() or FaqSet(slug=f["slug"])
        for k in ("name", "title", "items", "on_faq_page"):
            setattr(row, k, f[k])
        row.is_published = True
        db.add(row)
    db.flush()
    z = CONTENT["scenario_zimoy"]
    sc = db.execute(select(Scenario).where(Scenario.slug == "zimoy")).scalars().first()
    for k in ("title", "door", "hint", "seo_description", "lead", "cover_url", "tile_cover_url", "tile_cover_focus", "is_published"):
        setattr(sc, k, z[k])
    by_slug = {a.slug: a.id for a in db.execute(select(Article)).scalars().all()}
    sc.featured_article_ids = [by_slug[s] for s in z["featured_article_slugs"] if s in by_slug]
    db.commit()
    print("written to", os.environ.get("DATABASE_URL", "default DB"))


if DB:
    via_db()
else:
    via_api()
    if not LIVE:
        print("\nСухой прогон. Для записи: --live (админ-API) или --db (локальная БД превью).")
