"""Curated master data: clients, suppliers, materials, sites.

Names are fictional but plausible for the Tunisia/Libya EPC context (no real
company names are used in the synthetic dataset). Supplier profiles carry the
behavioural parameters used by the simulator (categories served, price level,
on-time-delivery probability, technical quality).
"""
from __future__ import annotations

# (code, name, country, sector)
CLIENTS = [
    ("CL-GSO", "Gulf of Sirte Oil Operations", "Libye", "oil_gas"),
    ("CL-FZP", "Fezzan Petroleum Company", "Libye", "oil_gas"),
    ("CL-TBK", "Tobruk Terminal Services", "Libye", "oil_gas"),
    ("CL-MLT", "Mellitah Processing Co", "Libye", "oil_gas"),
    ("CL-SRA", "Sahara Refining & Assets", "Libye", "oil_gas"),
    ("CL-INT", "IntEPC Contracting Ltd", "Royaume-Uni", "oil_gas"),
    ("CL-MED", "MedEnergy Partners", "Italie", "oil_gas"),
    ("CL-STG", "Société Tunisienne du Gaz Sud", "Tunisie", "oil_gas"),
    ("CL-TPP", "Tunisian Power Projects", "Tunisie", "power"),
    ("CL-SFX", "Sfax Industrial Terminal", "Tunisie", "industrial"),
    ("CL-ONI", "Office National des Infrastructures", "Tunisie", "government"),
    ("CL-GAB", "Gabès Chemical Industries", "Tunisie", "industrial"),
]

# (code, name, country, city, payment_terms_days, preferred_payment_method,
#  categories_served, price_factor, otd_prob_or_None, quality_0_1)
# otd None => use BASE_OTD from config; the story supplier has its own value.
SUPPLIERS = [
    ("SUP-TAC", "Tunisie Acier Sfax", "Tunisie", "Sfax", 60, "bank_transfer",
     ["steel", "welding_consumables"], 1.00, None, 0.72),
    ("SUP-TSS", "Trans-Sahara Steel Trading", "Tunisie", "Ben Guerdane", 45, "check",
     ["steel", "piping"], 0.91, "STORY", 0.55),   # cheap but habitually late
    ("SUP-MTL", "Maghreb Tubes & Lignes", "Tunisie", "Tunis", 60, "bank_transfer",
     ["piping", "valves"], 1.02, None, 0.70),
    ("SUP-SEL", "Sfax Électro-Industrie", "Tunisie", "Sfax", 45, "bank_transfer",
     ["electrical", "instrumentation"], 1.04, None, 0.74),
    ("SUP-CPT", "Carthage Peintures Techniques", "Tunisie", "Tunis", 30, "check",
     ["coatings"], 0.98, None, 0.68),
    ("SUP-NSE", "Nord Sécurité Équipements", "Tunisie", "Sousse", 30, "bank_transfer",
     ["safety"], 1.00, None, 0.66),
    ("SUP-ATM", "Atelier Tunisien de Mécanique", "Tunisie", "Sfax", 60, "bank_transfer",
     ["mechanical_equipment", "welding_consumables"], 1.03, None, 0.71),
    ("SUP-MVI", "Milano Valvole Industriali", "Italie", "Milan", 90, "letter_of_credit",
     ["valves", "instrumentation"], 1.22, None, 0.88),
    ("SUP-GPI", "Genova Piping International", "Italie", "Gênes", 90, "letter_of_credit",
     ["piping", "steel"], 1.18, None, 0.85),
    ("SUP-LYS", "Lyon Systèmes de Contrôle", "France", "Lyon", 90, "letter_of_credit",
     ["instrumentation", "electrical"], 1.30, None, 0.90),
    ("SUP-BAV", "Bavaria Pumpen & Kompressoren", "Allemagne", "Munich", 90, "letter_of_credit",
     ["mechanical_equipment"], 1.35, None, 0.93),
    ("SUP-IST", "Istanbul Çelik Export", "Turquie", "Istanbul", 75, "letter_of_credit",
     ["steel", "piping"], 0.96, None, 0.68),
    ("SUP-ANK", "Anadolu Vana Sanayi", "Turquie", "Ankara", 75, "letter_of_credit",
     ["valves"], 0.98, None, 0.70),
    ("SUP-CNE", "Ningbo Electro Components", "Chine", "Ningbo", 60, "letter_of_credit",
     ["electrical"], 0.82, None, 0.60),
    ("SUP-CNV", "Shanghai Valve Works", "Chine", "Shanghai", 60, "letter_of_credit",
     ["valves", "piping"], 0.80, None, 0.58),
    ("SUP-DXB", "Gulf Instruments FZE", "Émirats", "Dubaï", 60, "letter_of_credit",
     ["instrumentation", "safety"], 1.10, None, 0.80),
    ("SUP-EGY", "Alexandria Coatings Co", "Égypte", "Alexandrie", 45, "promissory_note",
     ["coatings", "welding_consumables"], 0.90, None, 0.62),
    ("SUP-ESP", "Valencia Aceros SL", "Espagne", "Valence", 90, "letter_of_credit",
     ["steel"], 1.12, None, 0.82),
]

