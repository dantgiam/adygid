"""Транслитерация и генерация уникальных slug для статей.

Отдельный модуль (а не app.main), чтобы его можно было импортировать из
скриптов вроде seed_demo.py без побочных эффектов (создание FastAPI-приложения,
повторные ALTER TABLE) — импорт app.main внутри уже открытой транзакции к тем
же таблицам приводит к самоблокировке в Postgres.
"""
import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article

_TRANSLIT = {
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i",
    "й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t",
    "у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"",
    "э":"e","ю":"yu","я":"ya",
}


def slugify(text_: str) -> str:
    out = []
    for ch in text_.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug or uuid.uuid4().hex[:8]


def unique_slug(db: Session, base_slug: str, exclude_id: Optional[int] = None, model=Article) -> str:
    slug = base_slug
    i = 2
    while True:
        q = select(model.id).where(model.slug == slug)
        if exclude_id is not None:
            q = q.where(model.id != exclude_id)
        if db.execute(q).first() is None:
            return slug
        slug = f"{base_slug}-{i}"
        i += 1
