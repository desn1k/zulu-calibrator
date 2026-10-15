# HANDOFF

## 0. Current state

- PR-1 (skeleton), PR-2 (engine), PR-3 (local UI, no auth) merged. PR-2 got no review comments.
  Run locally: `scripts/run_local.ps1` / `scripts/run_local.sh` (`docs/LOCAL.md`), 127.0.0.1 only.
- PR-4 (CTP schemes 12, 3, 5, 6, elevators, real Zulu formats) is in review on branch
  `pr-4-schemes-12-3-5-real-formats`:
  - `docs/algorithm.md`: the 8 approved changes of 2026-10-15 + «Шероховатость по возрасту».
  - Golden sets `chernyshevskogo_8`, `beregovaya_1_15`, `verkhnyaya_24`, `pionerskaya_2_30_36`
    (`tests/fixtures/network_*` stay untracked — they belong to PR-5).
  - `app/engine/parsers/`: one interface `parse_upload` for the Zulu CTP card paste
    (`Field<TAB>value`, 2+ spaces, decimal comma) + consumer export (xlsx / csv, read in the browser
    with vendored SheetJS 0.20.3 mini, sha256 `0cb353f8…0939`) and the old JSON export. Private
    columns (Name, Bld, Adres, FIAS_Adress, FIAS_ID, UUTE_Name, any *adres* / *address* / *fias*)
    are dropped in the browser and again on the server. Card meter blocks `_TS/_OT/_GVS/_SV` → CTP
    fact.
  - Engine: `schemes.py` (matrices, initial statuses), `dhw.py` (DHW target, sequential / parallel /
    mixed-dependent test parameters, stage II tuning, Hgv2), `validity.py` (one building: CTP return
    sensor; flow channel by load factor), `targets.py` (meter / group meter split by model flow /
    remainder by Kso·Qo_r; Kso factors, unmetered k), `hydraulics.py` (washer ΔH, two H(G) points,
    house head forecast), `inputs.py`, `run_warnings.py` (inlet washer plug, washer changed between
    runs), `sql.py` (Zulu UPDATE batch / one by one, `Nshb = 0` fix).
  - Steps: step 1 per scheme (Kgv «по Tgv объекта» / «по расходу модели», an unmetered DHW object
    gets the CTP meter rest), step 2 (skipped without circulation; Gcirc check + Tcirc from two
    runs), step 4 (one Kso per building, unmetered k, cross-check, «сначала шаг 5»), step 5 (targets
    for every input, two H(G) points for a second round, series washers, return washer as the lever,
    elevators, forecast head below 4 m).
  - Tolerances ±4 % + temperature rule (`criteria.by_temp`); step order 5 before 4 per project.
  - Scheme registry table `scheme_status` (migration 0003) seeded as calibrated: CTP 2, 3, 5, 6, 12,
    consumers 2, 4, 26; the step page warns about uncalibrated schemes. The registry page and
    «подтвердить» are still to do (PR-9).
  - UI: SQL block with «по одной» and «Скопировать SQL», layer setting, Russian labels and units on
    the checks, status legend, DHW source on check 7, group meters entered by hand (until PR-5).
- Next: PR-5 — network after the CTP (export format to be confirmed by Andrew) + pressures of the
  second contour (section «Давления второго контура», task 3c of PROMPT_PR-5) + the roughness band
  check (bands go to `config.py` together with the check).

### Open questions for Andrew (PR-4)

Values marked `QUESTION` in `app/engine/config.py` are my choices where the method gives no number.

1. Kgv: formula 1.3 (Tgv of the object) is the default; «по расходу модели»
   (Kgv·(G1 − G2)ф/Ggv, plus the Tgv change entered in the same run) is a step 1 setting.
   Чернышевского and Верхняя golden values need «по модели», Огородная / Береговая / Пионерская need
   1.3 — no single automatic rule reproduces all five. Which default?
2. `KGV_DRAW_OFF_DIFF_PCT` 10 → 4 %: algorithm 1.3 says 10 %, the new tolerance caps flows at 4 %
   (Чернышевского changed all 13 objects, 28108 was +8.9 %). Kgv now has 3 decimals.
3. Stage II (scheme 12): Q_needed = Gп(target)·(Tгв − T21_verh)/1000 reproduces 0.31 exactly; from
   it6 it gives 0.377 vs README 0.385 (the session used the model flow 8.675).
4. `STEP1_DHW_TEMP_C` 1 °C (T DHW at the CTP outlet), `DHW_HOUSES_AGREE_PCT` 10 % (building sum
   «agrees» with the CTP balance), `CHANNEL_FACTOR_MAX_DIFF_PCT` 25 %,
   `STEP2_TCIRC_ONLY_COOLING_SHARE` 0.5 (Gcirc matches and the model loop cooling ≥ ½ of the target
   → Tcirc only, as on Береговая; otherwise step 2 as on Огородная).
5. Источник потерь уточнить: Qut_pod + Qut_obr + Qut_potr = 0.013 on Верхняя (as README) but 0.029
   on Чернышевского vs README 0.02 (the golden test uses 0.02 as an input). Qut_potr alone is 0.019.
6. Пионерская a8: the first Kso 0.925 (its inputs had Kso 1.3 / 1.0) is not reproduced; the
   fine-tune 0.976 is, with the README target 0.42 (the card loss 0.0106 would give 0.9675).
