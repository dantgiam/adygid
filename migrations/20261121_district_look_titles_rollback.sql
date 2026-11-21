-- Откат заголовков районов «что посмотреть».
-- Трогает seo_title, только если там ещё наш текст. Описание не меняет.
BEGIN;
UPDATE districts SET seo_title = CASE WHEN seo_title = 'Майкоп и окрестности: что посмотреть' THEN 'Майкоп и окрестности: что посмотреть и где термы' ELSE seo_title END WHERE id = 1 AND slug = 'maikop';
UPDATE districts SET seo_title = CASE WHEN seo_title = 'Хаджох (Каменномостский): что посмотреть' THEN 'Каменномостский (Хаджох): что посмотреть рядом' ELSE seo_title END WHERE id = 2 AND slug = 'khadzhokh';
UPDATE districts SET seo_title = CASE WHEN seo_title = 'Даховская: что посмотреть' THEN 'Даховская: что посмотреть и куда съездить' ELSE seo_title END WHERE id = 3 AND slug = 'dakhovskaya';
UPDATE districts SET seo_title = CASE WHEN seo_title = 'Плато Лаго-Наки: что посмотреть' THEN 'Лаго-Наки: как доехать, смотровые и прогулки' ELSE seo_title END WHERE id = 4 AND slug = 'lagonaki';
UPDATE districts SET seo_title = CASE WHEN seo_title = 'Гузерипль: что посмотреть' THEN 'Гузерипль: что посмотреть у входа в заповедник' ELSE seo_title END WHERE id = 5 AND slug = 'guzeripl';
COMMIT;
