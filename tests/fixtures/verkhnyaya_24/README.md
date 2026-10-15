# Golden fixtures — ЦТП «Верхняя, 24»

CTP scheme N_schem = 5 (direct heating, two-stage mixed DHW). Consumers: heating scheme 2 (elevator), DHW scheme 26,
dead-end DHW (no circulation). 6 buildings, 15 heating inputs, 6 DHW objects. 10.02.2026, −12.8 °C.
Same formats as the other sets. Note: in `it3_step4_kso_metered` the CTP card is a duplicate of it2 (the user pasted the
old card); consumers.csv is the real it3 export.

## Meter facts and validity

| Block | Values | Verdict |
|---|---|---|
| Inlet `_TS` | G1 24.3, **G2 68**, T 89.1 / 54.2, P 60.5 / 42.6, Q −1.299 | G2 valid; G1 and Q rejected |
| CTP heating `_OT` | G 20.9 / 21.3, T 89.2 / 56.4, P 59 / 47.1, Q 0.666 | flows/heat rejected (metered houses alone take 19.0 t/h, 0.60) |
| CTP DHW `_GVS` | G1 4.5, T 62.7, P 61.7, Q 0.259 | valid (= Σ G1 of 6 buildings) |
| Metered heating 28403 / 28409 / 28413 | 4.8 / 12.7 / 1.5 t/h; 0.152 / 0.389 / 0.058 | valid |

Proof for G2: split 68 t/h by the mixed-scheme formulas (T12_verh chosen 40) → stage II 3.4 t/h, heating 64.6 t/h,
2.12 Gcal/h; unmetered buildings need ×1.27 of design load at −12.8 vs ×1.22 for metered ones → consistent.
Rule: when a CTP flowmeter cannot cover the metered buildings alone, reject it; accept the channel that gives the
unmetered buildings the same load factor as the metered ones.

## Iterations (entered BEFORE each run)

| Folder | Entered |
|---|---|
| it0_initial | nothing |
| it1_step1_dhw_stages_kgv_hgv2 | Tgv 62.7; stage I 55.6/54.2/5/26, Q 0.095; stage II 89.2/40/26/62.7, Q 0.165; Hgv2_obr 108.4, Hgv2_ras 2; Kgv 28435 0.658, 28441 0.330, 28443 0.205, 28474 0.373, 28478 0.293, 28484 0.465 |
| it2_step5_washers_nozzles_r1 | Dshb_pod 28403 15.5, 28409 22.8, 28413 8.3; Dshb_so_pod_u 28445 16.6, 40519 14.3, 40522 14.6, 40524 14.2, 28455 21.7; washers removed (D 0, N 0) + Dsop_u 12.9 on 40534/40536/40538, 11.4 on 28463/40510/40514/40516 |
| it3_step4_kso_metered | Kso 28403 0.877, 28409 0.894, 28413 0.770 |
| it4_roughness_0_5_kso_finetune | pipe roughness CTP→buildings 2 → 0.5 mm; Kso 28403 0.924, 28409 0.940, 28413 0.839 |
| it5_step4_kso_unmetered_nozzle_final | Kso …75 1.057, …79 0.720, …65 1.023; Dsop_u 11.7 on 28463/40510/40514/40516 → FINAL |

## Golden values

Elevator model in Zulu: H_ras = ΔH_washer + ΔH_nozzle exactly; ΔH_nozzle = G²·(9.6/dс)⁴ (= dHsop).
Nozzle when washer is removed: dс = 9.6·(G²/H)^¼.
Head per building vs total heating flow from two runs: H_i = c − k·G_tot².
Unmetered heating target = 68 − 3.7 (stage II) − 19.0 = 45.3 t/h split by Kso·Qo_r (28.3 t/h per Gcal/h).
Unmetered Kso factor = (2.373 − 0.264 − 0.588 − 0.013) / 1.2086 = 1.248 (metered buildings needed ×1.25).
Roughness 2 mm vs 0.5 mm: λ ∝ k^0.25 → losses ×1.41.

Final it5: inlet G 66.6 vs 68 (−2.1 %), G·ΔT 2.342 vs 2.373 (−1.3 %), ΔT +0.7 %; heating 63.0 vs 64.3 (−2.1 %);
metered G −1.6…−2.3 %, Q −1.7…−2.8 %; all 15 inputs −0.2…−3.8 %; DHW exact. Open: indoor 13.5–16.8 °C in model
(step 6), CTP flowmeters G1_TS and `_OT` to be checked, T1 −1.2 °C (first contour).
