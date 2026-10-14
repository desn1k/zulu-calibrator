# AGENTS.md — standing rules for zulu-calibrator

Read this file and `HANDOFF.md` («0. Current state») at the start of every session.

## What this project is

A password-protected web app that guides an engineer step by step through calibrating a ZuluThermo
(Zulu GIS) model of a central heating substation (CTP / ЦТП) and the buildings behind it against real
heat-meter data. The method is fixed in `docs/algorithm.md`. The app computes the values to enter in
Zulu, checks convergence after each verification run, and keeps history.

## Source of truth

1. `docs/algorithm.md` is the only source of the calibration method (steps, formulas, criteria, traps).
   Code must not contradict it.
2. If you believe the method or a formula is wrong, STOP and ask. Never change the method on your own.
   Proposed changes to `docs/algorithm.md` go in their own PR, approved by Andrew.
3. `tests/fixtures/ogorodnaya_87/` holds anonymized real iterations and the golden values
   (see its README). They are the acceptance tests of the calculation engine.

## Workflow

1. One task = one branch = one PR. Only one PR open at a time. No parallel branches.
2. Show a short plan first and wait for Andrew's «go».
3. Every fix starts with a failing test. Every new formula gets a test against the golden fixtures.
4. Andrew merges. Never push to `main`, never force-push, never rewrite published history.
5. Do not mention any AI model or assistant in commits, PR titles, PR bodies or code comments.
6. Keep PRs small and reviewable; describe what changed and how it was tested in plain words.
7. Update `HANDOFF.md` («0. Current state» and the work queue) in every PR that changes state.
8. Releases only with an explicit `IMAGE_TAG` (e.g. `v0.1.0-rc1`), never `latest`.
   Release candidates are launched by Andrew.
9. After every push to a PR branch, and whenever Andrew says «review», read all PR review comments
   (`gh pr view --comments` and `gh api .../pulls/{n}/comments`), address each one in the same PR
   (fix with a test, or reply with a reason if you disagree), reply to each comment on GitHub, push,
   and summarize what was done. Never resolve or dismiss a review on your own — Andrew decides.

## Architecture

- Python 3.12, FastAPI, Jinja2 templates + HTMX (no SPA framework). Keep it simple.
- SQLite via SQLAlchemy 2 + Alembic migrations, WAL mode. All DB access through SQLAlchemy so that
  switching to PostgreSQL is a connection-string change.
- `app/engine/` — the calculation engine: pure functions only (no I/O, no DB, no HTTP). Each function
  names the section of `docs/algorithm.md` it implements. Tolerances and step criteria live in one
  config module, not scattered in code.
- Steps are a state machine: intake → step 0 → reset-to-base → 1 → 2 → 3 → 4 → 5 → 6 → summary.
  Moving forward requires the step criteria to pass, or an explicit «accept with deviation» with a
  mandatory comment. Each step is its own page.
- Scheme registry: every CTP scheme (1–41) and consumer scheme (1–49) has a status
  (not calibrated / in check / calibrated). Initial state: CTP scheme 2, consumer schemes 4 and 26 calibrated.
  The UI warns when a project uses a scheme that is not calibrated. «Calibrated» is set only by a user
  pressing «confirm» on a finished project.
- AI assistant is called only from the backend. It explains and reviews a step.
  It NEVER produces the numbers to enter in Zulu and its output is never written into input fields.
  Payload = compact step summary (no raw exports).
  - Provider-agnostic client with two providers: GigaChat (primary) and OpenAI (secondary).
    `AI_DEFAULT_PROVIDER` (`gigachat` | `openai`) sets the initial one; admin switches the active
    provider in app settings.
  - Per-provider settings in `.env`: `GIGACHAT_API_KEY`, `GIGACHAT_MODEL`, `GIGACHAT_SCOPE`,
    `GIGACHAT_PROXY_URL`; `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_PROXY_URL` (optional).
  - Each provider uses ONLY its own proxy (HTTP CONNECT), set on that provider's HTTP client only and
    never on other app traffic (no global `HTTP(S)_PROXY`).
  - GigaChat: OAuth token flow via `ngw.devices.sberbank.ru:9443`; the Russian Ministry of Digital
    Development root CA is added to the image trust store. Its proxy is the server in Russia reached over
    NetBird (tinyproxy with a domain allowlist).
  - Monthly spend limit and cost counter per provider: GigaChat in RUB, OpenAI in USD.
- Deployment: Docker Compose (app + Caddy + daily backup). The image is built locally (`build: .`,
  tag `zulu-calibrator:${IMAGE_TAG}`), no image registry. Caddy gets HTTPS automatically from `DOMAIN`
  in `.env`. On a clean Ubuntu 24.04 VPS: `git clone`, fill `.env`, `docker compose up -d --build`
  (step by step in `docs/DEPLOY.md`).

## Privacy

- Consumer `Name`, `Bld`, `Adres` and any other address fields are dropped in the browser while parsing
  a paste, before anything is sent to the server. Consumers are identified by `Sys` only.
  `GUID` is kept as is (used to group multi-input buildings).
- No addresses in the DB, logs, AI payloads, exports or error messages. A dedicated test enforces this.
- The CTP name is stored (needed for history); the CTP address is not.

## Security

- HTTPS only (HSTS), secure headers (CSP, X-Frame-Options, Referrer-Policy).
- Passwords: Argon2id, min 12 chars. TOTP second factor with backup codes, mandatory after first login.
- Login throttling (5 attempts / 15 min per IP and per account, growing delay), generic error messages.
- Server-side sessions, cookie HttpOnly + Secure + SameSite=Strict, rotate on login, 12 h idle timeout,
  CSRF token on every state-changing request.
- Accounts are identified by a login (username), NOT an email. There is no email field anywhere
  (152-FZ: the app server is outside Russia, so no personal data of users is stored).
- Roles: admin and user. Only admin creates users (login + display name), gets a one-time generated
  password to hand over, can reset passwords and disable accounts. User must change password on first login.
- Secrets only in `.env` (never committed); `.env.example` documents every variable.
- Pinned dependency versions. Daily SQLite backup in the compose setup.

## Language

- UI in Russian. Code, identifiers, comments, commit messages and PRs in English.
- Zulu field names are used verbatim (e.g. `T12_i_niz`, `Dshb_so_pod_u`).

## Deferred

- Exact paste formats of the Zulu CTP card and the consumer query: Andrew will provide real samples
  copied from Zulu. Until then the parser works by field name and is tested on data rebuilt from the fixtures.
  Keep the parser isolated behind one interface so the real format can be plugged in later.
