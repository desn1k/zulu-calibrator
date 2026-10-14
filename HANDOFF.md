# HANDOFF

## 0. Current state

- Repository just created. Contains `AGENTS.md`, `docs/algorithm.md`, golden fixtures
  `tests/fixtures/ogorodnaya_87/`. No application code yet.
- Next: PR-1 (project skeleton), waiting for Andrew's «go» on the plan.

## Work queue

1. PR-1 Skeleton: FastAPI app, Jinja2 + HTMX base layout, SQLite + Alembic, Docker Compose with Caddy
   (`DOMAIN` from `.env`), health check, CI running tests and lint.
2. PR-2 Auth: admin/user roles, admin creates users with one-time password, forced password change,
   TOTP, throttling, sessions, CSRF, secure headers.
3. PR-3 Engine core: units, balances and meter checks (algorithm «Входные данные»), GUID grouping and
   multi-input split, golden tests.
4. PR-4 Engine steps 1–2 (CTP scheme 2 test parameters, Kgv, Kcirc/Hcirc) with golden tests.
5. PR-5 Engine steps 3–5 (CTP inlet washer, Kso exception, building washers, washers in series).
6. PR-6 Projects and history: new CTP calculation, history list, resume, iterations, manual edits by Sys.
7. PR-7 Step pages (slides), state machine, «accept with deviation».
8. PR-8 Scheme registry page and statuses.
9. PR-9 AI review button via backend proxy, settings (model, monthly limit), cost counter.
10. PR-10 Reset-to-base and the full scheme matrices (CTP 1–41, consumers 1–49) marked «first check».
11. Deferred: real paste formats (samples from Zulu).

## Decisions log

- Stack: FastAPI + Jinja2 + HTMX, SQLite (SQLAlchemy/Alembic, Postgres-ready), Docker Compose + Caddy.
- GUID stored as is (not personal data). Consumer names/addresses never stored.
- AI explains only; numbers come from the engine.
