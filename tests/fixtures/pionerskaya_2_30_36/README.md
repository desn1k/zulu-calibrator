# Golden fixtures — ЦТП «2-я Пионерская, 30/36»

CTP scheme N_schem = 6 (direct heating, parallel DHW, one-stage HX). Consumers: heating scheme 4 (14 inputs of
3 multi-input buildings), DHW scheme 26 (3 objects, circulation only at 33652). 10.02.2026, −12.8 °C.
Same formats as the other sets. CTP cards were preserved only for it4–it6 (meter blocks are identical in every run);
it0–it3 have consumers.csv only. The network export with meter nodes is in `../network_pionerskaya_2_30_36/`.

## Meter facts

| Block | Values | Verdict |
|---|---|---|
| Inlet `_TS` | G 58.8 / 57.8, T 87.9 / 58.1, P 64.1 / 49.6 (ΔP 14.5), Q 1.807 | valid |
| CTP heating `_OT` | G 51.6 / 51.7, T 87.9 / 58, P 64.1 / 50.5 (ΔP 13.6), Q 1.54 | valid |
| CTP DHW `_GVS` | G1 5.5, T 60.2, P1 47.6, Q 0.308 | Q overstated: supply-only meter counts circulation water as heated from 5 °C; true DHW heat ≈ 0.20 = draw-off + loop cooling |
| Meter node 84083 → b8 (33640, 40369, 40377, 40379, 40381, 40383) | G 19.3, T 86.1 / 55.5, P 52 / 39 (ΔP 13.0), Q 0.592 | valid (P2 given by the user, not in the export) |
| Meter node 84089 → b2 (33638, 40391, 40395, 40398) | G 18.6 / 18.5, T 86.7 / 59, P 55.2 / 44 (ΔP 11.2), Q 0.521 | valid |
| a8 (33636, 40387), no meter | remainder 51.6 − 19.3 − 18.6 = 13.7 t/h, ≈ 0.42 | remainder rule |
| DHW buildings 33648 / 33650 / 33652 | draw-off 0.9 / 1.1 / 1.2 t/h; circulation 33652 2.3 t/h, T 47.3 | valid |

Absolute pressures of different meters are not consistent (return head at b2 = 71.09 + 44 = 115.1 m is below the
CTP return head 67.02 + 50.5 = 117.5 m although water flows b2 → CTP). Only each meter's own ΔP is used.

## Iterations (entered BEFORE each run)

| Folder | Entered |
|---|---|
| it0_after_step1_dhw | DHW HX test parameters 87.9 / 45→55 / 22.7 / 60.2, Q_i_niz 0.308; Hgv2_obr 114.8, Hgv2_ras 5 (state at the start of the fixture) |
| it1_step4_kso_kgv_circulation | Kso a8 0.925, b2 0.784, b8 0.749; Kgv 33648 0.294, 33650 0.461, 33652 0.278; 33652 Kcirc 192, Hcirc 5, Tcirc 36, Nshb_gvs_u 0, Nshb_circ_u 0 (N = 1 with empty D → Zulu error «неверное значение поля») |
| it2_step5_supply_washers_regul_test | Dshb_so_pod_u + N 1: a8 18.9, b8 11.7 (40379 11.4); b2 Regul_T «Без регулятора» (test, no effect on flow); Tcirc 49 |
| it3_return_washer_b2_kso_t12niz | b2 return washer Dshb_so_obr_u 10 → 11.3 (it ate 14.2 of 14.5 m); Regul_T restored; Kso a8 0.976, b8 0.782; T12_i_niz 55 |
| it4_pressure_overgrowth_b2_branch | pipes 33639, 58333: Zarost_pod = Zarost_obr = 4.8 mm |
| it5_pressure_ctp_washer_77_5 | CTP Dshb_pod_u 77.5, Nshb_pod_u 1; b2 Dshb_so_obr_u 11.5 |
| it6_pressure_ctp_washer_72_8_final | CTP Dshb_pod_u 72.8; Dshb_so_obr_u a8 15.1, b2 11.7, b8 10.8 (40379 10.3) → FINAL |

## Golden values

Consumer washer in Zulu: ΔH = G²/(d/10)⁴ exactly (b2 it5: 11.5 mm, 4.563 t/h → 11.906 m).
CTP inlet washer: Zulu gave 0.70 m where the same formula gives 0.88 m (77.5 mm, 56.4 t/h); 72.8 mm → 0.90 m.
Rule: size the CTP washer from the result of a run, d_new = d · (ΔH_got / ΔH_needed)^¼.

Pressure calibration of the second contour (it6):

| Check | Model | Meter | Tolerance |
|---|---|---|---|
| CTP internal loss = inlet ΔP − outlet ΔP | 15.81 − 14.88 = 0.94 m | 14.5 − 13.6 = 0.9 m | ✅ |
| Loss CTP outlet → node 84089 (b2) | ≈ 2.55 m | 13.6 − 11.2 = 2.4 m | ✅ (±0.5 m) |
| Loss CTP outlet → node 84083 (b8) | ≈ 0.97 m | 13.6 − 13.0 = 0.6 m | ✅ (±0.5 m, two transducers) |
| Inlet ΔP | 15.81 m | 14.5 m | first contour, reported |

Overgrowth sizing: ΔH ∝ 1/d_eff^5.25, d_eff = Dвн − 2·Zarost; extra 0.87 m on 33639 + 58333 (DN100) → 4.8 mm; the run
confirmed the target (2.4 m), so Zulu treats Zarost as a layer thickness.

Final it6: heating a8 13.62 / 0.414 (−0.6 % / −1.4 %), b2 18.46 / 0.530 (−0.7 % / +1.8 %), b8 19.28 / 0.587
(−0.1 % / −0.8 %); CTP heating 51.38 (−0.4 %); inlet 57.12 (−2.9 %); DHW draw-off 0.91 / 1.13 / 1.23; circulation
2.27, T 48. Open: inlet ΔP +1.3 m and level −15 m (first contour).
