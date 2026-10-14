"""Tolerances and step criteria, in one place (docs/algorithm.md).

Values marked ASSUMPTION are not given as numbers in docs/algorithm.md; they implement a rule stated
there in words and should be confirmed by Andrew.
"""

# «Допуск» and step targets
TOLERANCE_PCT = 5.0  # flows, heat, temperatures
STEP_FLOW_TARGET_PCT = 2.0  # «Цель шага — расход ±2 %»
ESTIMATED_BLOCK_TOLERANCE_PCT = 7.0  # restored («расчётный») CTP block
MULTI_INPUT_GROUP_PCT = 2.0  # multi-input house: sum of the group
MULTI_INPUT_EACH_PCT = 5.0  # multi-input house: each input

# Meter checks 1–11 («Входные данные и проверка приборов»)
CHECK_HEAT_CLOSE_PCT = 2.0  # checks 1, 2 «близко / ≈» — ASSUMPTION
CHECK_INLET_BALANCE_PCT = 2.0  # check 3
# check 4: «дома возвращают почти всё» = houses lose < 25 % of the CTP «leak» — ASSUMPTION
CHECK_LEAK_HOUSES_SHARE = 0.25
CHECK_FLOWS_PCT = 3.0  # check 5
CHECK_LOSSES_PCT = (1.0, 3.0)  # check 6
CHECK_DRAW_OFF_PCT = 10.0  # check 7
CHECK_PRESSURE_SAME_SHIFT_M = 2.0  # check 11: «одинаковый сдвиг» — ASSUMPTION

# Step 1
STEP1_CLOSURE_PCT = 1.0  # G1_i·(T1 − T12_i)/1000 ≈ Qсо
STEP1_T12_I_MIN_GAP = 0.8  # T12_i ≥ T21_i + 0.8
STEP1_T12_VERH_MIN_GAP = 2.0  # T12_verh ≥ T21_verh + 2
STEP1_T22_NIZ_GAP = 2.0  # T22_niz 1.5–2 °C below T11_niz; default suggestion uses 2
STEP1_HEATING_TEMP_C = 0.7  # T3so_t / T2so_t ±0.7 °C
STEP1_INLET_T2_PCT = 4.0  # T2_t of the inlet ±4 %
STEP1_T11_NIZ_NOT_T1_C = 1.0  # «T11_niz ≈ расчётному (не T1)»: not within 1 °C of T1 — ASSUMPTION
KGV_DRAW_OFF_DIFF_PCT = 10.0  # Kgv only where draw-off differs by more than 10 %
KGV_NO_FLOW_T_H = 0.05  # G1_GVS − G2_GVS ≤ 0.05 t/h → Kgv by heat (approved method change)

# Step 2
STEP2_GCIRC_PCT = 10.0
STEP2_TCIRC_C = 1.5
HCIRC_PLACEHOLDER = 0.1

# Step 3 and 5
INLET_FLOW_PCT = 2.0  # G ввода ±2 %
WASHER_CHANGE_PCT = 2.0  # change a building washer only if |Gm/Gf − 1| > 2 %
HOUSE_FLOW_PCT = 2.0  # step 5: Gso each house ±2 %
CTP_SECOND_CIRCUIT_FLOW_PCT = 1.0  # step 5: Gsum_pod2 ±1 %
STEP1_SECOND_CIRCUIT_FLOW_PCT = 2.0  # step 1: Gsum_pod2 ±2 %
MIN_WASHER_MM = 3.0

# Step 4
HOUSE_HEAT_PCT = 5.0  # Q_sum each house ±5 %

# Rounding of values to enter in Zulu
ROUND_T = 1  # °C
ROUND_G = 1  # t/h
ROUND_Q = 3  # Gcal/h
ROUND_D = 1  # mm
ROUND_H = 1  # m
ROUND_KGV = 2
ROUND_KSO = 3
