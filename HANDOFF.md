# HANDOFF

## 0. Current state

- PR-1 (skeleton) merged: FastAPI app, SQLite + Alembic, Docker Compose (app, Caddy, backup), CI,
  `docs/DEPLOY.md`.
- PR-2 (engine) is in review on branch `pr-2-engine`. `app/engine/` (pure functions):
  - `legacy.py` — import of the old calculator export (fixture format); drops `Name`, `Bld`, `Adres`
    and any address field; pre-fills the CTP inlet/heating fact from the stored form inputs.
  - `meters.py` — meter block per scheme (26 → `_GVS`; heating → `_OT`, else `_TS` «взят ввод»),
    meter checks 1–11.
  - `grouping.py` — GUID + system type groups, multi-input split by load, duplicate-fact flag.
  - `step1.py` … `step5.py` — CTP scheme 2 test parameters and Kgv (with the approved «по теплу»
    fallback), Kcirc / Hcirc / Tcirc, CTP inlet washer, Kso by exception (default variant А),
    building washers, washers in series, junk washer fields.
  - `criteria.py` — criteria of steps 1–5 on a fresh export; «identical exports» trap.
  - `config.py` — all tolerances; values marked ASSUMPTION need Andrew's confirmation.
- All README golden values are tests (`tests/engine/`).
- Next: PR-3 (local UI), after PR-2 is merged.

## Rule before any public deployment

**Auth must be merged before any public deployment.** Until then the app runs only on localhost
(`uvicorn`), never on a public server or port.

## Work queue

1. PR-1 Skeleton — merged.
2. PR-2 Engine: meter checks and balances, GUID grouping and multi-input split, steps 1–5 for CTP
   scheme 2 and consumer schemes 4 and 26, washers-in-series rule, golden tests. — in review.
3. PR-3 UI for local use, NO auth yet (localhost only):
   - home page («Новый расчёт ЦТП», «История ЦТП»); project = CTP + measurement date;
   - intake page importing the old calculator JSON export (fixture format; Name/Bld/Adres stripped
     on import), manual CTP fact form (pressures in м вод. ст., кгс/см² ×10 as an option);
   - one page per step: «поле → сейчас → ввести» table, «не трогать» list, criteria pass/fail,
     re-import of fresh data per iteration, «принять с отклонением» with a mandatory comment;
   - history and resume. Run with `uvicorn` on localhost.
4. PR-4 Auth by login (no email field anywhere): admin/user roles, admin creates users with
   login + display name and a one-time generated password, forced password change, TOTP + backup
   codes, throttling, sessions, CSRF, secure headers.
5. PR-5 Deploy: first release candidate on the VPS per `docs/DEPLOY.md` (only after PR-4).
6. PR-6 AI review button via the backend: provider-agnostic client, GigaChat (primary) and OpenAI
   (secondary); per-provider `.env` settings (`GIGACHAT_API_KEY`, `GIGACHAT_MODEL`, `GIGACHAT_SCOPE`,
   `GIGACHAT_PROXY_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_PROXY_URL`, `AI_DEFAULT_PROVIDER`);
   each provider only through its own HTTP CONNECT proxy, never applied to other traffic; GigaChat OAuth
   via `ngw.devices.sberbank.ru:9443` and the Russian Ministry of Digital Development root CA in the
   image; admin switches the active provider; monthly limit and cost counter per provider (RUB / USD);
   `docs/DEPLOY.md` section on the NetBird + tinyproxy route for GigaChat.
7. PR-7 Reset-to-base, step 0 checklist, scheme registry page and statuses, the full scheme matrices
   (CTP 1–41, consumers 1–49) marked «first check».
8. PR-8 Real Zulu paste parser (CTP card and consumer query) behind the parser interface, once
   Andrew provides samples.

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
- 2026-10-14 priority change: working local calculator first (engine, then local UI), then auth, deploy,
  AI, other schemes, Zulu paste parser. Auth must be merged before any public deployment.
- Approved method change (algorithm.md 1.3): Kgv by heat when the draw-off is not measured
  (G1_GVS − G2_GVS ≤ 0.05 t/h or missing): Kgv = Q_GVS / Qgv_sred, «по теплу (расход не измерен)».
- Step 4 default is variant А (no changes, heat deficit reported); Kso only with the «исключение Kso» flag.
- Units: all pressures (meters and Zulu fields) are м вод. ст.; no conversion. The CTP fact form has a
  unit setting (м вод. ст. default, кгс/см² ×10 as an option).
