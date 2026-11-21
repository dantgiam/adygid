-- SEO-тексты статей, маршрутов, округов и сценариев правятся в админке.
-- Повторяемая: выполняется при каждом старте (app/main.py), только
-- ADD COLUMN IF NOT EXISTS — существующие тексты, часы и цены не трогает.
-- Пустая колонка — на сайте остаётся словарь site_app/seo.py, затем шаблон.
-- У сценария description уже был (seo_description VARCHAR(500)), добавляем title.

ALTER TABLE articles ADD COLUMN IF NOT EXISTS seo_title VARCHAR(80);
ALTER TABLE articles ADD COLUMN IF NOT EXISTS seo_description VARCHAR(230);

ALTER TABLE trails ADD COLUMN IF NOT EXISTS seo_title VARCHAR(80);
ALTER TABLE trails ADD COLUMN IF NOT EXISTS seo_description VARCHAR(230);

ALTER TABLE districts ADD COLUMN IF NOT EXISTS seo_title VARCHAR(80);
ALTER TABLE districts ADD COLUMN IF NOT EXISTS seo_description VARCHAR(230);

ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS seo_title VARCHAR(80);