7. Regul_T = 1 is not recommended for scheme 12 (the session kept 0 and tuned stage II by Q_i_verh).
8. Step 5 with CTP pumps (independent heating) waits for the inlet within ±4 % (was ±2 %; Береговая
   sized the washer at −2.4 %). The step 3 criterion stays ±2 %.
9. Step 5 criterion «Gsum_pod2 ЦТП ±1 %» (algorithm) fails on every final state of the new sets
   (+1.6 … −2.1 %) — keep, or ±2 / ±4 %?
10. A multi-input building with one meter: the flow target is split by model flow (task); the GUID
    section of the algorithm says Qo_r (user shares still override). One Kso per building.
11. Hsec_niz 0.4 (Чернышевского run 1): no rule found, not recommended.
12. Known Regul_G / Regul_T labels: «Без регулятора», «Регулятор температуры». Any other label stops
    the import with a message — send new labels to add their codes.

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
     shares, «Копировать» on each step's table. — merged.
4. PR-4 CTP schemes 12, 3, 5, 6 and elevators (consumer scheme 2), real Zulu formats (CTP card
   paste, consumer xlsx / csv — replaces the old «PR-8 parser»), method change 2026-10-15, SQL
   output, initial scheme statuses, UI fixes. — in review.
5. PR-5 Network after the CTP (after Andrew confirms the export format): pipes, nodes, valves with
   geometry; tree from the CTP to every input; checks (roughness / overgrowth outside the band,
   closed valves, diameter jumps, inputs not connected); per-path head losses into the washer head
   forecast; meter nodes of multi-input buildings from the export (replaces the hand entry);
   pressures of the second contour (losses CTP → each meter, CTP washer by the run result, return
   washers after each pressure change).
6. PR-6 Auth by login (no email field anywhere): admin/user roles, admin creates users with
   login + display name and a one-time generated password, forced password change, TOTP + backup
   codes, throttling, sessions, CSRF, secure headers.
7. PR-7 Deploy: first release candidate on the VPS per `docs/DEPLOY.md` (only after PR-6).
8. PR-8 AI review button via the backend: provider-agnostic client, GigaChat (primary) and OpenAI
   (secondary); per-provider `.env` settings (`GIGACHAT_API_KEY`, `GIGACHAT_MODEL`, `GIGACHAT_SCOPE`,
   `GIGACHAT_PROXY_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_PROXY_URL`, `AI_DEFAULT_PROVIDER`);
   each provider only through its own HTTP CONNECT proxy, never applied to other traffic; GigaChat OAuth
   via `ngw.devices.sberbank.ru:9443` and the Russian Ministry of Digital Development root CA in the
   image; admin switches the active provider; monthly limit and cost counter per provider (RUB / USD);
   `docs/DEPLOY.md` section on the NetBird + tinyproxy route for GigaChat.
9. PR-9 Reset-to-base, step 0 checklist, scheme registry page with «подтвердить», the full scheme
   matrices (CTP 1–41, consumers 1–49) marked «first check».

### Backlog

- Kgv target «верим ЦТП» (check 7 answer «ЦТП»): not specified in algorithm.md yet; engine raises
  `NotImplementedError` for `draw_off_source="ctp"`. Since 2026-10-15 the DHW target picks the
  building sum automatically when the CTP DHW meter contradicts the CTP balance.
- Step 6 (Kpoprav) and the second-day check.

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
- 2026-10-15 priority change: CTP schemes 12, 3, 5, 6 and the real Zulu formats before auth (PR-4),
  then the network export (PR-5). Auth must still be merged before any public deployment.
- Method change 2026-10-15 applied to `docs/algorithm.md` (8 changes + «Шероховатость по возрасту»).
- Zulu input: the CTP card is pasted as text, consumers come as an xlsx / csv export; the browser
  reads xlsx with SheetJS (vendored, pinned) so private columns never leave the browser. Real exports
  name the model heat `Qsum` (the old export `Q_sum`); the engine reads both.
- Tolerances: ±4 % on flows, heat, pressure drops, house heat, each input of a multi-input building;
  restored CTP block ±7 % (estimate). Temperatures: ±4 % of the value when the model supply is within
  1 °C of the meter, otherwise ±4 % on ΔT with the note «первый контур / прибор». Step 1
  «T3so_t / T2so_t ±0,7 °C» kept (independent heating only).
- Kso: one Kso per building (a multi-input building with one meter); unmetered buildings one factor
  k = (Q_heating − Σ Q_metered − loss) / Σ Q_model, loss = Qut_pod + Qut_obr + Qut_potr of the card.
- Washers: S = (H_ras − ΣΔHшайб)/G², ΔH = H_new − S·G_цель², all washers in series count, the return
  washer is the lever when present; second round: ΔP after the CTP from two runs, the loss to each
  house ∝ G² («Давления второго контура» п. 3). Elevator: H_ras = ΔHшайбы + ΔHсопла.
- SQL: batch with «;» after every line except the last (default), «по одной» without «;»; the layer is
  a project setting (default `Актуальный_расчетный_2025`).
- Fixture CSV line endings are normalised to LF by `.gitattributes` (content unchanged); ruff does not
  lint `tests/fixtures`.
