#!/bin/sh
# Возвращает seo_title пяти районов к живым формулировкам 21.11.2026.
# Трогает поле, только если там ещё стоит текст «{район}: что посмотреть».
# Описание района не меняет.
# Без доступа к базе: ROLLBACK_DISTRICT_LOOK_TITLES=1 на сервисе на один деплой.
#
#   DATABASE_URL='postgresql://...' ./scripts/rollback_district_look_titles.sh
set -eu
cd "$(dirname "$0")/.."
if [ -z "${DATABASE_URL:-}" ]; then
  echo "Нужна переменная DATABASE_URL" >&2
  exit 1
fi
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/20261121_district_look_titles_rollback.sql
echo "Откат выполнен."
