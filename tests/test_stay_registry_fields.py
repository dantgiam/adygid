"""Поля реестра гостевых домов: схема и админка, без публичного вывода.

База не нужна. Юридический вывод, является ли Адыгид агрегатором, здесь
не делается.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_model_and_migration_add_optional_registry_columns():
    models = (ROOT / "app/models.py").read_text(encoding="utf-8")
    for name in (
        "stay_registry_number",
        "stay_registry_url",
        "stay_registry_listed",
        "stay_registry_checked_on",
    ):
        assert name in models
    assert "nullable=True" in models  # listed может быть «не знаем»
    sql = (ROOT / "migrations/20261119_partner_stay_registry.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS stay_registry_number" in sql
    assert "UPDATE partners" not in sql
    assert "kremlin.ru/acts/bank/52766" in sql


def test_admin_can_edit_fields_and_save_function_writes_them():
    card = (ROOT / "app/templates/partners_card.html").read_text(encoding="utf-8")
    assert 'id="stay-registry"' in card
    assert "только админка" in card
    assert "name=\"stay_registry_number\"" in card
    assert "name=\"stay_registry_url\"" in card
    assert "ФЗ-557" in card
    admin = (ROOT / "app/partners_admin.py").read_text(encoding="utf-8")
    assert "p.stay_registry_number" in admin
    assert 'startswith("https://")' in admin
    assert "stay_registry_listed" in admin


def test_public_partner_pages_do_not_render_registry_fields():
    public = [
        ROOT / "site_app/templates/partners.html",
        ROOT / "site_app/templates/_partners_mock.html",
    ]
    for path in public:
        text = path.read_text(encoding="utf-8")
        assert "stay_registry" not in text, path
        assert "реестр" not in text.lower()
