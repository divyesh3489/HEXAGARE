#!/bin/sh
set -e

# Only the web service should run migrations / collectstatic; workers wait on it.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "==> Applying database migrations"
    python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-false}" = "true" ]; then
    echo "==> Collecting static files"
    python manage.py collectstatic --noinput
fi

exec "$@"
