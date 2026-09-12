FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# postgresql-client-17 (matching the postgres:17 service) so `pg_dump` is
# available for apps.accounts.tasks.run_database_backup (Phase 17 manual DB
# backup) -- this base image's own Debian release already carries it.
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

# psycopg[binary] ships wheels, so no build toolchain is needed here.
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000

# Invoked via `sh` so a bind-mounted source tree without the +x bit still works.
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["gunicorn", "hexagare.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
