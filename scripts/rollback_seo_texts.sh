#!/bin/sh
# Возвращает seo_title/seo_description 63 страниц к значениям до 21.11.2026.
# Трогает поле, только если там ещё стоит текст этой правки.
# Без доступа к базе: ROLLBACK_SEO_TEXTS_2026_11=1 на сервисе на один деплой.
#
#   DATABASE_URL='postgresql://...' ./scripts/rollback_seo_texts.sh
set -eu
cd "$(dirname "$0")/.."
if [ -z "${DATABASE_URL:-}" ]; then
  echo "Нужна переменная DATABASE_URL" >&2
  exit 1
fi
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/20261121_seo_texts_rollback.sql
echo "Откат выполнен."