# category -> list of (name, unit, ref_unit_price TND)
MATERIALS = {
    "piping": [
        ("Pipe CS A106 Gr.B 6\" Sch40", "m", 145), ("Pipe CS A106 Gr.B 10\" Sch40", "m", 260),
        ("Pipe SS 316L 4\" Sch10", "m", 310), ("Elbow 90° CS 6\"", "piece", 85),
        ("Flange WN CS 6\" 150#", "piece", 120), ("Tee CS 10\"", "piece", 240),
    ],
    "valves": [
        ("Gate valve CS 6\" 150#", "piece", 1450), ("Ball valve SS 4\" 300#", "piece", 2600),
        ("Check valve CS 10\" 150#", "piece", 1900), ("Globe valve CS 3\" 300#", "piece", 1100),
        ("Safety relief valve 2\"", "piece", 3400),
    ],
    "steel": [
        ("Steel plate S355 10mm", "sheet", 450), ("Steel plate S355 20mm", "sheet", 870),
        ("HEA 200 beam", "m", 95), ("IPE 300 beam", "m", 125),
        ("Angle bar 100x100x10", "m", 38), ("Rebar HA16", "ton", 2350),
    ],
    "electrical": [
        ("Cable Cu XLPE 4x25mm²", "m", 42), ("Cable Cu XLPE 4x95mm²", "m", 140),
        ("Cable tray HDG 300mm", "m", 55), ("Distribution panel 400A", "piece", 8200),
        ("LED floodlight ATEX 150W", "piece", 780), ("Motor 3ph 22kW", "piece", 4600),
    ],
    "instrumentation": [
        ("Pressure transmitter 0-100bar", "piece", 2900), ("Temperature transmitter PT100", "piece", 1750),
        ("Flow meter electromagnetic 4\"", "piece", 9800), ("Level radar transmitter", "piece", 7400),
        ("Control valve 2\" + positioner", "piece", 11200),
    ],
    "coatings": [
        ("Epoxy primer Zn-rich", "drum", 620), ("Epoxy intermediate coat", "drum", 480),
        ("Polyurethane topcoat", "drum", 540), ("Thinner industrial", "drum", 180),
    ],
    "welding_consumables": [
        ("Electrode E7018 3.2mm", "kg", 12), ("Wire ER70S-6 1.2mm", "kg", 14),
        ("Flux SAW F7A2", "kg", 9), ("Argon-CO2 mix bottle", "piece", 95),
    ],
    "mechanical_equipment": [
        ("Centrifugal pump API610 45kW", "piece", 68000), ("Air compressor 500L 11kW", "piece", 21000),
        ("Heat exchanger shell&tube 20m²", "piece", 54000), ("Storage tank agitator 15kW", "piece", 32000),
    ],
    "safety": [
        ("Safety harness kit", "set", 240), ("Fire extinguisher CO2 5kg", "piece", 210),
        ("Gas detector 4-gas portable", "piece", 1850), ("Safety helmet + accessories", "set", 65),
    ],
}

# (code, name, country, region, site_type)
SITES = [
    ("ST-SFX-SHOP", "Atelier de fabrication Sfax", "Tunisie", "Sfax", "fabrication_shop"),
    ("ST-SFX-WH", "Entrepôt central Sfax", "Tunisie", "Sfax", "warehouse"),
    ("ST-TUN-HQ", "Siège Tunis", "Tunisie", "Tunis", "office"),
    ("ST-TAT", "Site champ Tataouine", "Tunisie", "Tataouine", "field_site"),
    ("ST-GAB", "Site industriel Gabès", "Tunisie", "Gabès", "field_site"),
    ("ST-ERW", "Erawin Field", "Libye", "Fezzan", "field_site"),
    ("ST-SRR", "Sarir Complex", "Libye", "Cyrénaïque", "field_site"),
    ("ST-TBK", "Tobruk Terminal", "Libye", "Cyrénaïque", "field_site"),
    ("ST-MLT", "Mellitah Plant", "Libye", "Tripolitaine", "field_site"),
    ("ST-DFA", "Defa Field", "Libye", "Fezzan", "field_site"),
]

DISCIPLINE_TO_CATEGORIES = {
    "civil": ["steel", "safety"],
    "mechanical": ["mechanical_equipment", "steel", "welding_consumables"],
    "piping": ["piping", "valves", "welding_consumables"],
    "electrical": ["electrical"],
    "instrumentation": ["instrumentation"],
    "hse": ["safety"],
    "general": ["steel", "piping", "electrical", "coatings", "safety"],
}

TENDER_TITLE_TEMPLATES = [
    "{scope} — {what} for {site}",
]
TENDER_WHAT = [
    "crude storage tank rehabilitation", "jet fuel station package", "water injection system",
    "produced-water treatment unit", "pipeline tie-in works", "early production facility",
    "cathodic protection system", "metering skid supply", "flare system revamp",
    "substation & MCC upgrade", "firefighting network extension", "steel structures package",
    "pressure vessels fabrication", "field camp utilities", "loading arms refurbishment",
]
