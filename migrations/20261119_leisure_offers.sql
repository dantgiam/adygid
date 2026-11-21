-- Досуг: заявки организаторов, модерация и публичные карточки.
-- Сервисный сбор гостя за досуг — 5% (решение владельца).
-- Таблицу partners и её сбор (жильё и остальные партнёры) не меняем.
-- Повторный запуск безопасен.
-- Черновик (status <> approved или is_published = false) на сайт не выходит.

CREATE TABLE IF NOT EXISTS leisure_providers (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    legal_status VARCHAR(30) NOT NULL,
    legal_details VARCHAR(300),
    licenses_note TEXT,
    insurance_note TEXT,
    has_instructor BOOLEAN NOT NULL DEFAULT FALSE,
    instructor_note TEXT,
    website VARCHAR(500),
    socials VARCHAR(500),
    contact_name VARCHAR(120),
    contact_phone VARCHAR(40),
    contact_messenger VARCHAR(160),
    telegram VARCHAR(200),
    consent_version VARCHAR(20),
    consent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_leisure_providers_code ON leisure_providers (code);

CREATE TABLE IF NOT EXISTS leisure_offers (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES leisure_providers(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    slug VARCHAR(120) UNIQUE,
    activity_type VARCHAR(40) NOT NULL,
    description TEXT NOT NULL,
    meeting_address VARCHAR(300) NOT NULL,
    finish_address VARCHAR(300) NOT NULL,
    lat NUMERIC(9, 6),
    lon NUMERIC(9, 6),
    district VARCHAR(30),
    duration_text VARCHAR(200) NOT NULL,
    seasons VARCHAR(120),
    schedule_text TEXT,
    weather_terms TEXT NOT NULL,
    price_amount NUMERIC(12, 2),
    price_unit VARCHAR(20),
    price_text TEXT NOT NULL,
    included TEXT NOT NULL,
    excluded TEXT NOT NULL,
    group_min INTEGER NOT NULL,
    group_max INTEGER NOT NULL,
    age_text VARCHAR(200) NOT NULL,
    weight_limit TEXT NOT NULL,
    health_limits TEXT NOT NULL,
    difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
    what_to_bring TEXT NOT NULL,
    provided_gear TEXT NOT NULL,
    transfer VARCHAR(20) NOT NULL DEFAULT 'none',
    transfer_note TEXT,
    languages VARCHAR(80),
    language_note VARCHAR(200),
    conditions TEXT NOT NULL,
    cancellation_terms TEXT NOT NULL,
    equipment_state TEXT,
    vest VARCHAR(10) NOT NULL DEFAULT 'na',
    helmet VARCHAR(10) NOT NULL DEFAULT 'na',
    gear_check TEXT NOT NULL,
    briefing VARCHAR(10) NOT NULL DEFAULT 'no',
    briefing_note TEXT,
    category_extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    consent_own_service BOOLEAN NOT NULL DEFAULT FALSE,
    consent_docs BOOLEAN NOT NULL DEFAULT FALSE,
    photos_honest BOOLEAN NOT NULL DEFAULT FALSE,
    photos_vests BOOLEAN NOT NULL DEFAULT FALSE,
    service_fee_pct NUMERIC(5, 2) NOT NULL DEFAULT 5,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    moderation_note TEXT,
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_leisure_offers_provider_id ON leisure_offers (provider_id);
CREATE INDEX IF NOT EXISTS ix_leisure_offers_status ON leisure_offers (status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_leisure_offers_slug ON leisure_offers (slug);

CREATE TABLE IF NOT EXISTS leisure_items (
    id SERIAL PRIMARY KEY,
    offer_id INTEGER NOT NULL REFERENCES leisure_offers(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    quantity INTEGER,
    state_text TEXT NOT NULL,
    price_text VARCHAR(300),
    price_amount NUMERIC(12, 2),
    note TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_leisure_items_offer_id ON leisure_items (offer_id);

CREATE TABLE IF NOT EXISTS leisure_photos (
    id SERIAL PRIMARY KEY,
    offer_id INTEGER NOT NULL REFERENCES leisure_offers(id) ON DELETE CASCADE,
    item_id INTEGER REFERENCES leisure_items(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    thumb_url VARCHAR(500),
    alt VARCHAR(300) NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_leisure_photos_offer_id ON leisure_photos (offer_id);
CREATE INDEX IF NOT EXISTS ix_leisure_photos_item_id ON leisure_photos (item_id);

-- Если таблица уже была создана предыдущей версией этого файла.
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS finish_address VARCHAR(300);
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS weather_terms TEXT;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS weight_limit TEXT;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS provided_gear TEXT;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS cancellation_terms TEXT;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS vest VARCHAR(10) NOT NULL DEFAULT 'na';
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS helmet VARCHAR(10) NOT NULL DEFAULT 'na';
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS gear_check TEXT;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS briefing VARCHAR(10) NOT NULL DEFAULT 'no';
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS briefing_note TEXT;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS category_extra JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS consent_own_service BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS consent_docs BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS photos_honest BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE leisure_offers ADD COLUMN IF NOT EXISTS photos_vests BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE leisure_photos ADD COLUMN IF NOT EXISTS alt VARCHAR(300) NOT NULL DEFAULT '';
ALTER TABLE leisure_providers ADD COLUMN IF NOT EXISTS telegram VARCHAR(200);
