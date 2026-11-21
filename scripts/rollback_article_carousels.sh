#!/bin/sh
# Одна команда, которая возвращает статьи, маршруты и сценарии
# к тексту из снимка. Карточки мест не затрагивает.
# Срабатывает только у строк, где ещё стоит метка этой правки.
#
#   DATABASE_URL='postgresql://...' ./scripts/rollback_article_carousels.sh
set -eu
cd "$(dirname "$0")/.."
if [ -z "${DATABASE_URL:-}" ]; then
  echo "Нужна переменная DATABASE_URL" >&2
  exit 1
fi
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/20261120_article_carousels_rollback.sql
echo "Откат выполнен."
