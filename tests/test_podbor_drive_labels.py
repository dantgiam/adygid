"""Время в пути в плане подбора: откуда считаем — у каждой точки,
а пометка «приблизительно, по прямой» — один раз у итога дня."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "site_app/static/podbor.js").read_text(encoding="utf-8")
CORE = (ROOT / "site_app/static/podbor-core.js").read_text(encoding="utf-8")


def test_stop_labels_say_from_where():
    assert '"от базы" + (baseName ? " (" + baseName + ")" : "") + " на машине"' in JS
    assert '"переезд на машине"' in JS
    assert "обратно на базу на машине" in JS
    assert "по расчёту сайта" not in JS


def test_estimate_note_once_per_day_summary():
    assert JS.count("время в пути приблизительное, по прямой") == 1
    i = JS.index("function dayHtml")
    assert JS.index("время в пути приблизительное, по прямой") > i
    assert "a3-drive-note" in (ROOT / "site_app/static/podbor.css").read_text(encoding="utf-8")


def test_no_unused_walk_estimate():
    assert "walkMin" not in JS and "walkMin" not in CORE
