"""Публикация черновиков SEO-потока (content/seo-2026-11/content.json).

По умолчанию — сухой прогон: печатает, что будет создано или изменено.
  python scripts/seo_content_publish.py                     # что изменится
  python scripts/seo_content_publish.py --live              # записать через админ-API
  python scripts/seo_content_publish.py --db                # записать прямо в DATABASE_URL (локальное превью)

Для --live нужны переменные окружения ADYGID_API (например,
https://www.adygid.ru/api), ADMIN_USER и ADMIN_PASSWORD. Маршрут 11 и место 50
скрипт не трогает: он работает только со статьями, наборами вопросов,
сценарием zimoy и точечными правками text_patches (ссылки на карточки и
«округ» → «район» в уже опубликованных текстах).
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


# PATCH /api/scenarios/{id} перезаписывает сценарий целиком (форма админки
# всегда шлёт всё): частичный payload стёр бы иконку, обложки, фильтры и
# порядок. Поэтому берём текущую запись из GET и меняем только нужные поля.
SCENARIO_FIELDS = ("slug", "icon", "door", "hint", "title", "lead", "cover_url", "cover_thumb_url", "cover_focus",
                   "tile_cover_url", "tile_cover_thumb_url", "tile_cover_focus", "seo_description",
                   "featured_article_ids", "filter_kid_friendly", "filter_popularity", "filter_difficulty",
                   "filter_seasonality", "filter_access", "order_index", "is_published")


def scenario_payload(current: dict, **over) -> dict:
    data = {k: current.get(k) for k in SCENARIO_FIELDS if k in current}
    data.update(over)
    return data


def apply_text_patch(text: str, pairs: list, label: str) -> tuple:
    """Возвращает (новый текст, число применённых замен). Пара пропускается,
    если «было» уже нет, а «стало» есть (повторный запуск); если нет ни
    того ни другого или «было» встречается не один раз — правка не
    делается вовсе, чтобы не испортить текст, который успели поменять."""
    text = text or ""
    done = 0
    for old, new in pairs:
        if new in text:  # уже применено (повторный запуск)
            continue
        n = text.count(old)
        if n == 1:
            text = text.replace(old, new)
            done += 1
        else:
            raise SystemExit(f"text_patch {label}: «{old[:60]}» найдено {n} раз — текст изменился, правку надо пересобрать")
    return text, done


def patch_faq_items(items: list, pairs: list, label: str) -> tuple:
    """Та же замена, но внутри ответов набора вопросов (список JSON)."""
    enc = lambda v: json.dumps(v, ensure_ascii=False)[1:-1]  # noqa: E731
    text, done = apply_text_patch(json.dumps(items or [], ensure_ascii=False),
                                  [(enc(o), enc(n)) for o, n in pairs], label)
    return json.loads(text), done


FAQ_SET_FIELDS = ("slug", "name", "title", "items", "on_faq_page", "order_index", "is_published")


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
    payload = scenario_payload(sc, **{k: z[k] for k in ("title", "door", "hint", "seo_description", "lead", "cover_url", "tile_cover_url", "tile_cover_focus", "is_published")})
    payload["featured_article_ids"] = [articles[s]["id"] for s in z["featured_article_slugs"] if s in articles]
    # Обложки задаём новые — старые миниатюры от прежних картинок не нужны.
    payload["cover_thumb_url"] = None
    payload["tile_cover_thumb_url"] = None
    print("PATCH scenario zimoy", sc["id"]); LIVE and api("PATCH", f"/scenarios/{sc['id']}", payload)

    by_kind = {"article": {a["slug"]: a for a in api("GET", "/articles")},
               "scenario": {x["slug"]: x for x in api("GET", "/scenarios")}}
    by_kind["faq_set"] = {x["slug"]: x for x in api("GET", "/faq-sets")}
    for pch in CONTENT.get("text_patches", []):
        row = by_kind[pch["kind"]].get(pch["slug"])
        if row and pch["kind"] == "faq_set":
            items, done = patch_faq_items(row.get("items"), pch["replace"], f"faq:{pch['slug']}")
            print(f"PATCH faq-set {pch['slug']}: {done} правок")
            if done and LIVE:
                # PATCH наборов тоже перезаписывает всё — шлём набор целиком.
                api("PATCH", f"/faq-sets/{row['id']}", dict({k: row.get(k) for k in FAQ_SET_FIELDS}, items=items))
            continue
        if not row:
            print("SKIP  text_patch", pch["kind"], pch["slug"], "— нет на сайте"); continue
        new, done = apply_text_patch(row.get(pch["field"]), pch["replace"], f"{pch['slug']}.{pch['field']}")
        print(f"PATCH {pch['kind']} {pch['slug']}.{pch['field']}: {done} правок")
        if done and LIVE:
            data = scenario_payload(row, **{pch["field"]: new}) if pch["kind"] == "scenario" else {pch["field"]: new}
            api("PATCH", f"/{pch['kind']}s/{row['id']}", data)
            row[pch["field"]] = new


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
    for pch in CONTENT.get("text_patches", []):
        model = {"article": Article, "scenario": Scenario, "faq_set": FaqSet}[pch["kind"]]
        row = db.execute(select(model).where(model.slug == pch["slug"])).scalars().first()
        if not row:
            print("SKIP  text_patch", pch["slug"]); continue
        if pch["kind"] == "faq_set":
            row.items, done = patch_faq_items(row.items, pch["replace"], f"faq:{pch['slug']}")
            print(f"text_patch faq:{pch['slug']}: {done}")
            continue
        new, done = apply_text_patch(getattr(row, pch["field"]), pch["replace"], f"{pch['slug']}.{pch['field']}")
        setattr(row, pch["field"], new)
        print(f"text_patch {pch['slug']}.{pch['field']}: {done}")
    db.commit()
    print("written to", os.environ.get("DATABASE_URL", "default DB"))


if __name__ == "__main__" and DB:
    via_db()
elif __name__ == "__main__":
    via_api()
    if not LIVE:
        print("\nСухой прогон. Для записи: --live (админ-API) или --db (локальная БД превью).")
