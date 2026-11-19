-- Тексты сайта в админке: «Коротко для поездки», плашки, тексты страниц, история.
-- Повторяемая: выполняется при каждом старте (site_app/admin_texts_db.py,
-- ensure_admin_text_tables), только CREATE ... IF NOT EXISTS — существующие
-- данные не трогает. Начальное наполнение — там же, INSERT ... ON CONFLICT DO NOTHING.

CREATE TABLE IF NOT EXISTS place_trip_blocks (
    place_id INTEGER PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    heading_name VARCHAR(200),
    seo_title VARCHAR(300),
    seo_description TEXT,
    rows JSONB NOT NULL DEFAULT '[]'::jsonb,
    combine_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    route_id INTEGER,
    auto_visit BOOLEAN NOT NULL DEFAULT TRUE,
    search_facts JSONB NOT NULL DEFAULT '{}'::jsonb,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP DEFAULT now(),
    updated_by VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS site_notices (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    placement VARCHAR(40) NOT NULL DEFAULT 'podbor',
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,
    repeat_yearly BOOLEAN NOT NULL DEFAULT TRUE,
    winter_from DATE,
    show_from DATE,
    show_to DATE,
    kicker VARCHAR(200),
    kicker_late VARCHAR(200),
    kicker_late_from DATE,
    title VARCHAR(300),
    mode VARCHAR(20) NOT NULL DEFAULT 'custom',
    body TEXT,
    updated_at TIMESTAMP DEFAULT now(),
    updated_by VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS site_texts (
    key VARCHAR(120) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT now(),
    updated_by VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS admin_text_history (
    id SERIAL PRIMARY KEY,
    entity VARCHAR(40) NOT NULL,
    entity_key VARCHAR(120) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    author VARCHAR(120),
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_admin_text_history_entity ON admin_text_history (entity, entity_key, created_at DESC);
