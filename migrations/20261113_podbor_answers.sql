-- Анонимные ответы подборщика маршрутов.
-- Только случайный session_id и коды ответов. Имён, телефонов и свободного текста нет.
-- Повторный запуск безопасен.

CREATE TABLE IF NOT EXISTS podbor_answers (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    question_id VARCHAR(40),
    answer_code VARCHAR(80),
    skipped BOOLEAN NOT NULL DEFAULT FALSE,
    item_key VARCHAR(40),
    plan_id VARCHAR(32),
    algorithm_version VARCHAR(80),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_podbor_answers_session_id ON podbor_answers (session_id);

CREATE INDEX IF NOT EXISTS ix_podbor_answers_question_id ON podbor_answers (question_id);
