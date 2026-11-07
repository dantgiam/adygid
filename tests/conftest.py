"""Тесты ходят только в локальную базу. URL задаётся до импорта приложения,
чтобы случайный DATABASE_URL процесса не увёл запись в чужую базу."""
import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "adygid-test"

if "localhost" not in os.environ["DATABASE_URL"] and "127.0.0.1" not in os.environ["DATABASE_URL"]:
    raise RuntimeError("cost-status tests refuse a non-local DATABASE_URL")
