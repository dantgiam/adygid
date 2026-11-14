-- Сохранённые планы подбора («Сохранить план в бота»).
-- Короткий случайный id и состав плана (ключи мест/маршрутов по дням).
-- Без имён, телефонов и id мессенджеров. Повторный запуск безопасен.

CREATE TABLE IF NOT EXISTS podbor_plans (
    id VARCHAR(16) PRIMARY KEY,
    session_id VARCHAR(64),
    sig VARCHAR(64) NOT NULL,
    data TEXT NOT NULL,
    opens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT now(),
    last_open_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_podbor_plans_session_sig ON podbor_plans (session_id, sig);
