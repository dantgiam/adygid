#!/bin/sh
# Та же запись, что и боевой деплой с APPLY_ARTICLE_CAROUSELS=1.
# Строка меняется только если текст совпадает со снимком before.json.
#
#   DATABASE_URL='postgresql://...' ./scripts/apply_article_carousels.sh
set -eu
cd "$(dirname "$0")/.."
if [ -z "${DATABASE_URL:-}" ]; then
  echo "Нужна переменная DATABASE_URL" >&2
  exit 1
fi
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/20261120_article_carousels.sql
echo "Ленты записаны."
