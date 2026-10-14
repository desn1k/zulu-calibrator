# HANDOFF

## 0. Current state

- PR-1 (project skeleton) is in review on branch `pr-1-skeleton`:
  - FastAPI app factory (`app/main.py`), settings from env (`app/config.py`), SQLAlchemy engine with
    SQLite WAL + foreign keys (`app/db.py`), empty declarative `Base` (`app/models/`).
  - Alembic wired to `Base.metadata`, empty baseline revision `0001`; the container runs
    `alembic upgrade head` on start.
  - `GET /healthz` (DB `SELECT 1`, 503 if the DB is unavailable), Russian placeholder home page,
    htmx 2.0.11 served from `app/static/` (no CDN).
  - Docker Compose: `app` (built locally, `zulu-calibrator:${IMAGE_TAG}`), `caddy` (HTTPS for `DOMAIN`,
    HSTS, optional `ACME_EMAIL`), `backup` (daily `sqlite3 .backup`, keeps 14 copies).
  - CI: ruff lint + format check, pytest, lock consistency (`pip check`), compose smoke test over HTTPS.
  - `docs/DEPLOY.md` (Russian): VPS, DNS, Docker, `.env`, start, health check, backups and restore.
- No tables, no auth, no engine code yet.
- Next: PR-2 (auth by login), after PR-1 is merged.

## Work queue

1. PR-1 Skeleton: FastAPI app, Jinja2 + HTMX base layout, SQLite + Alembic, Docker Compose with Caddy
   (`DOMAIN` from `.env`), health check, CI running tests and lint, daily backup, `docs/DEPLOY.md`.
   — in review.
2. PR-2 Auth by login (no email field anywhere): admin/user roles, admin creates users with login +
   display name and a one-time generated password, forced password change, TOTP + backup codes,
   throttling, sessions, CSRF, secure headers.
3. PR-3 Engine core: units, balances and meter checks (algorithm «Входные данные»), GUID grouping and
   multi-input split, golden tests.
4. PR-4 Engine steps 1–2 (CTP scheme 2 test parameters, Kgv, Kcirc/Hcirc) with golden tests.
5. PR-5 Engine steps 3–5 (CTP inlet washer, Kso exception, building washers, washers in series).
6. PR-6 Projects and history: new CTP calculation, history list, resume, iterations, manual edits by Sys.
7. PR-7 Step pages (slides), state machine, «accept with deviation».
8. PR-8 Scheme registry page and statuses.
9. PR-9 AI review button via the backend: provider-agnostic client, GigaChat (primary) and OpenAI
   (secondary); per-provider `.env` settings (`GIGACHAT_API_KEY`, `GIGACHAT_MODEL`, `GIGACHAT_SCOPE`,
   `GIGACHAT_PROXY_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_PROXY_URL`, `AI_DEFAULT_PROVIDER`);
   each provider only through its own HTTP CONNECT proxy, never applied to other traffic; GigaChat OAuth
   via `ngw.devices.sberbank.ru:9443` and the Russian Ministry of Digital Development root CA in the image;
   admin switches the active provider in settings; monthly limit and cost counter per provider
   (RUB / USD); `docs/DEPLOY.md` section on the NetBird + tinyproxy route for GigaChat.
10. PR-10 Reset-to-base and the full scheme matrices (CTP 1–41, consumers 1–49) marked «first check».
11. Deferred: real paste formats (samples from Zulu).

## Decisions log

- Stack: FastAPI + Jinja2 + HTMX, SQLite (SQLAlchemy/Alembic, Postgres-ready), Docker Compose + Caddy.
- GUID stored as is (not personal data). Consumer names/addresses never stored.
- AI explains only; numbers come from the engine.
- Image is built locally on the server (`docker compose up -d --build`), no registry; tag from `IMAGE_TAG`.
- Dependencies: `pyproject.toml` + compiled `requirements.lock` / `requirements-dev.lock` with exact pins,
  plain pip (no uv). Regenerate with `scripts/lock.sh` (runs pip-tools in the production Python image).
- Daily SQLite backup via a compose service (`sqlite3 .backup`, 14 copies on the `backups` volume).
- Accounts by login, no email (152-FZ: server outside Russia, no personal data of users stored).
- AI providers: GigaChat (primary) and OpenAI (secondary), each through its own proxy only; per-provider
  monthly limit and cost counter (GigaChat RUB, OpenAI USD); admin switches the active provider.
