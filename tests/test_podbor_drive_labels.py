"""Подписи времени в пути: на машине, оценка по прямой, не навигатор.

База не нужна: проверяем тексты в клиентском коде подборщика.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plan_labels_say_car_estimate_not_router():
    js = (ROOT / "site_app/static/podbor.js").read_text(encoding="utf-8")
    assert "от базы на машине" in js
    assert "переезд на машине" in js
    assert "обратно на базу на машине" in js
    assert "оценка по прямой, не навигатор" in js
    assert "рядом с базой, без переезда на машине" in js
    assert "пеший подход от парковки в этой цифре отдельно не выделен" in js
    assert "по расчёту сайта" not in js


def test_core_exports_walk_min_and_keeps_drive_formula():
    core = (ROOT / "site_app/static/podbor-core.js").read_text(encoding="utf-8")
    assert "function walkMin" in core
    assert "walkSpeedKmh:4" in core
    assert "parkingMin" in core and "mountainFactor:1.3" in core
    assert "walkMin," in core  # экспортируется
