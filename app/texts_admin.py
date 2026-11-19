"""Админка «Тексты сайта» (/admin/texts): за тем же HTTP Basic, что /admin.

Три раздела:
  • Карточки мест — «Коротко для поездки», title и description для поиска;
  • Тексты страниц — тексты шаблонов t('ключ', 'текст') с поиском;
  • Плашки — плашка в подборе (каникулы и др.): текст, даты, вкл/выкл.
Каждая правка пишется в admin_text_history (кто, когда, было/стало) —
любую прошлую версию можно вернуть.

Обычные HTML-формы с POST и переадресацией, немного JS только для удобства
(добавить/переставить строку, счётчик длины, превью сниппета).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.bot_admin import _page, require_bot_admin
from app.database import get_db
from app.models import AdminTextHistory, Checkpoint, PlaceTripBlock, SiteNotice, SiteText, Trail
from site_app import site_texts, travel_notices, trip_facts
from site_app.router import SITE_URL, invalidate_home_cache
from site_app.urls import place_url
from app.slugs import set_slug

router = APIRouter()

DAYS = [("Monday", "Пн"), ("Tuesday", "Вт"), ("Wednesday", "Ср"), ("Thursday", "Чт"),
        ("Friday", "Пт"), ("Saturday", "Сб"), ("Sunday", "Вс")]
_DAY_RU = {ru.lower(): en for en, ru in DAYS}
_DAY_EN = dict(DAYS)
ROW_KEYS = [(k, trip_facts.LABELS[k]) for k in trip_facts.STANDARD_KEYS] + [("custom", "Своя строка")]
LD_KEYS = {"hours", "tickets", "cash", "pets"}
MAX_ROWS = 20
TITLE_RECOMMENDED = 60
DESC_RECOMMENDED = 160
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_URL_RE = re.compile(r"^https?://[^\s<>\"']+$")


# ───────────────── общее ─────────────────

def same_origin(request: Request) -> None:
    """Формы шлёт только сама админка: чужой сайт не сможет отправить POST от
    имени вошедшего админа (браузер подставил бы Basic-пароль сам)."""
    host = request.headers.get("host", "")
    for header in ("origin", "referer"):
        v = request.headers.get(header)
        if v:
            if urlparse(v).netloc != host:
                raise HTTPException(403, "Запрос не из админки")
            return


def _ctx(request: Request, **extra) -> dict:
    base = {"request": request, "section": "texts", "site_url": SITE_URL, "msk": _msk}
    base.update(extra)
    return base


def _msk(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def _s(form, name: str, limit: int = 1000) -> str:
    v = form.get(name)
    v = "" if v is None else str(v).replace("\r\n", "\n").strip()
    if len(v) > limit:
        raise HTTPException(400, f"Поле слишком длинное (до {limit} знаков)")
    return v


def _date(v: str) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise HTTPException(400, f"Неверная дата: {v}")


def _url(v: str) -> str:
    if v and not _URL_RE.match(v):
        raise HTTPException(400, f"Ссылка должна начинаться с http:// или https://: {v[:80]}")
    return v


def _history(db: Session, entity: str, key: str, old, new, author: str) -> None:
    db.add(AdminTextHistory(entity=entity, entity_key=str(key), old_value=old, new_value=new, author=author))


def _changed() -> None:
    trip_facts.invalidate()
    site_texts.invalidate()
    travel_notices.invalidate()
    invalidate_home_cache()


def _jsonable(v):
    return json.loads(json.dumps(v, default=str, ensure_ascii=False))


def _recent_history(db: Session, entity: str, key: str, limit: int = 15) -> list:
    return db.execute(
        select(AdminTextHistory).where(AdminTextHistory.entity == entity, AdminTextHistory.entity_key == str(key))
        .order_by(AdminTextHistory.created_at.desc(), AdminTextHistory.id.desc()).limit(limit)
    ).scalars().all()


# ───────────────── главная раздела ─────────────────

@router.get("/admin/texts")
def texts_home(request: Request, _: str = Depends(require_bot_admin)):
    return RedirectResponse("/admin/texts/places", status_code=303)


# ───────────────── карточки мест ─────────────────

def _block_dict(b: PlaceTripBlock) -> dict:
    return {
        "place_id": b.place_id, "enabled": b.enabled, "heading_name": b.heading_name or "",
        "seo_title": b.seo_title or "", "seo_description": b.seo_description or "",
        "rows": b.rows or [], "combine_ids": b.combine_ids or [], "route_id": b.route_id,
        "auto_visit": b.auto_visit, "search_facts": b.search_facts or {}, "sources": b.sources or [],
        "updated_at": b.updated_at, "updated_by": b.updated_by, "from_code": False,
    }


def _snapshot(b: dict) -> dict:
    return _jsonable({k: b.get(k) for k in ("enabled", "heading_name", "seo_title", "seo_description", "rows",
                                             "combine_ids", "route_id", "auto_visit", "search_facts", "sources")})


@router.get("/admin/texts/places")
def places_list(request: Request, q: str = "", flt: str = "", db: Session = Depends(get_db),
                _: str = Depends(require_bot_admin)):
    cps = db.execute(select(Checkpoint).where(Checkpoint.show_as_place == True).order_by(Checkpoint.name)).scalars().all()
    blocks = {b.place_id: _block_dict(b) for b in db.execute(select(PlaceTripBlock)).scalars().all()}
    items = []
    ql = q.strip().lower()
    for cp in cps:
        b = blocks.get(cp.id) or trip_facts.block_from_code(cp.id)
        rows = (b or {}).get("rows") or []
        n_ver = sum(1 for r in rows if r.get("verified"))
        title = trip_facts.title(b, cp.name, cp.district)
        item = {
            "id": cp.id, "name": cp.name, "url": place_url(cp), "published": cp.is_published, "has_block": bool(b and b.get("enabled") and rows),
            "rows": len(rows), "verified": n_ver, "title": title, "title_len": len(title),
            "manual_title": bool(b and b.get("seo_title")), "updated_at": (b or {}).get("updated_at"),
            "updated_by": (b or {}).get("updated_by"), "checked": (trip_facts.checked(b) or {}).get("label"),
        }
        if ql and ql not in cp.name.lower() and ql != str(cp.id) and ql != (cp.slug or ""):
            continue
        if flt == "noblock" and item["has_block"]:
            continue
        if flt == "verified" and not n_ver:
            continue
        if flt == "unverified" and (n_ver or not item["has_block"]):
            continue
        items.append(item)
    totals = {"all": len(cps), "with_block": sum(1 for i in items if i["has_block"])}
    return _page("texts_places.html", _ctx(request, tab="places", items=items, q=q, flt=flt, totals=totals))


def _place_or_404(db: Session, place_id: int) -> Checkpoint:
    cp = db.get(Checkpoint, place_id)
    if not cp:
        raise HTTPException(404, "Место не найдено")
    return cp


def _spec_to_text(spec: list) -> str:
    lines = []
    for r in spec or []:
        days = " ".join(_DAY_EN.get(d, d) for d in r.get("days", []))
        lines.append(f"{days} {r.get('opens', '')}–{r.get('closes', '')}")
    return "\n".join(lines)


def _spec_from_text(raw: str) -> list:
    out = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.*?)\s*(\d{2}:\d{2})\s*[-–—]\s*(\d{2}:\d{2})$", line)
        if not m:
            raise HTTPException(400, f"Не понял строку расписания: «{line}». Пример: «Вт Ср Чт 10:00–18:00»")
        days = []
        for tok in re.split(r"[\s,]+", m.group(1).strip()):
            if not tok:
                continue
            en = _DAY_RU.get(tok.lower().rstrip("."))
            if not en:
                raise HTTPException(400, f"Не понял день «{tok}» — пишите Пн, Вт, Ср, Чт, Пт, Сб, Вс")
            days.append(en)
        if not days or not _TIME_RE.match(m.group(2)) or not _TIME_RE.match(m.group(3)):
            raise HTTPException(400, f"Не понял строку расписания: «{line}»")
        out.append({"days": days, "opens": m.group(2), "closes": m.group(3)})
    return out


def _sources_to_text(sources: list) -> str:
    return "\n".join(f"{s.get('title', '')} | {s.get('url', '')}" for s in sources or [])


def _sources_from_text(raw: str) -> list:
    out = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            title, url = (x.strip() for x in line.rsplit("|", 1))
        else:
            title, url = "", line
        _url(url)
        out.append({"title": title or url, "url": url})
    return out[:10]


def _ids(raw: str) -> list:
    return [int(x) for x in re.findall(r"\d{1,6}", raw or "")][:12]


def _parse_rows(form) -> list:
    idx = sorted({int(m.group(1)) for k in form.keys() if (m := re.match(r"^r(\d{1,3})_key$", k))})
    rows = []
    for i in idx:
        p = f"r{i}_"
        key = _s(form, p + "key", 20)
        if key not in trip_facts.LABELS and key != "custom":
            raise HTTPException(400, "Неизвестный тип строки")
        label = _s(form, p + "label", 60) or trip_facts.LABELS.get(key, "")
        txt = _s(form, p + "text", 1500)
        if not txt:
            continue
        if not label:
            raise HTTPException(400, "У своей строки нужна подпись")
        verified = form.get(p + "verified") == "1"
        checked_on = _s(form, p + "checked_on", 10)
        if checked_on:
            _date(checked_on)
        if verified and not checked_on:
            checked_on = trip_facts.today_iso()
        ld: dict = {}
        if key == "hours":
            short = _s(form, p + "ld_short", 200)
            if short:
                ld["short"] = short
            for k in ("opens", "closes"):
                v = _s(form, p + "ld_" + k, 5)
                if v and not _TIME_RE.match(v):
                    raise HTTPException(400, f"Время пишите как 09:00, а не «{v}»")
                if v:
                    ld[k] = v
            days = [d for d, _ in DAYS if form.get(p + "ld_day_" + d) == "1"]
            if days and len(days) < 7:
                ld["days"] = days
            hp = _s(form, p + "ld_hours_place", 200)
            if hp:
                ld["hours_place"] = hp
            spec = _spec_from_text(_s(form, p + "ld_spec", 1000))
            if spec:
                ld["spec"] = spec
        elif key == "tickets":
            price = _s(form, p + "ld_price", 10).replace(" ", "")
            if price:
                if not price.isdigit() or int(price) > 1_000_000:
                    raise HTTPException(400, "Цена — целое число рублей, 0 — вход свободный")
                ld["price"] = int(price)
            ld["label"] = _s(form, p + "ld_label", 300)
            ld["place"] = _s(form, p + "ld_place", 300)
            if "price" not in ld and not ld["label"] and not ld["place"]:
                ld = {}
        elif key == "cash":
            if form.get(p + "ld_cash_only") == "1":
                ld["cash_only"] = True
        elif key == "pets":
            v = form.get(p + "ld_allowed")
            if v in ("yes", "no"):
                ld["allowed"] = v == "yes"
        try:
            order = float(form.get(p + "order") or i)
        except ValueError:
            order = i
        rows.append((order, {"key": key, "label": label, "text": txt, "verified": verified,
                             "checked_on": checked_on if verified else (checked_on or ""),
                             "source_url": _url(_s(form, p + "source_url", 500)), "ld": ld}))
    rows.sort(key=lambda x: x[0])
    if len(rows) > MAX_ROWS:
        raise HTTPException(400, f"Не больше {MAX_ROWS} строк")
    return [r for _, r in rows]


def _place_editor_ctx(request, db, cp, b, *, saved="", error=""):
    trails = db.execute(select(Trail.id, Trail.name).order_by(Trail.name)).all()
    names = dict(db.execute(select(Checkpoint.id, Checkpoint.name)).all())
    auto_title = trip_facts.auto_title(dict(b, seo_title=""), cp.name, cp.district)
    auto_desc = trip_facts.auto_description(dict(b, seo_description=""), cp.name)
    from site_app.router import _excerpt
    fallback_desc = auto_desc or _excerpt(cp.description, 200) or cp.name
    f = trip_facts.facts(b, cp.name)
    return _ctx(
        request, tab="places", cp=cp, b=b, row_keys=ROW_KEYS, ld_keys=LD_KEYS, days=DAYS,
        spec_to_text=_spec_to_text, sources_text=_sources_to_text(b.get("sources")),
        trails=trails, names=names, auto_title=auto_title, auto_desc=fallback_desc,
        effective_title=b.get("seo_title") or auto_title, effective_desc=b.get("seo_description") or fallback_desc,
        title_rec=TITLE_RECOMMENDED, desc_rec=DESC_RECOMMENDED, facts=f, checked=trip_facts.checked(b),
        heading=trip_facts.heading(b, cp.name), history=_recent_history(db, "place", cp.id),
        saved=saved, error=error, today=trip_facts.today_iso(),
        page_url=place_url(cp), ld_json=json.dumps(f, ensure_ascii=False, indent=1) if f else "",
    )


@router.get("/admin/texts/places/{place_id}")
def place_editor(request: Request, place_id: int, saved: str = "", db: Session = Depends(get_db),
                 _: str = Depends(require_bot_admin)):
    cp = _place_or_404(db, place_id)
    row = db.get(PlaceTripBlock, place_id)
    b = _block_dict(row) if row else (trip_facts.block_from_code(place_id) or {
        "place_id": place_id, "enabled": False, "heading_name": "", "seo_title": "", "seo_description": "",
        "rows": [], "combine_ids": [], "route_id": None, "auto_visit": True, "search_facts": {}, "sources": [],
        "updated_at": None, "updated_by": None, "from_code": True})
    return _page("texts_place.html", _place_editor_ctx(request, db, cp, b, saved=saved))


def _save_block(db: Session, place_id: int, new: dict, author: str) -> None:
    row = db.get(PlaceTripBlock, place_id)
    if row:
        old = _snapshot(_block_dict(row))
    else:
        code = trip_facts.block_from_code(place_id)
        old = _snapshot(code) if code else None
        row = PlaceTripBlock(place_id=place_id)
        db.add(row)
    for k in ("enabled", "heading_name", "seo_title", "seo_description", "rows", "combine_ids",
              "route_id", "auto_visit", "search_facts", "sources"):
        v = new.get(k)
        if k in ("heading_name", "seo_title", "seo_description"):
            v = v or None
        setattr(row, k, v)
    row.updated_at = datetime.now()
    row.updated_by = author
    _history(db, "place", place_id, old, _snapshot(new), author)
    db.commit()
    _changed()


@router.post("/admin/texts/places/{place_id}")
async def place_save(request: Request, place_id: int, db: Session = Depends(get_db),
                     author: str = Depends(require_bot_admin)):
    same_origin(request)
    cp = _place_or_404(db, place_id)
    form = await request.form()
    route = _s(form, "route_id", 10)
    new = {
        "enabled": form.get("enabled") == "1",
        "heading_name": _s(form, "heading_name", 200),
        "seo_title": " ".join(_s(form, "seo_title", 300).split()),
        "seo_description": " ".join(_s(form, "seo_description", 1000).split()),
        "rows": _parse_rows(form),
        "combine_ids": _ids(_s(form, "combine_ids", 200)),
        "route_id": int(route) if route.isdigit() else None,
        "auto_visit": form.get("auto_visit") == "1",
        "search_facts": {k: v for k in ("locality", "street", "phone") if (v := _s(form, "sf_" + k, 200))},
        "sources": _sources_from_text(_s(form, "sources", 3000)),
    }
    # Адрес страницы: меняется только явно; прежний остаётся 301-редиректом.
    slug = _s(form, "slug", 120)
    if slug and slug != cp.slug:
        set_slug(db, cp, slug)
    _save_block(db, cp.id, new, author)
    return RedirectResponse(f"/admin/texts/places/{cp.id}?saved=1", status_code=303)


@router.post("/admin/texts/places/{place_id}/reset")
async def place_reset(request: Request, place_id: int, db: Session = Depends(get_db),
                      author: str = Depends(require_bot_admin)):
    """Вернуть версию из кода (seo.PLACE_PRACTICAL) — как было до переноса в базу."""
    same_origin(request)
    cp = _place_or_404(db, place_id)
    code = trip_facts.block_from_code(cp.id)
    if not code:
        raise HTTPException(400, "Для этой карточки в коде ничего нет")
    _save_block(db, cp.id, code, author)
    return RedirectResponse(f"/admin/texts/places/{cp.id}?saved=reset", status_code=303)


# ───────────────── тексты страниц ─────────────────

def _texts_rows(db: Session) -> dict:
    return {t.key: t for t in db.execute(select(SiteText)).scalars().all()}


@router.get("/admin/texts/pages")
def pages_list(request: Request, q: str = "", page: str = "", edited: str = "", db: Session = Depends(get_db),
               _: str = Depends(require_bot_admin)):
    reg = site_texts.registry()
    rows = _texts_rows(db)
    ql = q.strip().lower()
    groups: dict = {}
    for key, info in reg.items():
        cur = rows.get(key)
        value = cur.value if cur else info["default"]
        if page and info["page"] != page:
            continue
        if edited and not cur:
            continue
        if ql and ql not in key.lower() and ql not in value.lower() and ql not in info["default"].lower():
            continue
        groups.setdefault(info["page"], {"label": info["page_label"], "url": info["url"], "items": []})["items"].append(
            dict(info, value=value, edited=cur))
    pages = sorted({(i["page"], i["page_label"]) for i in reg.values()}, key=lambda x: list(site_texts.PAGES).index(x[0]) if x[0] in site_texts.PAGES else 99)
    order = list(site_texts.PAGES)
    groups = dict(sorted(groups.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))
    return _page("texts_pages.html", _ctx(request, tab="pages", groups=groups, pages=pages, q=q, page=page,
                                          edited=edited, total=len(reg), n_edited=len([k for k in rows if k in reg])))


@router.get("/admin/texts/pages/edit")
def page_text_editor(request: Request, key: str, saved: str = "", db: Session = Depends(get_db),
                     _: str = Depends(require_bot_admin)):
    info = site_texts.registry().get(key)
    if not info:
        raise HTTPException(404, "Такого текста нет в шаблонах")
    cur = db.get(SiteText, key)
    value = cur.value if cur else info["default"]
    preview = site_texts.render_plain(value) if info["plain"] else site_texts.render_inline(value)
    return _page("texts_page_edit.html", _ctx(request, tab="pages", info=info, cur=cur, value=value,
                                              preview=preview, saved=saved,
                                              history=_recent_history(db, "text", key)))


def _save_text(db: Session, key: str, value: Optional[str], author: str) -> None:
    cur = db.get(SiteText, key)
    old = cur.value if cur else None
    if value is None:
        if cur:
            db.delete(cur)
    else:
        if not cur:
            cur = SiteText(key=key, value=value)
            db.add(cur)
        cur.value = value
        cur.updated_at = datetime.now()
        cur.updated_by = author
    _history(db, "text", key, {"value": old}, {"value": value}, author)
    db.commit()
    _changed()


@router.post("/admin/texts/pages/edit")
async def page_text_save(request: Request, db: Session = Depends(get_db), author: str = Depends(require_bot_admin)):
    same_origin(request)
    form = await request.form()
    key = _s(form, "key", 120)
    info = site_texts.registry().get(key)
    if not info:
        raise HTTPException(404, "Такого текста нет в шаблонах")
    try:
        value = site_texts.validate(str(form.get("value") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if form.get("action") == "reset" or value == info["default"]:
        _save_text(db, key, None, author)
        return RedirectResponse(f"/admin/texts/pages/edit?key={quote(key)}&saved=reset", status_code=303)
    if not value:
        raise HTTPException(400, "Пустой текст нельзя — чтобы вернуть исходный, нажмите «Вернуть исходный»")
    _save_text(db, key, value, author)
    return RedirectResponse(f"/admin/texts/pages/edit?key={quote(key)}&saved=1", status_code=303)


# ───────────────── плашки ─────────────────

_NOTICE_FIELDS = ("slug", "name", "placement", "is_enabled", "priority", "repeat_yearly", "winter_from", "show_from",
                  "show_to", "kicker", "kicker_late", "kicker_late_from", "title", "mode", "body")


def _notice_dict(n: SiteNotice) -> dict:
    return {k: getattr(n, k) for k in _NOTICE_FIELDS + ("id", "updated_at", "updated_by")}


@router.get("/admin/texts/notices")
def notices_list(request: Request, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    rows = db.execute(select(SiteNotice).order_by(SiteNotice.priority.desc(), SiteNotice.id)).scalars().all()
    today = travel_notices.today_msk()
    items = []
    for n in rows:
        d = _notice_dict(n)
        always, winter = travel_notices.notice_windows(d, today)
        d["state"] = ("выключена" if not n.is_enabled else "видна всем" if always
                      else "видна выбравшим зиму" if winter else "не по датам — скрыта")
        items.append(d)
    current = travel_notices.current_notice("podbor", today)
    return _page("texts_notices.html", _ctx(request, tab="notices", items=items, today=today,
                                            current=current, modes=travel_notices.MODES))


def _notice_preview(d: dict) -> Optional[dict]:
    return travel_notices.render_notice(d, travel_notices.today_msk(), force=True)


@router.get("/admin/texts/notices/{notice_id}")
def notice_editor(request: Request, notice_id: str, saved: str = "", db: Session = Depends(get_db),
                  _: str = Depends(require_bot_admin)):
    if notice_id == "new":
        d = {"id": None, "slug": "", "name": "", "placement": "podbor", "is_enabled": False, "priority": 0,
             "repeat_yearly": False, "winter_from": None, "show_from": None, "show_to": None, "kicker": "",
             "kicker_late": "", "kicker_late_from": None, "title": "", "mode": "custom", "body": "",
             "updated_at": None, "updated_by": None}
        history = []
    else:
        if not notice_id.isdigit():
            raise HTTPException(404, "Плашка не найдена")
        n = db.get(SiteNotice, int(notice_id))
        if not n:
            raise HTTPException(404, "Плашка не найдена")
        d = _notice_dict(n)
        history = _recent_history(db, "notice", n.id)
    return _page("texts_notice.html", _ctx(request, tab="notices", n=d, modes=travel_notices.MODES,
                                           preview=_notice_preview(d) if d["id"] else None, saved=saved,
                                           history=history, auto_body=travel_notices.auto_body_markdown()))


def _notice_snapshot(d: dict) -> dict:
    return _jsonable({k: d.get(k) for k in _NOTICE_FIELDS})


@router.post("/admin/texts/notices/save")
async def notice_save(request: Request, db: Session = Depends(get_db), author: str = Depends(require_bot_admin)):
    same_origin(request)
    form = await request.form()
    nid = _s(form, "id", 10)
    n = db.get(SiteNotice, int(nid)) if nid.isdigit() else None
    if nid and not n:
        raise HTTPException(404, "Плашка не найдена")
    if form.get("action") == "delete" and n:
        _history(db, "notice", n.id, _notice_snapshot(_notice_dict(n)), None, author)
        db.delete(n)
        db.commit()
        _changed()
        return RedirectResponse("/admin/texts/notices", status_code=303)
    mode = _s(form, "mode", 20)
    if mode not in travel_notices.MODES:
        raise HTTPException(400, "Неизвестный вид текста")
    name = _s(form, "name", 200)
    if not name:
        raise HTTPException(400, "Нужно название плашки (видно только в админке)")
    try:
        body = site_texts.validate(str(form.get("body") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if mode == "custom" and not body:
        raise HTTPException(400, "Для своего текста заполните поле «Текст»")
    prio = _s(form, "priority", 5)
    vals = {
        "name": name, "placement": "podbor", "is_enabled": form.get("is_enabled") == "1",
        "priority": int(prio) if prio.lstrip("-").isdigit() else 0,
        "repeat_yearly": form.get("repeat_yearly") == "1",
        "winter_from": _date(_s(form, "winter_from", 10)), "show_from": _date(_s(form, "show_from", 10)),
        "show_to": _date(_s(form, "show_to", 10)), "kicker": _s(form, "kicker", 200),
        "kicker_late": _s(form, "kicker_late", 200), "kicker_late_from": _date(_s(form, "kicker_late_from", 10)),
        "title": _s(form, "title", 300), "mode": mode, "body": body,
    }
    if bool(vals["show_from"]) != bool(vals["show_to"]):
        raise HTTPException(400, "Укажите обе даты «показывать всем»: с какого и по какое число")
    if vals["show_from"] and vals["show_to"] and not vals["repeat_yearly"] and vals["show_to"] < vals["show_from"]:
        raise HTTPException(400, "Дата окончания раньше даты начала")
    if vals["winter_from"] and not vals["show_from"]:
        raise HTTPException(400, "«Только тем, кто выбрал зиму» работает до даты «показывать всем с» — укажите её")
    old = _notice_snapshot(_notice_dict(n)) if n else None
    if not n:
        slug = re.sub(r"[^a-z0-9-]+", "-", _s(form, "slug", 60).lower()).strip("-") or f"plashka-{int(datetime.now().timestamp())}"
        if db.execute(select(SiteNotice).where(SiteNotice.slug == slug)).first():
            slug += f"-{int(datetime.now().timestamp())}"
        n = SiteNotice(slug=slug, **vals)
        db.add(n)
        db.flush()
    else:
        for k, v in vals.items():
            setattr(n, k, v)
    n.updated_at = datetime.now()
    n.updated_by = author
    _history(db, "notice", n.id, old, _notice_snapshot(_notice_dict(n)), author)
    db.commit()
    _changed()
    return RedirectResponse(f"/admin/texts/notices/{n.id}?saved=1", status_code=303)


# ───────────────── история ─────────────────

@router.get("/admin/texts/history")
def history_list(request: Request, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    rows = db.execute(select(AdminTextHistory).where(AdminTextHistory.entity != "seed")
                      .order_by(AdminTextHistory.created_at.desc(), AdminTextHistory.id.desc()).limit(200)).scalars().all()
    names = dict(db.execute(select(Checkpoint.id, Checkpoint.name)).all())
    notices = dict(db.execute(select(SiteNotice.id, SiteNotice.name)).all())
    return _page("texts_history.html", _ctx(request, tab="history", rows=rows, names=names, notices=notices,
                                            registry=site_texts.registry()))


@router.post("/admin/texts/history/{hid}/restore")
async def history_restore(request: Request, hid: int, db: Session = Depends(get_db),
                          author: str = Depends(require_bot_admin)):
    """Вернуть состояние «после» этой правки."""
    same_origin(request)
    h = db.get(AdminTextHistory, hid)
    if not h or h.entity == "seed":
        raise HTTPException(404, "Запись истории не найдена")
    if h.entity == "place":
        if not h.new_value:
            raise HTTPException(400, "Нечего возвращать")
        _place_or_404(db, int(h.entity_key))
        _save_block(db, int(h.entity_key), dict(h.new_value), author)
        return RedirectResponse(f"/admin/texts/places/{h.entity_key}?saved=restored", status_code=303)
    if h.entity == "text":
        value = (h.new_value or {}).get("value")
        _save_text(db, h.entity_key, value, author)
        return RedirectResponse(f"/admin/texts/pages/edit?key={quote(h.entity_key)}&saved=restored", status_code=303)
    if h.entity == "notice":
        if not h.new_value:
            raise HTTPException(400, "Это запись об удалении — вернуть можно предыдущую версию")
        n = db.get(SiteNotice, int(h.entity_key))
        vals = dict(h.new_value)
        for k in ("winter_from", "show_from", "show_to", "kicker_late_from"):
            vals[k] = _date(vals.get(k) or "")
        old = _notice_snapshot(_notice_dict(n)) if n else None
        if not n:
            n = SiteNotice(id=int(h.entity_key), **vals)
            db.add(n)
        else:
            for k, v in vals.items():
                setattr(n, k, v)
        n.updated_at = datetime.now()
        n.updated_by = author
        db.flush()
        _history(db, "notice", n.id, old, _notice_snapshot(_notice_dict(n)), author)
        db.commit()
        _changed()
        return RedirectResponse(f"/admin/texts/notices/{n.id}?saved=restored", status_code=303)
    raise HTTPException(400, "Неизвестный тип записи")
