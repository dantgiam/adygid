-- Необязательные поля реестра гостевых домов (к 01.01.2027, ФЗ-127 в ред. ФЗ-557).
-- Только схема и админка; публичный вывод не трогаем.
-- https://www.kremlin.ru/acts/bank/52766
-- https://www.kremlin.ru/acts/bank/51996

ALTER TABLE partners
    ADD COLUMN IF NOT EXISTS stay_registry_number VARCHAR(80),
    ADD COLUMN IF NOT EXISTS stay_registry_url VARCHAR(500),
    ADD COLUMN IF NOT EXISTS stay_registry_listed BOOLEAN,
    ADD COLUMN IF NOT EXISTS stay_registry_checked_on DATE;
