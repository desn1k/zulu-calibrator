"""Tolerances and step criteria, in one place (docs/algorithm.md).

Values marked APPROVED are not given as numbers in docs/algorithm.md; they implement a rule stated
there in words and were approved by Andrew (2026-10-14).
"""

# «Допуск» (method change 2026-10-15) and step targets
TOLERANCE_PCT = 4.0  # flows, heat, pressure drops: ±4 % at most
# Return temperature: ±4 % of the value when the model supply is within 1 °C of the meter;
# otherwise ±4 % on ΔT (supply − return) and the absolute T2 shift is «первый контур / прибор».
TEMP_TOLERANCE_PCT = 4.0
TEMP_SUPPLY_MATCH_C = 1.0
STEP_FLOW_TARGET_PCT = 2.0  # «Цель шага — расход ±2 %»
ESTIMATED_BLOCK_TOLERANCE_PCT = 7.0  # restored («расчётный») CTP block: an estimate — APPROVED
MULTI_INPUT_GROUP_PCT = 2.0  # multi-input house: sum of the group
MULTI_INPUT_EACH_PCT = 4.0  # multi-input house: each input — APPROVED 2026-10-15

# Meter checks 1–11 («Входные данные и проверка приборов»)
CHECK_HEAT_CLOSE_PCT = 2.0  # checks 1, 2 «близко / ≈» — APPROVED
CHECK_INLET_BALANCE_PCT = 2.0  # check 3
# check 4: «дома возвращают почти всё» = houses lose < 25 % of the CTP «leak» — APPROVED
CHECK_LEAK_HOUSES_SHARE = 0.25
CHECK_FLOWS_PCT = 3.0  # check 5
CHECK_LOSSES_PCT = (1.0, 3.0)  # check 6
CHECK_DRAW_OFF_PCT = 10.0  # check 7
CHECK_PRESSURE_SAME_SHIFT_M = 2.0  # check 11: «одинаковый сдвиг» — APPROVED

# Step 1
STEP1_CLOSURE_PCT = 1.0  # G1_i·(T1 − T12_i)/1000 ≈ Qсо
STEP1_T12_I_MIN_GAP = 0.8  # T12_i ≥ T21_i + 0.8
STEP1_T12_VERH_MIN_GAP = 2.0  # T12_verh ≥ T21_verh + 2
STEP1_T22_NIZ_GAP = 2.0  # T22_niz 1.5–2 °C below T11_niz; default suggestion uses 2
STEP1_HEATING_TEMP_C = 0.7  # T3so_t / T2so_t ±0.7 °C
STEP1_T11_NIZ_NOT_T1_C = 1.0  # «T11_niz ≈ расчётному (не T1)»: not within 1 °C of T1 — APPROVED
# Kgv only where the draw-off differs by more than this. algorithm 1.3 says 10 %; the approved
# tolerance of 2026-10-15 caps every flow at ±4 % — QUESTION to Andrew (see HANDOFF).
KGV_DRAW_OFF_DIFF_PCT = 4.0
KGV_NO_FLOW_T_H = 0.05  # G1_GVS − G2_GVS ≤ 0.05 t/h → Kgv by heat (approved method change)

STEP1_DHW_TEMP_C = 1.0  # T DHW at the CTP outlet vs the meter (scheme 12 stage II) — QUESTION
KGV_MODEL_T_MIN_C = 40.0  # «по расходу модели» needs a warm model DHW at the object
DHW_HOUSES_AGREE_PCT = (
    10.0  # building DHW sum «agrees» with the CTP balance (as check 7) — QUESTION
)
PARALLEL_TO_START_GAP = 4.0  # parallel DHW, independent heating: Tо search starts at T21_i + 4
PARALLEL_TO_STEP = 0.5  # … in 0.5 °C steps
MIXED_T12_VERH_DEFAULT = 40.0  # scheme 5: T12_verh free parameter, default 40
DEAD_END_HGV2_RAS = 2.0  # dead-end DHW: Hgv2_ras default (Верхняя, 24)
HGV2_SUM_TOL_M = 0.5  # dead-end: leave Hgv2 when the sum is already within 0.5 m

CTP_RETURN_SENSOR_GAP_C = 2.0  # one building: CTP T2 colder than the building outlet by > 2 °C
CHANNEL_FACTOR_MAX_DIFF_PCT = 25.0  # flow channel: unmetered load factor vs metered — QUESTION

# Step 2
STEP2_GCIRC_PCT = 10.0
STEP2_TCIRC_C = 1.5
HCIRC_PLACEHOLDER = 0.1
# Gcirc matches and the model loop cooling is at least this share of the target → keep Kcirc /
# Hcirc and tune Tcirc only (Береговая); otherwise step 2 (Огородная) — QUESTION
STEP2_TCIRC_ONLY_COOLING_SHARE = 0.5

# Step 3 and 5
INLET_FLOW_PCT = 2.0  # G ввода ±2 %
WASHER_CHANGE_PCT = 2.0  # change a building washer only if |Gm/Gf − 1| > 2 %
HOUSE_FLOW_PCT = 2.0  # step 5: Gso each house ±2 %
CTP_SECOND_CIRCUIT_FLOW_PCT = 1.0  # step 5: Gsum_pod2 ±1 %
STEP1_SECOND_CIRCUIT_FLOW_PCT = 2.0  # step 1: Gsum_pod2 ±2 %
MIN_WASHER_MM = 3.0
MIN_FORECAST_HEAD_M = 4.0  # forecast head below → pipe data suspect (Верхняя, 24)
MIN_ELEVATOR_WASHER_DH_M = 0.5  # elevator: less head for a washer → remove it, size the nozzle
HEAD_POINTS_MIN_DG_PCT = 1.0  # two H(G) points need flows at least 1 % apart
STEPS_5_BEFORE_4_PCT = 20.0  # «Порядок 4 и 5»: house flows off by > 20 % → washers first

# Step 4
HOUSE_HEAT_PCT = 4.0  # Q_sum each house ±4 % — APPROVED 2026-10-15

# Rounding of values to enter in Zulu
ROUND_T = 1  # °C
ROUND_G = 1  # t/h
ROUND_Q = 3  # Gcal/h
ROUND_D = 1  # mm
ROUND_H = 1  # m
ROUND_KGV = 3  # README values of 2026-10-15 have 3 decimals (0.261, 0.089)
ROUND_KSO = 3
