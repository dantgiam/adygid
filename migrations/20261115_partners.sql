-- Партнёры АдыГида: анкеты поставщиков, карточки партнёров и брони (лиды).
-- Модель 15.11: партнёр ничего не платит. Турист платит АдыГиду собственный
-- сервисный сбор за подбор и бронь, остальное — партнёру на месте.
-- Персональные данные (имя контакта, телефон, мессенджер) пишутся в contact_*
-- только при PARTNER_PD_IN_SITE_DB=1. Иначе контакты приходят через бота (YDB, РФ).
-- В лидах нет имени и телефона туриста — только номер обращения в боте.
-- Повторный запуск безопасен.

CREATE TABLE IF NOT EXISTS partner_applications (
    id SERIAL PRIMARY KEY,
    code VARCHAR(12) NOT NULL UNIQUE,
    company VARCHAR(200) NOT NULL,
    category VARCHAR(40) NOT NULL,
    subcategory VARCHAR(40),
    location VARCHAR(200),
    services TEXT,
    prices TEXT,
    seasons VARCHAR(120),
    discount TEXT,
    booking_terms TEXT,
    website VARCHAR(500),
    socials VARCHAR(500),
    lead_channels VARCHAR(120),
    comment TEXT,
    contact_name VARCHAR(120),
    contact_phone VARCHAR(40),
    contact_messenger VARCHAR(120),
    consent_version VARCHAR(20),
    consent_at TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'new',
    notes TEXT,
    partner_id INTEGER,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_partner_applications_status ON partner_applications (status);

CREATE TABLE IF NOT EXISTS partners (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(40) NOT NULL,
    subcategory VARCHAR(40),
    location VARCHAR(200),
    short TEXT,
    description TEXT,
    photos JSONB NOT NULL DEFAULT '[]'::jsonb,
    price_from VARCHAR(120),
    seasons VARCHAR(120),
    discount TEXT,
    booking_terms TEXT,
    cancellation_terms TEXT,
    service_fee_pct NUMERIC(5,2) NOT NULL DEFAULT 5,
    place_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    route_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    contacts JSONB NOT NULL DEFAULT '{}'::jsonb,
    agreement VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    application_id INTEGER,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS partner_leads (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    inbox_ref VARCHAR(40),
    service VARCHAR(200),
    service_date DATE,
    people VARCHAR(60),
    status VARCHAR(20) NOT NULL DEFAULT 'requested',
    provider_price NUMERIC(12,2),
    discount_amount NUMERIC(12,2),
    service_fee_pct NUMERIC(5,2),
    service_fee_amount NUMERIC(12,2),
    fee_status VARCHAR(20) NOT NULL DEFAULT 'not_paid',
    is_repeat BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_partner_leads_partner_id ON partner_leads (partner_id);
