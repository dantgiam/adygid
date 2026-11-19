"""Тесты ходят только в локальную базу. URL задаётся до импорта приложения,
чтобы случайный DATABASE_URL процесса не увёл запись в чужую базу."""
import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "adygid-test"

if "localhost" not in os.environ["DATABASE_URL"] and "127.0.0.1" not in os.environ["DATABASE_URL"]:
    raise RuntimeError("cost-status tests refuse a non-local DATABASE_URL")


import pytest


@pytest.fixture(scope="session", autouse=True)
def _test_ids_away_from_curated_cards():
    """В seo.py ручные настройки привязаны к id боевых карточек (24, 55, 62…).
    На свежей тестовой базе созданное тестом место может получить такой же id
    и «унаследовать» чужой блок фактов, title и JSON-LD. Сдвигаем счётчики
    id мест и маршрутов далеко за боевые значения."""
    import app.main  # noqa: F401  — создаёт таблицы
    from sqlalchemy import text
    from app.database import engine
    with engine.begin() as conn:
        for table in ("checkpoints", "trails"):
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table}), 100000))"
            ))
    yield
