# Golden fixtures — ЦТП «Береговая, 1/15»

CTP scheme N_schem = 3 (independent heating through a heat exchanger, parallel DHW). One building, GUID
c49b6336…: heating object 14744 (scheme 4), DHW object 21311 (scheme 26). Daily averages 10.02.2026, outdoor −12.8 °C.
Same file formats as `chernyshevskogo_8` (`ctp_card.tsv`, `consumers.csv`, address columns removed).

## Meter facts

| Block | Values |
|---|---|
| Inlet `_TS` | G 19.1 / 19.0 t/h; T 86.8 / 59.4 °C; P 80.1 / 72.5 m; Q 0.538 (G·ΔT 0.523) |
| CTP heating `_OT` | G 38.1 / 38.0; T 68.4 / **53.3** (sensor wrong); P 74.2 / 49.0; Q 0.586 (rejected) |
| CTP DHW `_GVS` | G1 3.3, G2 2.1; T 61.3 / 45.3; P 86.8 / 85.0; Q 0.10 |
| House heating 14744 | G 39.3; T 68.2 / 57.5; Q 0.419 |
| House DHW 21311 | G1 3.3, G2 2.1; T 60.4 / 45.8; Q 0.099 |

Balance check that rejects the CTP heating return sensor: house heating 0.419 + DHW 0.10 + losses ≈ inlet G·ΔT 0.523,
while the CTP heating meter alone gives 0.586 > inlet. Rule: one building behind the CTP and CTP T2 colder than the
building outlet by more than 2 °C → the CTP return sensor is rejected, the building meter is the target.

## Iterations (entered BEFORE each run)

| Folder | Entered |
|---|---|
| it0_initial | nothing: DHW HX test parameters junk (40/35/5/35, Q 0.001) → DHW 23 °C |
| it1_step1_hx_params_kgv_hgv2 | T12_i 61.5, T21_i 57.5, G1_i 16.7, G2_i 38.8; T11_i_niz 86.8, T12_i_niz 44.6, T21_i_niz 30.6, T22_i_niz 61.3, Q_i_niz 0.1; Hgv2_obr 112.3; Kgv 21311 = 0.474 |
| it2_washer_tcirc_trial | Dshb_pod 14744 = 33.8 (Dshb_so_pod_u 39 disappeared between runs → flow 45.05); Tcirc 21311 = 28.4 |
| it3_kso_washer_tcirc_final | Dshb_pod 14744 = 30.2; Kso 14744 = 0.695; Tcirc 21311 = 30.3 → FINAL |

## Golden values

Step 1 parallel DHW (formula from the algorithm, free parameter Tо = 61.5 chosen so that T12_niz ≥ T21_niz + 2):
Gгв = [1000·0.10 − 19.1·(61.5 − 59.4)] / (86.8 − 61.5) = 2.37 t/h; T12_niz = 86.8 − 100/2.37 = 44.6;
Gсо = 16.7; T21_niz = (1.2·5 + 2.1·45.3)/3.3 = 30.6; G2_i = 0.423·1000/(68.4 − 57.5) = 38.8.
Hgv2_obr = H_geo + P2_GVS = 27.3 + 85 = 112.3. Kgv = 1.2·(60 − 5)/(1000·0.139247) = 0.474.

Circulation model observed: Gcirc = Kcirc/100 · Ggv · √(H_ras/Hcirc) = 0.45 · 1.183 · √(1.536/0.1) = 2.09 (Zulu 2.115).
Tcirc changes only the loop cooling: Tcirc 33 → 12.8 °C, 28.4 → 16.6 °C; linear → 30.3 for 15.0 °C (result 14.9).

Washer with two points H(G) at the building: H = 25.188 − 0.003209·G²; system 3.13 m at 45.05 t/h;
target 38.7 → ΔHш = 18.07 m → d = 30.2 mm.
Kso with CTP regulator (heat independent of flow): 0.667 · 0.419 / 0.402 = 0.695.

Final state it3: inlet G −2.6 %, G·ΔT −0.8 %; heating G 38.9 (ЦТП 38.1 / house 39.3), Q −1.1 %, ΔT 10.6 vs 10.7;
draw-off 1.18 vs 1.2; circulation 2.12 vs 2.1; Tcirc 45.9 vs 45.8; DHW heat 0.098 / 0.100; DHW and heating
secondary pressures exact. Outside the second contour: inlet ΔP 7.2 vs 7.6 m, level −13 m (first contour).
