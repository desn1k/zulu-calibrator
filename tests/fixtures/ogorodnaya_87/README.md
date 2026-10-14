# Golden fixtures — ЦТП «Огородная, 87»

Real calibration session, ZuluThermo, CTP scheme N_schem = 2 (two-stage mixed DHW, independent heating).
Measurement: daily averages for 10.02.2026, outdoor temperature −12.8 °C, source supply temperature 88.7 °C.
Consumers are anonymized: `Name`, `Bld`, `Adres` are set to null; consumers are identified by `Sys` only.
`GUID` is kept (it is not personal data and is needed to group multi-input buildings).

Each file is the export of the old offline calculator (`zulu_ctp_calibration.html`, button «Собрать файл для разбора»)
after a verification run in Zulu. Model values live in `карточка_ЦТП` and in `дома[*]` result fields;
meter values in `дома[*]` blocks `*_TS`, `*_OT`, `*_GVS`, `*_SV`.

## CTP meter facts (entered manually, not in the files as a separate block)

| Block | Values |
|---|---|
| Inlet (network) | G1 98.4, G2 99.7 t/h; T1 89.2, T2 57.0 °C; P1 54.8, P2 48.4 m; Q 3.104 Gcal/h |
| Heating after CTP | G3 143.4, G4 136.5 t/h; T3 78.5, T4 60.3 °C; P3 70.9, P4 53.3 m; Q (G·ΔT) 2.610 |
| DHW at CTP | Gп 23.1, Gц 16.4 t/h; Tгв 62.8, Tц 53.5 °C; Q 0.537; Tхв 5 |

User decisions: DHW draw-off target = sum of building meters (variant «Б»), Kso/loads locked except the explicit
step-4 exception, building design graph 95/95/70 stays.

## Iterations

| File | What was entered in Zulu before this run |
|---|---|
| it0_initial | nothing (starting state, contains junk values) |
| it1_step1 | step 1: N_schem 2, first test parameters, Kgv of 4 DHW objects |
| it2_step1a | step 1-A: corrected test parameters (see table below) |
| it3_step2 | step 2: Kcirc / Hcirc of 5 DHW objects |
| it4_step3_graph_trial_rejected | building design graph changed (T1_r/T3_r/T2_r) — REJECTED by the user, must NOT be reproduced |
| it5_step3_rollback | graph reverted to 95/95/70 (identical results to it3) |
| it6_step4_kso | step 4: Kso exception |
| it7_step5_washers | step 5: building washers |

## Golden values the code must reproduce

Step 1.2 (scheme 2), free parameters T22_niz = 59, T12_verh = 57.5, draw-off Gр = 6.7 t/h (CTP meter):

| Field | Value |
|---|---|
| T11_i / T12_i / T21_i / T22_i / G1_i / G2_i | 89.2 / 61.1 / 60.3 / 78.5 / 92.8 / 143.4 |
| T11_i_niz / T12_i_niz / T21_i_niz / T22_i_niz / Q_i_niz | 60.9 / 57.2 / 5 / 59 / 0.362 |
| T11_i_verh / T12_i_verh / T21_i_verh / T22_i_verh / Q_i_verh | 89.2 / 57.5 / 55.1 / 62.8 / 0.178 |
| closure G1_i·(T1 − T12_i)/1000 vs Qсо | 2.608 vs 2.610 |

Step 1.3 Kgv from it0 (formula (G1−G2)(Tgv−Thv)/(1000·Qgv_sred)): 33553 → 0.36, 33559 → 0.31, 33561 → 0.25.
33567: G1_GVS = 0 → fallback by heat Q_GVS/Qgv_sred ≈ 0.07 (0.08 was entered).

Step 2 Kcirc from it2 (Kcirc = 100·G2_GVS / Ggv, Ggv = 1000·Qgv_sred·Kgv/(Tgv−Thv)), Hcirc = H_ras:

| Sys | Kcirc (formula) | Kcirc entered | Hcirc |
|---|---|---|---|
| 33551 | 612 | 617 | 19.4 |
| 33561 | 200 | 206 | 19.6 |
| 33569 | 564 | 560 | 18.5 |
| 33573 | 796 | 791 | 18.9 |
| 33575 | 520 | 528 | 18.0 |

Both sets converge (it3: Gcirc within ±3 %, Tcirc within ±1 °C). Tests use the formula column (tolerance 1 %).

Step 4 Kso from it5 (Kso_new = Kso · Q_meter / Q_sum): 33523 1.075, 33525 0.849, 33531 0.751, 33535 0.638,
33539 1.018, 33563 0.766, 36749 0.611, 36751 1.365.

Step 5 washers from it6 (change only if |Gm/Gf − 1| > 2 %; ΔHш,new = H_ras − (H_ras − ΔHш)(Gf/Gm)²;
d_new = d·√(Gf/Gm)·(ΔHш/ΔHш,new)^¼): 33523 17.5 → 16.7, 33539 27.3 → 24.0, 33525 21.1 → 21.7, 36749 37.4 → 36.9.

Step 5 «two washers in series» from it7 (d_eq = (d1⁻⁴ + d2⁻⁴)^(−¼)): 33525 → 17.5, 33531 → 20.0, 33535 → 21.5;
36751 has Nshb_pod = 1 with empty Dshb_pod → junk, clear.

Final state it7: inlet G +0.3 %, Q +1.1 %, T2 −1.7 %; building flows −1.3…+1.8 %; building heat −2.1…−4.0 %;
circulation ±2 %; T3so/T2so −2 °C (step 6 postponed).
