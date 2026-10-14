# HANDOFF

## 0. Current state

- PR-1 (skeleton) and PR-2 (engine, `app/engine/`) merged.
- PR-3 (local UI, no auth) is in review on branch `pr-3-local-ui`:
  - DB (migration `0002`): `project` (CTP + measurement date, CTP fact, settings), `iteration`
    (each imported export, attached to the open step), `step_state`, `consumer_edit` (by Sys).
  - `app/services/projects.py` — state machine fact → checks → 1 … 5 → summary; recommendations and
    criteria always from the latest export with manual edits applied; «принять с отклонением»
    needs a comment.
  - `app/routes/projects.py` + templates: home, history / resume, import (`static/import.js` strips
    Name / Bld / Adres in the browser; the server strips again), CTP fact form (м вод. ст. or
    кгс/см² ×10), meter checks 1–11 with per-Sys edits (block, value, «не доверять») and
    multi-input shares, one page per step with «Копировать», summary, read-only iterations.
  - Engine: `edits.py` (manual edits), `house_meters` (split meters of multi-input houses with
    edited shares) used by steps 4–5 and criteria; «не доверять» meters are left out of the balance,
    the recommendations and the criteria.
  - Run locally: `scripts/run_local.ps1` / `scripts/run_local.sh` (`docs/LOCAL.md`), 127.0.0.1 only.
- PR-2 CodeRabbit review had not arrived when PR-2 was merged: address it at the start of the next PR
  (fix with a test, or reply with a reason on the PR-2 threads).
- Next: PR-4 (auth by login), after PR-3 is merged.

## Rule before any public deployment

**Auth must be merged before any public deployment.** Until then the app runs only on localhost
(`uvicorn`), never on a public server or port.

## Work queue

1. PR-1 Skeleton — merged.
2. PR-2 Engine: meter checks and balances, GUID grouping and multi-input split, steps 1–5 for CTP
   scheme 2 and consumer schemes 4 and 26, washers-in-series rule, golden tests. — merged.
3. PR-3 UI for local use, NO auth yet (localhost only):
   - home page («Новый расчёт ЦТП», «История ЦТП»); project = CTP + measurement date;
   - intake page importing the old calculator JSON export (fixture format; Name/Bld/Adres stripped
     on import), manual CTP fact form (pressures in м вод. ст., кгс/см² ×10 as an option);
   - one page per step: «поле → сейчас → ввести» table, «не трогать» list, criteria pass/fail,
     re-import of fresh data per iteration, «принять с отклонением» with a mandatory comment;
   - history and resume. Run with `uvicorn` on localhost.
   - manual consumer fact edits by Sys (block, value, «не доверять»), GUID groups with editable
     shares, «Копировать» on each step's table. — in review.
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

### Backlog

- Kgv target «верим ЦТП» (check 7 answer «ЦТП»): not specified in algorithm.md yet; engine raises
  `NotImplementedError` for `draw_off_source="ctp"`.

## Decisions log

- Local UI: a fresh export attaches to the open step and is checked against its criteria;
  recommendations always come from the latest export (with manual edits). No CSRF/auth until PR-4 —
  localhost only.
- Numbers are shown and copied with a decimal comma («Копировать»: Sys / field / value, tab-separated).

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
- Approved method change (algorithm.md 1.2): the inlet T2 is balanced first,
  T2_bal = T1 − 1000·(Qсо + Q_i_niz + Q_i_verh)/G, T12_niz = T2_bal; the page shows T2_bal and the meter T2.
- Tolerances given in words only in algorithm.md (checks 1/2 ±2 %, check 4 < 25 %, check 11 within 2 m,
  «T11_niz не ≈ T1» > 1 °C) approved as in `app/engine/config.py` (marked APPROVED).
- Step 1 hint when the draw-off source is «дома» and Σ house draw-off < CTP draw-off: «T2 ввода
  физически не опустится до факта — допустимо принять с отклонением».
- Step 4 default is variant А (no changes, heat deficit reported); Kso only with the «исключение Kso» flag.
- Units: all pressures (meters and Zulu fields) are м вод. ст.; no conversion. The CTP fact form has a
  unit setting (м вод. ст. default, кгс/см² ×10 as an option).
