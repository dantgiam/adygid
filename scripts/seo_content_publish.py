"""Публикация черновиков SEO-потока (content/seo-2026-11/content.json).

По умолчанию — сухой прогон: печатает, что будет создано или изменено.
  python scripts/seo_content_publish.py                     # что изменится
  python scripts/seo_content_publish.py --live              # записать через админ-API
  python scripts/seo_content_publish.py --db                # записать прямо в DATABASE_URL (локальное превью)

Для --live нужны переменные окружения ADYGID_API (например,
https://www.adygid.ru/api), ADMIN_USER и ADMIN_PASSWORD. Маршрут 11 и место 50
скрипт не трогает ни при каких условиях. Что делает, по шагам:
  1. Фото с Wikimedia Commons (content["commons"]) заливает через
     /api/uploads/photo и подставляет наш адрес; соответствие хранится в
     content/seo-2026-11/uploaded.json, повторный запуск не грузит заново.
  2. Статьи, наборы вопросов, сценарий zimoy — создаёт или обновляет.
  3. text_patches — точечные правки опубликованных текстов.
  4. cover_updates — замена обложек, если на сайте ещё старая картинка.
  5. Автоссылки (site_app/autolink.py): первое упоминание места с карточкой
     в статьях и хабах /kuda становится ссылкой.
  6. district_assign — район местам и маршрутам, у которых его ещё нет
     (проверяется по публичной странице карточки).
Всё идемпотентно: второй запуск подряд ничего не меняет.
"""
import base64
import json
import os
import re
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from site_app.autolink import autolink, strip_place_links  # noqa: E402

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
        # Применено, а потом автоссылки связали место внутри «стало»:
        # сравниваем тексты без ссылок на карточки.
        s_new, s_old, s_text = strip_place_links(new), strip_place_links(old), strip_place_links(text)
        if s_new != s_old and s_new in s_text:
            continue
        # Правка, которая только ставит ссылку: место уже связано — готово.
        hrefs = re.findall(r'href="/mesta/\d+"', new)
        if s_new == s_old and hrefs and all(h in text for h in hrefs):
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


NEVER_TOUCH = {("mesta", 50), ("marshruty", 11)}
UPLOADED_PATH = _DIR / "uploaded.json"
UA = {"User-Agent": "AdyGidBot/1.0 (https://www.adygid.ru; publish script)"}


def site_base() -> str:
    return os.environ.get("ADYGID_SITE") or os.environ["ADYGID_API"].rstrip("/").rsplit("/api", 1)[0]


