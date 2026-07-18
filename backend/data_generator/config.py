"""Central configuration of the synthetic-data simulator.

Every business rule shaping the dataset lives here: change a number, re-run,
get a different — but still internally consistent — five-year company
history. Deterministic under a seed (reproducible datasets, citable in the
thesis). Methodology: rule-driven chronological simulation, per prior work.

All prices are TND unless stated otherwise.
"""
from __future__ import annotations

import datetime as dt

# --- Simulation window & determinism ---------------------------------------
SIM_START = dt.date(2021, 7, 1)   # first tender may be issued on this day
SIM_NOW = dt.date(2026, 7, 1)     # "today": all statuses consistent with it
DEFAULT_SEED = 42

# --- Volumes ----------------------------------------------------------------
TENDERS_PER_YEAR = 40
MAX_PROJECTS = 65
BOQS_PER_PROJECT = (5, 16)        # for projects with a material scope
BOQ_LINES = (2, 6)
QUOTES_PER_RFQ = (2, 4)
ASSET_COUNT = 120

# --- Tendering rules --------------------------------------------------------
SCOPE_WEIGHTS = {                 # (E, P, C): weight — offers cover any subset
    (True, True, True): 30,
    (False, True, False): 22,     # procurement only
    (False, False, True): 14,
    (True, True, False): 10,
    (False, True, True): 12,
    (True, False, False): 7,
    (True, False, True): 5,
}
WIN_RATE = 0.36
WITHDRAW_RATE = 0.04
CANCEL_TENDER_RATE = 0.04
VALUE_RANGE_BY_SCOPE = {          # dominant scope -> TND range
    "epc": (1_500_000, 12_000_000),
    "procurement": (300_000, 3_000_000),
    "construction": (800_000, 6_000_000),
    "engineering": (150_000, 900_000),
}
SUBMISSION_WINDOW_DAYS = (20, 45)
DECISION_DELAY_DAYS = (15, 60)

# --- Project rules ----------------------------------------------------------
PROJECT_CODE_PREFIXES = ["JI", "SOR", "MP", "JFT", "TB"]
PROJECT_DURATION_MONTHS = (6, 24)
ON_HOLD_RATE = 0.05
PROJECT_START_DELAY_DAYS = (15, 45)
COMPLETION_SLIP_DAYS = (-20, 75)  # actual end vs planned

# --- Procurement chain timing (days) ---------------------------------------
BOQ_VALIDATION_DELAY = (1, 12)
BOQ_VALIDATION_RATE = 0.96
RFQ_ISSUE_DELAY = (1, 5)
RFQ_QUOTE_WINDOW = (10, 21)
PO_AWARD_DELAY = (3, 10)

LEAD_TIME_BY_CATEGORY = {         # supplier-promised days (triangular)
    "piping": (20, 35, 60),
    "valves": (30, 50, 90),
    "steel": (10, 20, 40),
    "electrical": (20, 40, 75),
    "instrumentation": (35, 60, 100),
    "coatings": (7, 14, 30),
    "welding_consumables": (5, 10, 20),
    "mechanical_equipment": (45, 75, 130),
    "safety": (7, 15, 30),
}
IMPORT_LEAD_TIME_FACTOR = 1.35

# --- Bid evaluation ---------------------------------------------------------
TBE_PASS_THRESHOLD = 70.0
TBE_MEAN, TBE_STD = 78.0, 9.0
CBE_PRICE_WEIGHT = 0.65
CBE_LEAD_WEIGHT = 0.35

# --- Delivery & logistics ---------------------------------------------------
SHIPMENT_SPLIT_WEIGHTS = {1: 70, 2: 25, 3: 5}
BASE_OTD = 0.85                   # on-time probability, normal suppliers
LATE_DELAY_DAYS = (2, 8, 35)      # triangular extra days when late
EARLY_DAYS_MAX = 3
TRANSIT_DAYS = {"road": (2, 6), "sea": (25, 45), "air": (3, 7), "multimodal": (15, 30)}
CUSTOMS_CLEARANCE_DAYS = {"Libye": (3, 8, 25), "Tunisie": (2, 5, 15)}
FREIGHT_COST_PCT_OF_VALUE = {
    "road": (0.010, 0.030), "sea": (0.015, 0.045),
    "air": (0.060, 0.120), "multimodal": (0.020, 0.055),
}
QC_WEIGHTS = {"accepted": 88, "accepted_with_reserve": 8, "rejected": 4}

# --- Payments ---------------------------------------------------------------
PAYMENT_PATTERNS = [([1.0], 45), ([0.3, 0.7], 35), ([0.2, 0.6, 0.2], 20)]
PAY_ON_TIME_RATE = 0.82
PAY_LATE_DAYS = (3, 12, 45)

# --- Assets -----------------------------------------------------------------
ASSET_CATEGORY_WEIGHTS = {
    "crane": 4, "welding_set": 18, "generator": 10, "vehicle": 14,
    "test_equipment": 8, "compressor": 6, "scaffolding": 10, "pump": 8,
    "it_equipment": 14, "furniture": 5, "tooling": 3,
}
ASSET_CONDITION_WEIGHTS = {
    "good": 68, "fair": 15, "damaged": 7, "under_repair": 5, "stolen": 2, "lost": 3,
}
ASSET_COST_RANGE = {
    "crane": (250_000, 950_000), "welding_set": (3_000, 25_000),
    "generator": (15_000, 120_000), "vehicle": (45_000, 220_000),
    "test_equipment": (8_000, 90_000), "compressor": (12_000, 80_000),
    "scaffolding": (5_000, 40_000), "pump": (6_000, 60_000),
    "it_equipment": (1_500, 9_000), "furniture": (300, 4_000),
    "tooling": (500, 15_000),
}
MAINTENANCE_EVENTS_PER_ASSET = (0, 8)
ASSET_ACQ_WINDOW = (dt.date(2015, 1, 1), dt.date(2026, 5, 1))

# --- Currency handling (generator-internal, for coherent budgets) ----------
# Fixed indicative rates to TND used ONLY by the simulator to keep project
# procurement spend coherent with contract values across currencies
# (an fx_rates table in the DB itself remains a documented v-next extension).
FX_TO_TND = {"TND": 1.00, "EUR": 3.40, "USD": 3.10, "LYD": 0.64}
# Procurement spend target as a share of contract value (for P/C-scope projects)
PROCUREMENT_BUDGET_SHARE = (0.35, 0.65)

# --- INJECTED STORIES (what demo charts will "discover") --------------------
STORY_LATE_SUPPLIER_CODE = "SUP-TSS"       # Trans-Sahara Steel Trading
STORY_LATE_SUPPLIER_OTD = 0.30             # vs 0.85 baseline
STORY_LATE_EXTRA_DELAY = (10, 18, 45)

STORY_STEEL_ESCALATION_START = dt.date(2024, 1, 1)
STORY_STEEL_ESCALATION_END = dt.date(2025, 6, 30)
STORY_STEEL_ESCALATION_PEAK = 1.45         # +45% at the end of the ramp

STORY_CUSTOMS_CRISIS_START = dt.date(2025, 1, 1)
STORY_CUSTOMS_CRISIS_END = dt.date(2025, 3, 31)
STORY_CUSTOMS_CRISIS_FACTOR = 2.5          # Libyan-route clearances x2.5

STORY_OVERBUDGET_TARGET_RATIO = 1.10       # one project spends 110% of contract
