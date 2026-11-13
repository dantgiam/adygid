"""Приём анонимных ответов подборщика и простые агрегаты для админки.

В таблицу пишутся только коды. Если таблицы ещё нет — пишем в лог и
отвечаем 202, страница подбора из-за этого не ждёт и не падает.
"""
import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import PodborAnswer

log = logging.getLogger("adygid.podbor")
router = APIRouter()

_EVENT_TYPES = {
    "answer",
    "plan_build",
    "podbor_like",
    "podbor_dislike",
    "place_seen_before",
    "plan_vote",
    "plan_dislike_reason",
    "plan_density",
    "plan_fix",
    "podbor_feedback_max",
    "alt_toggle",
}
_QUESTIONS = {
    "season", "duration", "base", "party", "been", "pace", "interests",
    "childage", "walking", "distance", "rain", "exclude",
}
_VERSION_RE = re.compile(r"^[A-Za-z0-9 .·_-]{1,80}$")
_CHILD_PARTIES = {"family", "small"}


class PodborEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = Field(pattern=r"^[a-z_]{1,40}$")
    question_id: str | None = Field(default=None, pattern=r"^[a-z]{1,40}$")
    answer_code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_,-]{1,80}$")
    skipped: bool = False
    item_key: str | None = Field(default=None, pattern=r"^(place|route):\d{1,6}$")
    plan_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,32}$")
    algorithm_version: str | None = Field(default=None, max_length=80)


class PodborBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    events: list[PodborEventIn] = Field(min_length=1, max_length=40)


def ensure_podbor_table() -> None:
    """Повторяемая миграция. Ошибка не должна ронять старт сайта."""
    path = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261113_podbor_answers.sql")
    try:
        raw = open(path, encoding="utf-8").read()
    except OSError:
        log.warning("podbor migration file missing: %s", path)
        return
    statements = []
    for chunk in raw.split(";"):
        lines = [ln for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    except Exception:
        log.exception("podbor_answers migration failed; answers will return 202 until the table exists")


def _check_event(ev: PodborEventIn) -> None:
    if ev.event_type not in _EVENT_TYPES:
        raise HTTPException(400, "Неизвестный тип события")
    if ev.question_id and ev.question_id not in _QUESTIONS:
        raise HTTPException(400, "Неизвестный вопрос")
    if ev.algorithm_version and not _VERSION_RE.match(ev.algorithm_version):
        raise HTTPException(400, "Некорректная версия алгоритма")
    if ev.answer_code and re.search(r"\d{7,}", ev.answer_code):
        raise HTTPException(400, "В ответе не должно быть длинных чисел")


def _missing_table(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "podbor_answers" in msg or "does not exist" in msg or "undefinedtable" in msg


def save_answers(db: Session, batch: PodborBatchIn) -> dict:
    for ev in batch.events:
        _check_event(ev)
    rows = [
        PodborAnswer(
            session_id=batch.session_id,
            event_type=ev.event_type,
            question_id=ev.question_id,
            answer_code=ev.answer_code,
            skipped=ev.skipped,
            item_key=ev.item_key,
            plan_id=ev.plan_id,
            algorithm_version=ev.algorithm_version,
        )
        for ev in batch.events
    ]
    try:
        db.add_all(rows)
        db.commit()
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        if _missing_table(exc):
            log.warning("podbor_answers table missing; %s events not stored", len(rows))
            return {"ok": True, "stored": 0}
        raise
    return {"ok": True, "stored": len(rows)}


def podbor_stats(db: Session) -> dict:
    """Сколько сессий с детьми и без, и расклад ответов по вопросам.

    Берётся последний ответ сессии на вопрос. «С детьми» — party family или small.
    """
    empty = {
        "available": False,
        "sessions": 0,
        "with_children": 0,
        "without_children": 0,
        "by_question": {},
    }
    try:
        total = db.execute(select(func.count(func.distinct(PodborAnswer.session_id)))).scalar() or 0
        rows = db.execute(
            select(
                PodborAnswer.session_id,
                PodborAnswer.question_id,
                PodborAnswer.answer_code,
                PodborAnswer.skipped,
            )
            .where(PodborAnswer.event_type == "answer")
            .order_by(PodborAnswer.id.asc())
        ).all()
    except (ProgrammingError, OperationalError) as exc:
        db.rollback()
        if _missing_table(exc):
            log.warning("podbor_answers table missing; stats unavailable")
            return empty
        raise

    latest: dict = {}
    for row in rows:
        if not row.question_id:
            continue
        latest[(row.session_id, row.question_id)] = "any" if row.skipped else (row.answer_code or "any")

    by_question: dict = {}
    party: dict = {}
    for (sid, question), answer in latest.items():
        bucket = by_question.setdefault(question, {})
        bucket[answer] = bucket.get(answer, 0) + 1
        if question == "party":
            party[sid] = answer

    with_children = sum(1 for answer in party.values() if answer in _CHILD_PARTIES)
    without = sum(1 for answer in party.values() if answer not in _CHILD_PARTIES)
    return {
        "available": True,
        "sessions": total,
        "with_children": with_children,
        "without_children": without,
        "by_question": by_question,
    }


@router.post("/api/podbor/answers", status_code=202)
def post_podbor_answers(body: PodborBatchIn, db: Session = Depends(get_db)):
    return save_answers(db, body)