def upload_photo(src: str) -> dict:
    """Скачать фото с Commons и залить через /api/uploads/photo (multipart)."""
    with urllib.request.urlopen(urllib.request.Request(src, headers=UA), timeout=120) as r:
        data = r.read()
    name = src.rsplit("/", 1)[-1].split("?")[0]
    ext = "png" if name.lower().endswith(".png") else "jpg"
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"commons.{ext}\"\r\n"
            f"Content-Type: image/{'png' if ext == 'png' else 'jpeg'}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    base = os.environ["ADYGID_API"].rstrip("/")
    token = base64.b64encode(f"{os.environ['ADMIN_USER']}:{os.environ['ADMIN_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(base + "/uploads/photo", method="POST", data=body, headers={
        "Authorization": "Basic " + token, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def localize_commons(content: dict) -> dict:
    """Commons-адреса в content → адреса нашего хранилища (только --live).
    В сухом прогоне печатает, что будет залито, и ничего не меняет."""
    uploaded = json.loads(UPLOADED_PATH.read_text("utf-8")) if UPLOADED_PATH.exists() else {}
    raw = json.dumps(content, ensure_ascii=False)
    for key, c in (content.get("commons") or {}).items():
        src = c["src"]
        if src not in raw.replace(json.dumps(content.get("commons"), ensure_ascii=False), ""):
            continue
        if src in uploaded:
            print(f"photo {key}: уже залито → {uploaded[src]['url']}")
        elif LIVE:
            uploaded[src] = upload_photo(src)
            UPLOADED_PATH.write_text(json.dumps(uploaded, ensure_ascii=False, indent=1), "utf-8")
            print(f"UPLOAD {key} → {uploaded[src]['url']}")
        else:
            print(f"UPLOAD {key}: {c['what']} — {c['author']}, {c['license']} (Commons → /api/uploads/photo)")
    commons = content.get("commons")
    body = {k: v for k, v in content.items() if k != "commons"}
    raw = json.dumps(body, ensure_ascii=False)
    for src, up in uploaded.items():
        raw = raw.replace(src, up["url"])
    out = json.loads(raw)
    out["commons"] = commons
    out["_thumbs"] = {up["url"]: up.get("thumb_url") for up in uploaded.values()}
    return out


def published_place_ids(checkpoints: list) -> set:
    return {c["id"] for c in checkpoints if c.get("is_published") and c.get("show_as_place")}


def has_district_on_page(kind: str, obj_id: int) -> Optional[str]:
    """Район на публичной странице карточки (API поле district не отдаёт)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{site_base()}/{kind}/{obj_id}", headers=UA), timeout=60) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return f"? ({e})"
    m = re.search(r'href="/okrugi/([a-z]+)" style="color:inherit"', html)
    return m.group(1) if m else None


def district_plan(assign: dict):
    for kind, rows in (assign or {}).items():
        for obj_id, slug in rows.items():
            obj_id = int(obj_id)
            if (kind, obj_id) in NEVER_TOUCH:
                raise SystemExit(f"district_assign: {kind}/{obj_id} трогать нельзя")
            yield kind, obj_id, slug


FAQ_SET_FIELDS = ("slug", "name", "title", "items", "on_faq_page", "order_index", "is_published")


class PatchConflict(Exception):
    pass


def safe_patch(text, pairs, label, skipped):
    """apply_text_patch, но конфликт (текст успели поменять — например,
    параллельная правка фото) не валит весь прогон: правка пропускается и
    попадает в итоговый список «пропущено»."""
    try:
        return apply_text_patch(text, pairs, label)
    except SystemExit as e:
        skipped.append(str(e))
        print("SKIP ", e)
        return text, 0


def fresh(kind: str, slug: str):
    """Запись берём с сайта прямо перед записью — никаких снимков: обложки и
    фото могли поменять параллельно, PATCH сценария и набора вопросов
    перезаписывает запись целиком."""
    path = {"article": "/articles", "scenario": "/scenarios", "faq_set": "/faq-sets"}[kind]
    return next((x for x in api("GET", path) if x["slug"] == slug), None)


def via_api():
    content = localize_commons(CONTENT)
    thumbs = content.pop("_thumbs", {})
    skipped: list = []
    changes = {"create": [], "update": [], "patch": [], "autolink": [], "district": []}

    # 1. Новые статьи потока (черновики из build.py) — с автоссылками.
    checkpoints = api("GET", "/checkpoints")
    pub_places = published_place_ids(checkpoints)
    for a in content["articles"]:
        payload = {k: a[k] for k in ("slug", "title", "excerpt", "cover_url", "body", "faq", "district",
                                     "featured_checkpoint_ids", "featured_trail_ids")}
        payload["body"], added = autolink(payload["body"], pub_places)
        if thumbs.get(payload["cover_url"]):
            payload["cover_thumb_url"] = thumbs[payload["cover_url"]]
        payload["is_published"] = True
        row = fresh("article", a["slug"])
        if row:
            print("PATCH article", a["slug"], f"(+{len(added)} автоссылок)")
            changes["update"].append("stati/" + a["slug"])
            LIVE and api("PATCH", f"/articles/{row['id']}", payload)
        else:
            print("POST  article", a["slug"], f"(+{len(added)} автоссылок)")
            changes["create"].append("stati/" + a["slug"])
            LIVE and api("POST", "/articles", payload)

    # 2. Наборы вопросов.
    for f in content["faq_sets"]:
        payload = dict(f, is_published=True)
        row = fresh("faq_set", f["slug"])
        if row:
            payload = dict({k: row.get(k) for k in FAQ_SET_FIELDS}, **payload)
            print("PATCH faq-set", f["slug"]); changes["update"].append("faq:" + f["slug"])
            LIVE and api("PATCH", f"/faq-sets/{row['id']}", payload)
        else:
            print("POST  faq-set", f["slug"]); changes["create"].append("faq:" + f["slug"])
            LIVE and api("POST", "/faq-sets", payload)

    # 3. Хаб zimoy.
    articles = {x["slug"]: x for x in api("GET", "/articles")}
    sc = fresh("scenario", "zimoy")
    z = content["scenario_zimoy"]
    lead, _ = autolink(z["lead"], pub_places)
    payload = scenario_payload(sc, **{k: z[k] for k in ("title", "door", "hint", "seo_description", "cover_url", "tile_cover_url", "tile_cover_focus", "is_published")}, lead=lead)
    payload["featured_article_ids"] = [articles[s]["id"] for s in z["featured_article_slugs"] if s in articles]
    payload["cover_thumb_url"] = thumbs.get(z["cover_url"])
    payload["tile_cover_thumb_url"] = thumbs.get(z["tile_cover_url"])
    print("PATCH scenario zimoy", sc["id"]); changes["update"].append("kuda/zimoy")
    LIVE and api("PATCH", f"/scenarios/{sc['id']}", payload)

    # 4. Точечные правки опубликованных текстов. Каждую запись — свежей.
    for pch in content.get("text_patches", []):
        row = fresh(pch["kind"], pch["slug"])
        if not row:
            print("SKIP  text_patch", pch["kind"], pch["slug"], "— нет на сайте"); continue
        if pch["kind"] == "faq_set":
            try:
                items, done = patch_faq_items(row.get("items"), pch["replace"], f"faq:{pch['slug']}")
            except SystemExit as e:
                skipped.append(str(e)); print("SKIP ", e); continue
            print(f"PATCH faq-set {pch['slug']}: {done} правок")
            if done:
                changes["patch"].append(f"faq:{pch['slug']} ({done})")
                LIVE and api("PATCH", f"/faq-sets/{row['id']}", dict({k: row.get(k) for k in FAQ_SET_FIELDS}, items=items))
            continue
        new, done = safe_patch(row.get(pch["field"]), pch["replace"], f"{pch['slug']}.{pch['field']}", skipped)
        print(f"PATCH {pch['kind']} {pch['slug']}.{pch['field']}: {done} правок")
        if done:
            changes["patch"].append(f"{pch['kind']}:{pch['slug']}.{pch['field']} ({done})")
            if LIVE:
                # Статья — частичный PATCH одного поля (обложку не трогаем);
                # сценарий — целиком, но из свежей записи.
                data = scenario_payload(row, **{pch["field"]: new}) if pch["kind"] == "scenario" else {pch["field"]: new}
                api("PATCH", f"/{pch['kind']}s/{row['id']}", data)

    # 5. Автоссылки во всех статьях и хабах /kuda (свежие записи, только текст).
    for kind, field, prefix in (("article", "body", "stati/"), ("scenario", "lead", "kuda/")):
        path = "/articles" if kind == "article" else "/scenarios"
        for row in api("GET", path):
            text = row.get(field) or ""
            if not LIVE:  # в сухом прогоне учесть ещё не применённые правки
                for pch in content.get("text_patches", []):
                    if pch["kind"] == kind and pch["slug"] == row["slug"] and pch["field"] == field:
                        text, _ = safe_patch(text, pch["replace"], "dry", [])
            new, added = autolink(text, pub_places)
            if not added:
                continue
            print(f"LINK  {prefix}{row['slug']}: " + ", ".join(f"«{t}»→/mesta/{i}" for i, t in added))
            changes["autolink"].append(f"{prefix}{row['slug']} ({len(added)})")
            if LIVE:
                cur = fresh(kind, row["slug"])  # перечитать прямо перед записью
                new, added = autolink(cur.get(field) or "", pub_places)
                if added:
                    data = scenario_payload(cur, **{field: new}) if kind == "scenario" else {field: new}
                    api("PATCH", f"/{kind}s/{cur['id']}", data)

    # 6. Районы для карточек без района.
    for kind, obj_id, slug in district_plan(content.get("district_assign")):
        now = has_district_on_page(kind, obj_id)
        if now and not now.startswith("?"):
            print(f"SKIP  district {kind}/{obj_id}: уже {now}"); continue
        if now and now.startswith("?"):
            print(f"SKIP  district {kind}/{obj_id}: страница не открылась {now}"); skipped.append(f"district {kind}/{obj_id}"); continue
        print(f"PATCH district {kind}/{obj_id} → {slug}")
        changes["district"].append(f"{kind}/{obj_id}→{slug}")
        if LIVE:
            api("PATCH", f"/{'checkpoints' if kind == 'mesta' else 'trails'}/{obj_id}", {"district": slug})

    print("\nИтого:", json.dumps({k: len(v) for k, v in changes.items()}, ensure_ascii=False))
    if skipped:
        print("Пропущено (текст на сайте изменился, правку надо пересобрать):")
        for x in skipped:
            print("  -", x)
    return changes, skipped


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
    from app.models import Checkpoint, Trail
    pub = {c.id for c in db.execute(select(Checkpoint)).scalars().all() if c.is_published and c.show_as_place}
    for row in db.execute(select(Article)).scalars().all():
        row.body, added = autolink(row.body or "", pub)
        added and print(f"autolink stati/{row.slug}: {len(added)}")
    for row in db.execute(select(Scenario)).scalars().all():
        row.lead, added = autolink(row.lead or "", pub)
        added and print(f"autolink kuda/{row.slug}: {len(added)}")
    for kind, obj_id, slug in district_plan(CONTENT.get("district_assign")):
        obj = db.get(Checkpoint if kind == "mesta" else Trail, obj_id)
        if obj is not None and not obj.district:
            obj.district = slug
            print(f"district {kind}/{obj_id} → {slug}")
    db.commit()
    print("written to", os.environ.get("DATABASE_URL", "default DB"))


if __name__ == "__main__" and DB:
    via_db()
elif __name__ == "__main__":
    via_api()
    if not LIVE:
        print("\nСухой прогон. Для записи: --live (админ-API) или --db (локальная БД превью).")
