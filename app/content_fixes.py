"""Точечные правки контента в базе, которые повторяются на каждом старте
и ничего не делают, если уже применены или данные не те (проверка по
названиям, а не только по id).

Маршрут «Уна-Коз понизу»: в описании были ссылки на /mesta/95, 96, 97 —
это точки маршрута без своей страницы, ссылки отдавали 404. Две из них
совпадают с настоящими карточками мест: верхняя станция → «Савранская
канатная дорога», выход к Чёртову пальцу → «Скала Чёртов палец». Третья
(вход в пещеру Пыльную) отдельной карточки не имеет — её ссылку при выводе
страницы site_app/urls.py ведёт на точку в списке маршрута (#stop-96).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Checkpoint, Trail

# (маршрут, начало названия точки, точное название карточки места)
_STOP_TO_PLACE = [
    ("Уна-Коз понизу", "Старт: верхняя станция Савранской канатной дороги", "Савранская канатная дорога"),
    ("Уна-Коз понизу", "Выход к Чёртову пальцу", "Скала Чёртов палец"),
]


def fix_stop_links(db: Session) -> int:
    changed = 0
    for trail_prefix, stop_name, place_name in _STOP_TO_PLACE:
        place = db.execute(select(Checkpoint).where(
            Checkpoint.name == place_name, Checkpoint.show_as_place == True, Checkpoint.is_published == True,
        )).scalars().first()
        if not place:
            continue
        for t in db.execute(select(Trail).where(Trail.name.startswith(trail_prefix))).scalars().all():
            for cp in t.checkpoints:
                if cp.show_as_place or not cp.name.startswith(stop_name):
                    continue
                old = f'href="/mesta/{cp.id}"'
                if t.description and old in t.description:
                    # Без onupdate: это ремонт ссылки, а не правка маршрута.
                    db.execute(Trail.__table__.update().where(Trail.id == t.id).values(
                        description=t.description.replace(old, f'href="/mesta/{place.id}"'),
                        updated_at=Trail.__table__.c.updated_at,
                    ))
                    db.refresh(t)
                    changed += 1
    return changed


def apply(engine) -> int:
    with Session(engine) as db:
        n = fix_stop_links(db)
        db.commit()
    return n
