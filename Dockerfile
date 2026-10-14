FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# sqlite3 CLI is used by the backup service and for manual restores.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 10001 --user-group --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.lock ./
RUN pip install -r requirements.lock

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY docker/entrypoint.sh docker/backup.sh /usr/local/bin/

RUN chmod 0755 /usr/local/bin/entrypoint.sh /usr/local/bin/backup.sh \
    && mkdir -p /data /backups \
    && chown app:app /data /backups

USER app

ENV DATABASE_URL=sqlite:////data/app.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["entrypoint.sh"]
