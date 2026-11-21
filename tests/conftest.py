"""Тесты ходят только в локальную базу. URL задаётся до импорта приложения,
чтобы случайный DATABASE_URL процесса не увёл запись в чужую базу."""
import os

# ADYGID_TEST_DB — имя отдельной локальной базы, чтобы два прогона из разных
# веток (worktree) не мешали друг другу. Хост всегда localhost.
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://adygid:adygid@localhost:5432/" + os.environ.get("ADYGID_TEST_DB", "adygid_test")
)
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "adygid-test"

if "localhost" not in os.environ["DATABASE_URL"] and "127.0.0.1" not in os.environ["DATABASE_URL"]:
    raise RuntimeError("cost-status tests refuse a non-local DATABASE_URL")


import pytest


def _install_admin_form_origin():
    """Браузер на POST из формы админки сам шлёт Origin. TestClient — нет.

    Подставляем Origin тестового хоста, только если тест не задал ни Origin,
    ни Referer. Явный чужой заголовок не затираем: проверки CSRF на нём
    остаются. Запрос совсем без обоих заголовков собирается мимо TestClient.
    """
    from fastapi.testclient import TestClient

    original = TestClient.request

    def request(self, method, url, **kwargs):
        headers = kwargs.get("headers")
        if headers is None:
            pairs = []
        elif hasattr(headers, "multi_items"):
            pairs = list(headers.multi_items())
        elif hasattr(headers, "items"):
            pairs = list(headers.items())
        else:
            pairs = list(headers)
        keys = {str(key).lower() for key, _ in pairs}
        path = url if isinstance(url, str) else str(getattr(url, "path", url))
        if (
            str(method).upper() == "POST"
            and path.startswith("/admin")
            and "origin" not in keys
            and "referer" not in keys
        ):
            base = str(getattr(self, "base_url", "http://testserver")).rstrip("/")
            kwargs["headers"] = dict(pairs) | {"Origin": base}
        return original(self, method, url, **kwargs)

    TestClient.request = request


_install_admin_form_origin()


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
