"""Админка поездок автора: /admin/poezdki. Тот же HTTP Basic, что у /admin.

Черновик по умолчанию. Публичный адрес — /poezdki/<slug>; числовой id
и прежний слаг отвечают 301. Тексты самой страницы раздела правятся
в «Текстах сайта», здесь — записи поездок.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bot_admin import _page, require_bot_admin
from app.database import get_db
from app.models import AuthorTrip, Checkpoint
from app.slugs import entity_slug_base, not_digits, set_slug, slugify, unique_slug
from app.texts_admin import _s, _url, same_origin

router = APIRouter()

_MAX_PHOTOS = 12


def _places(db: Session) -> list:
    rows = db.execute(
        select(Checkpoint.id, Checkpoint.name, Checkpoint.is_published)
        .where(Checkpoint.show_as_place == True)
        .order_by(Checkpoint.name)
    ).all()
    return [{"id": i, "name": n, "published": bool(p)} for i, n, p in rows]


def _photo_rows(trip: Optional[AuthorTrip]) -> list:
    rows = [{"url": p.get("url") or "", "alt": p.get("alt") or ""} for p in ((trip.photos if trip else None) or [])]
    while len(rows) < 3:
        rows.append({"url": "", "alt": ""})
    if rows[-1]["url"] and len(rows) < _MAX_PHOTOS:
        rows.append({"url": "", "alt": ""})
    return rows[:_MAX_PHOTOS]


def _form_ctx(request, db, trip, saved: str):
    selected = set(trip.place_ids or []) if trip and trip.id else set()
    return {
        "request": request,
        "section": "trips",
        "trip": trip,
        "photos": _photo_rows(trip),
        "places": _places(db),
        "selected": selected,
        "saved": saved,
        "date_value": trip.trip_date.isoformat() if trip and trip.trip_date else "",
    }


@router.get("/admin/poezdki")
def trips_list(request: Request, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    rows = db.execute(select(AuthorTrip).order_by(AuthorTrip.trip_date.desc(), AuthorTrip.id.desc())).scalars().all()
    return _page("trips_admin_list.html", {"request": request, "section": "trips", "trips": rows})


@router.get("/admin/poezdki/new")
def trip_new(request: Request, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    blank = AuthorTrip(title="", trip_date=date.today(), body="", photos=[], place_ids=[], is_published=False)
    return _page("trips_admin_edit.html", _form_ctx(request, db, blank, ""))


@router.get("/admin/poezdki/{trip_id}")
def trip_edit(request: Request, trip_id: int, saved: str = "",
              db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    trip = db.get(AuthorTrip, trip_id)
    if not trip:
        raise HTTPException(404, "Поездка не найдена")
    return _page("trips_admin_edit.html", _form_ctx(request, db, trip, saved))


def _photos(form) -> list:
    urls = form.getlist("photo_url")
    alts = form.getlist("photo_alt")
    out = []
    for i, raw in enumerate(urls):
        url = str(raw or "").strip()
        alt = str(alts[i] if i < len(alts) else "").strip()
        if not url:
            continue
        if len(out) >= _MAX_PHOTOS:
            raise HTTPException(400, f"Фото не больше {_MAX_PHOTOS}")
        url = _url(url)
        if not url.startswith("https://"):
            raise HTTPException(400, "Адрес фото должен начинаться с https://")
        if len(url) > 500:
            raise HTTPException(400, "Слишком длинный адрес фото")
        if not alt:
            raise HTTPException(400, "У каждого фото нужен alt — коротко, что на кадре")
        if len(alt) > 180:
            raise HTTPException(400, "Alt длиннее 180 знаков")
        out.append({"url": url, "alt": alt})
    return out


def _place_ids(db: Session, form) -> list:
    raw = form.getlist("place_ids")
    ids = []
    for item in raw:
        if not str(item).isdigit():
            continue
        ids.append(int(item))
    if not ids:
        return []
    found = {i for i, in db.execute(select(Checkpoint.id).where(Checkpoint.id.in_(ids), Checkpoint.show_as_place == True)).all()}
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(400, "Неизвестное место: " + ", ".join(str(i) for i in missing))
    # порядок чекбоксов сохраняем, без повторов
    seen = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    return seen


@router.post("/admin/poezdki/save")
async def trip_save(request: Request, db: Session = Depends(get_db), _: str = Depends(require_bot_admin)):
    same_origin(request)
    form = await request.form()
    raw_id = _s(form, "id", 12)
    trip = db.get(AuthorTrip, int(raw_id)) if raw_id.isdigit() else None
    if raw_id and trip is None:
        raise HTTPException(404, "Поездка не найдена")
    if form.get("action") == "delete":
        if trip is None:
            raise HTTPException(404, "Поездка не найдена")
        db.delete(trip)
        db.commit()
        return RedirectResponse("/admin/poezdki?deleted=1", status_code=303)

    title = _s(form, "title", 255)
    if not title:
        raise HTTPException(400, "Нужен заголовок")
    try:
        trip_date = date.fromisoformat(_s(form, "trip_date", 10))
    except ValueError:
        raise HTTPException(400, "Нужна дата поездки")
    body = _s(form, "body", 20000)
    changes = _s(form, "changes_note", 4000) or None
    spent = _s(form, "spent_note", 255) or None
    video = _url(_s(form, "video_url", 500)) or None
    source = _url(_s(form, "source_url", 500)) or None
    if video and not video.startswith("https://"):
        raise HTTPException(400, "Ссылка на видео должна начинаться с https://")
    if source and not source.startswith("https://"):
        raise HTTPException(400, "Ссылка на пост должна начинаться с https://")
    photos = _photos(form)
    place_ids = _place_ids(db, form)
    published = form.get("is_published") == "1"
    requested = _s(form, "slug", 120)

    if trip is None:
        if requested:
            base = not_digits(slugify(requested)[:120].strip("-"), "trip")
        else:
            base = entity_slug_base(title, "trip")
        trip = AuthorTrip(
            title=title, trip_date=trip_date, body=body, slug=unique_slug(db, base, model=AuthorTrip),
            photos=photos, video_url=video, changes_note=changes, spent_note=spent,
            place_ids=place_ids, source_url=source, is_published=published,
        )
        db.add(trip)
        db.commit()
        return RedirectResponse(f"/admin/poezdki/{trip.id}?saved=1", status_code=303)

    trip.title = title
    trip.trip_date = trip_date
    trip.body = body
    trip.photos = photos
    trip.video_url = video
    trip.changes_note = changes
    trip.spent_note = spent
    trip.place_ids = place_ids
    trip.source_url = source
    trip.is_published = published
    if requested:
        set_slug(db, trip, requested)
    db.commit()
    return RedirectResponse(f"/admin/poezdki/{trip.id}?saved=1", status_code=303)
