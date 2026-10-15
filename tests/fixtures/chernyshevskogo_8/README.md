# Golden fixtures — ЦТП «Чернышевского, 8»

Real calibration session, ZuluThermo, CTP scheme N_schem = 12 (two-stage sequential DHW, direct heating).
Measurement: daily averages for 10.02.2026, outdoor −12.8 °C, source supply 88.7 °C (same source as Огородная, 87).
Zulu layer: `[Актуальный_расчетный_2025]`.

Each iteration folder holds the two real input formats the app must parse:

- `ctp_card.tsv` — the CTP card copied from Zulu, one `Field<TAB>value` line per field. Contains the meter blocks
  `*_TS` (inlet), `*_OT` (heating), `*_GVS` (DHW at CTP). `Adres` removed.
- `consumers.csv` — the consumer query export (originally xlsx, header row). Removed columns: `FIAS_Adress`,
  `FIAS_ID`, `Adres`, `Name`, `UUTE_Name`. Consumers are identified by `Sys`; `GUID` kept for multi-input grouping.
  `Regul_G` / `Regul_T` are text labels («Без регулятора», «Регулятор температуры»), not numbers.

## CTP meter facts (in every card)

| Block | Values |
|---|---|
| Inlet `_TS` | G1 129.5, G2 132.4 t/h; T 89.2 / 53.0 °C; P 68.8 / 55.9 m; Q 4.571 Gcal/h |
| Heating `_OT` | G 128.5 / 128.2 t/h; T 89.2 / 58.2 °C; P 66.6 / 56.3 m; Q 4.012 |
| DHW `_GVS` | G1 4.7 t/h, T1 65.8, Q 0.285; no G2/T2 — REJECTED as target (does not fit the CTP balance) |

User decisions: DHW draw-off target = sum of building meters G1 − G2 = 8.5 t/h (variant «Б»); no circulation from
the CTP → Kcirc = 0, step 2 skipped; Kso exception allowed; building graph 95/95/70 untouched; tolerance ±4 % on
all parameters (temperatures: by ΔT when model supply differs from the meter by more than 1 °C).

## Iterations (what was entered in Zulu BEFORE this run)

| Folder | Entered |
|---|---|
| it0_initial | nothing |
| it1_step1_inlet_washer_plug | stage I: T11_i_niz 58.2, T12_i_niz 53, T21_i_niz 5, T22_i_niz 56, Q_i_niz 0.673, Hsec_niz 0.4; inlet washer cleared → Nshb_pod_u 0 with empty D = PLUG (dHshb_pod 18.7, Gsum_pod 0.35). Negative example. |
| it2_step1a_inlet_washer_200 | Dshb_pod_u 200, Nshb_pod_u 1 → inlet 166.9 t/h |
| it3_step1_3_kgv | Kgv of 13 DHW objects = Kgv·(G1−G2)_meter / Ggv_model → draw-off 8.65 t/h |
| it4_step5_washers_round1 | washers: Dshb_pod 27992 13.2, 28018 8.2, 28026 18.1, 28040 15.6; Dshb_so_pod_u + Nshb_so_pod_u = 1 on 29 objects → inlet 144.6 |
| it5_step5_washers_round2_stage2_on | washers round 2 (head forecast from two H(G) points) + stage II: T11_i_verh 89.2, T12_i_verh 60, T21_i_verh 56, T22_i_verh 65.8, Q_i_verh 0.083 → inlet 129.49 |
| it6_step4_kso | Kso (5 metered buildings by meter, 8 unmetered × 1.0997); Q_i_verh 0.31 |
| it7_step4_kso_finetune | Kso once more by Q_meter/Q_model; Q_i_verh 0.385 → FINAL, all within 4 % |

## Golden values

Step 1.3 Kgv (from it2): 28108 0.261, 28116 0.208, 28124 0.205, 28134 0.089, 28154 0.276, 28166 0.448,
28184 0.103, 28190 0.181, 28196 0.434, 28198 0.143, 28210 0.272, 28218 0.335, 28250 0.260.

Unmetered heating target (from it3): (128.5 − 28.8) = 99.7 t/h split by Kso·Qo_r → 30.1 t/h per Gcal/h
(metered buildings 23.6–29.5). Building 28030 meter (12.5 t/h) = whole 3-input GUID group 28030/40488/40490.

Step 5 round 2 (from it4), Dshb_so_pod_u: 27966/40462 12.7, 27976/40466 13.1, 27998/40470 12.1, 28014/40478 12.4,
28030/40452/40454 13.5, 28034/40482 9.5, 28038/40427 12.0, 28060 12.6, 28072 13.3, 28226/40493/40496 12.9,
40435/40437/40441 11.9, 40439 11.8, 40445/40476 12.5, 40456 13.4, 40488/40490 13.2;
Dshb_pod: 27992 11.5, 28018 7.1, 28026 15.4, 28040 13.9. Tolerance 0.3 mm (head forecast is approximate).

Step 4 Kso (from it5): 27992 0.858, 28018 0.658, 28026 0.844, 28040 0.835, 28030 group 1.071;
unmetered factor k = (4.012 − 0.952 − 0.02) / 2.7645 = 1.0997.
Fine-tune (from it6): 27992 0.882, 28018 0.671, 28026 0.859, 28040 0.851, group 1.102, k = 1.0194.

Stage II rule: Zulu passes ≈ 0.25 × the test flow through stage II; Q_i_verh_new = Q_i_verh · Q_needed / Q_verh
(0.083 → 0.31 → 0.385).

Final state it7: inlet G +0.8 %, G·ΔT +0.3 %; heating Q −1.0 %; metered G +1.0…+2.3 %, Q −0.4…−0.7 %;
ΔT per metered building −3.4…+0.3 %; draw-off 8.45 vs 8.5; T DHW 65.5 vs 65.8; heating return at CTP 54.95 vs 58.2
(explained by supply 87.05 vs 89.2 — first contour / meter, outside the second contour).
