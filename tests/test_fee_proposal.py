"""Предложение сменить сервисный сбор по умолчанию с 5% на 3%.

Тесты читают исходники и шаблон, база и SQLAlchemy не нужны. Решение
владельца ещё не утверждено: ветку в main не мержить без явного согласия.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_default_fee_constant_is_three_percent():
    models = (ROOT / "app/models.py").read_text(encoding="utf-8")
    assert "DEFAULT_SERVICE_FEE_PCT = 3" in models
    assert "default=DEFAULT_SERVICE_FEE_PCT" in models
    admin = (ROOT / "app/partners_admin.py").read_text(encoding="utf-8")
    assert "service_fee_pct=Decimal(DEFAULT_SERVICE_FEE_PCT)" in admin
    assert "Decimal(\"5\")" not in admin or admin.count("service_fee_pct=Decimal(\"5\")") == 0


def test_public_partners_page_uses_three_percent_example():
    html = (ROOT / "site_app/templates/partners.html").read_text(encoding="utf-8")
    assert "около 3%" in html
    assert "≈ 3%" in html
    assert "−150 ₽" in html
    assert "4 850 ₽" in html
    assert "150 ₽" in html
    assert 'value="3% — в размере сервисного сбора АдыГида"' in html
    # «5 минут» на анкету — это время, не сбор; его не трогаем.
    assert "около 5 минут" in html
    assert "около 5%" not in html
    assert "скидка 5%" not in html
    assert "−250 ₽" not in html
    assert "4 750 ₽" not in html


def test_new_migration_only_changes_the_default():
    sql = (ROOT / "migrations/20261119_partner_fee_default_3.sql").read_text(encoding="utf-8")
    assert "SET DEFAULT 3" in sql
    assert "UPDATE partners" not in sql
    old = (ROOT / "migrations/20261115_partners.sql").read_text(encoding="utf-8")
    assert "DEFAULT 5" in old
