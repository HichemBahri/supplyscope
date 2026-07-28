"""Chronological business simulator for the SupplyScope mock ERP (schema v2).

Replays ~5 years of an EPC contractor's life in causal order:
tenders -> proposals (client award) -> projects -> BoQs (Engineering
validation) -> RFQs -> supplier quotations (TBE/CBE) -> purchase orders ->
shipments (customs on cross-border routes) -> goods receipts -> payments,
plus the company asset register.

Output: an in-memory row store (dict of table -> list of tuples) whose
insertion order encodes all foreign keys (row N of a table gets identity N,
guaranteed by loading into freshly TRUNCATE ... RESTART IDENTITY tables).
"""
from __future__ import annotations

import datetime as dt
import math
import math
import random

from . import config as C
from . import reference_data as R

DAY = dt.timedelta(days=1)


def _dominant_scope(e: bool, p: bool, c: bool) -> str:
    if e and p and c:
        return "epc"
    if c:
        return "construction"
    if p:
        return "procurement"
    return "engineering"


class Simulator:
    """Deterministic generator of a coherent company history."""

    def __init__(self, seed: int = C.DEFAULT_SEED):
        self.rng = random.Random(seed)
        self.rows: dict[str, list[tuple]] = {t: [] for t in (
            "clients", "suppliers", "materials", "sites", "fx_rates",
            "tenders", "proposals", "projects",
            "boqs", "boq_lines", "rfqs", "supplier_quotations",
            "purchase_orders", "po_lines", "payments",
            "shipments", "shipment_lines", "goods_receipts",
            "assets", "asset_assignments", "maintenance_events",
        )}
        # side registries (indexed by 1-based id, aligned with insertion order)
        self.supplier_profiles: dict[int, dict] = {}
        self.material_info: dict[int, dict] = {}
        self.site_info: dict[int, dict] = {}
        self.client_info: dict[int, dict] = {}
        self.project_info: dict[int, dict] = {}
        self.po_info: dict[int, dict] = {}
        self.po_line_info: dict[int, dict] = {}
        self.pol_category: dict[int, str] = {}
        self._counters: dict[str, int] = {}

    # ------------------------------------------------------------------ utils
    def _add(self, table: str, row: tuple) -> int:
        self.rows[table].append(row)
        return len(self.rows[table])

    def _ref(self, prefix: str, year: int) -> str:
        key = f"{prefix}-{year}"
        self._counters[key] = self._counters.get(key, 0) + 1
        return f"{prefix}-{year}-{self._counters[key]:04d}"

    def _tri(self, spec: tuple[float, float, float]) -> float:
        lo, mode, hi = spec
        return self.rng.triangular(lo, hi, mode)

    def _weighted(self, weights: dict):
        keys = list(weights.keys())
        return self.rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]

    def _date_between(self, a: dt.date, b: dt.date) -> dt.date:
        if b <= a:
            return a
        return a + DAY * self.rng.randint(0, (b - a).days)

    def escalation(self, category: str, on: dt.date) -> float:
        """Price multiplier over time; steel follows the injected escalation story."""
        drift = 1.0 + 0.02 * ((on - C.SIM_START).days / 365.25)   # 2%/yr inflation
        if category == "steel":
            s, e = C.STORY_STEEL_ESCALATION_START, C.STORY_STEEL_ESCALATION_END
            if on >= e:
                drift *= C.STORY_STEEL_ESCALATION_PEAK
            elif on > s:
                frac = (on - s).days / (e - s).days
                drift *= 1.0 + (C.STORY_STEEL_ESCALATION_PEAK - 1.0) * frac
        return drift

    def _currency_for_client(self, country: str) -> str:
        return {"Tunisie": "TND", "Libye": "USD"}.get(country, "EUR")

    def _currency_for_supplier(self, country: str) -> str:
        if country == "Tunisie":
            return "TND"
        if country in ("Italie", "France", "Allemagne", "Espagne"):
            return "EUR"
        return "USD"

    # ------------------------------------------------------- reference data
    def build_reference(self) -> None:
        for code, name, country, sector in R.CLIENTS:
            cid = self._add("clients", (code, name, country, sector, True))
            self.client_info[cid] = {"country": country}
        for (code, name, country, city, terms, method,
             cats, price_f, otd, quality) in R.SUPPLIERS:
            sid = self._add("suppliers", (code, name, country, city, terms, method, True))
            self.supplier_profiles[sid] = {
                "code": code, "country": country, "categories": set(cats),
                "price_factor": price_f, "quality": quality,
                "otd": (C.STORY_LATE_SUPPLIER_OTD if otd == "STORY" else C.BASE_OTD),
                "story_late": otd == "STORY",
            }
        for category, items in R.MATERIALS.items():
            for i, (name, unit, price) in enumerate(items, start=1):
                code = f"MAT-{category[:4].upper()}-{i:02d}"
                mid = self._add("materials", (code, name, category, unit, price, "TND"))
                self.material_info[mid] = {"category": category, "unit": unit, "ref_price": price}
        for cur, rate in C.FX_TO_TND.items():
            self._add("fx_rates", (cur, rate))
        for code, name, country, region, stype in R.SITES:
            sid = self._add("sites", (code, name, country, region, stype))
            self.site_info[sid] = {"country": country, "type": stype}

    # ------------------------------------------------------- commercial phase
    def simulate_commercial(self) -> None:
        month = C.SIM_START.replace(day=1)
        while month <= C.SIM_NOW:
            lam = C.TENDERS_PER_YEAR / 12.0
            for _ in range(self._poisson(lam)):
                self._spawn_tender(month)
            month = (month.replace(day=28) + 5 * DAY).replace(day=1)

    def _poisson(self, lam: float) -> int:
        # Knuth's algorithm — small lambda, deterministic under self.rng
        p, k, target = 1.0, 0, math.exp(-lam)
        while p > target:
            k += 1
            p *= self.rng.random()
        return k - 1

    def _spawn_tender(self, month: dt.date) -> None:
        client_id = self.rng.randint(1, len(self.rows["clients"]))
        c_country = self.client_info[client_id]["country"]
        scope = self._weighted(C.SCOPE_WEIGHTS)
        e, p, c = scope
        dom = _dominant_scope(e, p, c)
        issue = self._date_between(month, min(month + 27 * DAY, C.SIM_NOW))
        deadline = issue + DAY * self.rng.randint(*C.SUBMISSION_WINDOW_DAYS)
        lo, hi = C.VALUE_RANGE_BY_SCOPE[dom]
        est = round(self.rng.uniform(lo, hi), -3)
        currency = self._currency_for_client(c_country)
        scope_label = "".join(x for x, f in zip("EPC", (e, p, c)) if f)
        site_hint = self.rng.choice([s[1] for s in R.SITES if s[4] == "field_site"])
        title = f"{scope_label} — {self.rng.choice(R.TENDER_WHAT)} for {site_hint}"
        year = issue.year
        t_status = "open"
        tender_id = self._add("tenders", (
            self._ref("TDR", year), client_id, title, e, p, c,
            issue, deadline, est, currency, t_status,
        ))

        # --- proposal lifecycle
        r = self.rng.random()
        if r < C.WITHDRAW_RATE:
            status, submitted, decision = "withdrawn", None, None
            proposed = None
        else:
            submitted = deadline - DAY * self.rng.randint(0, 6)
            proposed = round(est * self.rng.uniform(0.88, 1.06), -3)
            decision = submitted + DAY * self.rng.randint(*C.DECISION_DELAY_DAYS)
            if submitted > C.SIM_NOW:
                status, submitted, decision, proposed = "draft", None, None, None
            elif decision > C.SIM_NOW:
                status, decision = "submitted", None
            else:
                won = self.rng.random() < C.WIN_RATE
                if won and len(self.rows["projects"]) >= C.MAX_PROJECTS:
                    won = False   # portfolio full: coherence requires losing this bid
                status = "won" if won else "lost"
        prop_id = self._add("proposals", (
            tender_id, submitted, proposed,
            self.rows["tenders"][tender_id - 1][9], status, decision,
        ))
        if self.rng.random() < C.CANCEL_TENDER_RATE and status not in ("won",):
            self._set_tender_status(tender_id, "cancelled")
        elif status in ("won", "lost"):
            self._set_tender_status(tender_id, "awarded")
        if status == "won" and len(self.rows["projects"]) < C.MAX_PROJECTS:
            self._spawn_project(tender_id, prop_id, (e, p, c), proposed, decision, client_id)

    def _set_tender_status(self, tender_id: int, status: str) -> None:
        row = list(self.rows["tenders"][tender_id - 1])
        row[10] = status
        self.rows["tenders"][tender_id - 1] = tuple(row)

    def _spawn_project(self, tender_id: int, prop_id: int, scope, value, award: dt.date,
                       client_id: int) -> None:
        e, p, c = scope
        c_country = self.client_info[client_id]["country"]
        candidate_sites = [sid for sid, s in self.site_info.items()
                           if s["type"] == "field_site" and s["country"] == c_country]
        if not candidate_sites:  # foreign client -> work happens at the shop
            candidate_sites = [sid for sid, s in self.site_info.items()
                               if s["type"] == "fabrication_shop"]
        site_id = self.rng.choice(candidate_sites)
        start = award + DAY * self.rng.randint(*C.PROJECT_START_DELAY_DAYS)
        v_lo, v_hi = C.VALUE_RANGE_BY_SCOPE["epc"]
        size = min(1.0, math.log10(max(value, 1)) / math.log10(v_hi))
        months = round(C.PROJECT_DURATION_MONTHS[0]
                       + size * (C.PROJECT_DURATION_MONTHS[1] - C.PROJECT_DURATION_MONTHS[0]))
        planned_end = start + DAY * int(months * 30.4)
        actual_end = None
        if planned_end < C.SIM_NOW:
            status = "completed"
            actual_end = planned_end + DAY * self.rng.randint(*C.COMPLETION_SLIP_DAYS)
            actual_end = min(actual_end, C.SIM_NOW)
            if actual_end < start:
                actual_end = planned_end
        elif start > C.SIM_NOW:
            status = "planning"
        else:
            status = "on_hold" if self.rng.random() < C.ON_HOLD_RATE else "active"
        prefix = self.rng.choice(C.PROJECT_CODE_PREFIXES)
        self._counters["project"] = self._counters.get("project", 0) + 1
        code = f"{prefix}{2000 + self._counters['project']}"
        name = self.rows["tenders"][tender_id - 1][2].split("— ", 1)[-1][:80]
        currency = self.rows["tenders"][tender_id - 1][9]
        proj_id = self._add("projects", (
            code, name, client_id, site_id, prop_id, e, p, c,
            value, currency, start, planned_end, actual_end, status,
        ))
        value_tnd = value * C.FX_TO_TND[currency]
        self.project_info[proj_id] = {
            "scopes": (e, p, c), "value": value, "currency": currency,
            "value_tnd": value_tnd,
            "budget_tnd": value_tnd * self.rng.uniform(*C.PROCUREMENT_BUDGET_SHARE),
            "site_id": site_id, "start": start, "end": planned_end,
            "status": status, "code": code, "spend_tnd": 0.0, "po_ids": [],
        }

    # ------------------------------------------------------ procurement phase
    def simulate_procurement(self) -> None:
        mats_by_cat: dict[str, list[int]] = {}
        for mid, info in self.material_info.items():
            mats_by_cat.setdefault(info["category"], []).append(mid)
        for proj_id, proj in self.project_info.items():
            e, p, c = proj["scopes"]
            if not (p or c) or proj["status"] == "planning":
                continue
            size_factor = min(1.0, proj["value"] / 6_000_000)
            lo, hi = C.BOQS_PER_PROJECT
            n_boqs = self.rng.randint(lo, max(lo + 1, round(lo + size_factor * (hi - lo))))
            for _ in range(n_boqs):
                if proj["spend_tnd"] >= proj["budget_tnd"]:
                    break   # procurement budget for this project is consumed
                self._spawn_boq_chain(proj_id, proj, mats_by_cat)

    def _spawn_boq_chain(self, proj_id: int, proj: dict, mats_by_cat) -> None:
        start, end = proj["start"], proj["end"]
        req = self._date_between(start, start + (end - start) * 6 // 10)
        if req > C.SIM_NOW:
            return
        needed = req + DAY * self.rng.randint(30, 90)
        discipline = self.rng.choice(list(R.DISCIPLINE_TO_CATEGORIES))
        year = req.year
        validated = self.rng.random() < C.BOQ_VALIDATION_RATE
        val_date = req + DAY * self.rng.randint(*C.BOQ_VALIDATION_DELAY) if validated else None
        if val_date and val_date > C.SIM_NOW:
            validated, val_date = False, None
        boq_status = "draft" if not validated else "approved"
        boq_id = self._add("boqs", (
            f"BOQ-{proj['code']}-{self._boq_seq(proj['code'])}",
            proj_id, discipline, req, needed, validated, val_date, boq_status,
        ))
        # lines
        cats = R.DISCIPLINE_TO_CATEGORIES[discipline]
        cat = self.rng.choice(cats)
        pool = list(mats_by_cat[cat])
        self.rng.shuffle(pool)
        n_lines = self.rng.randint(*C.BOQ_LINES)
        chosen = pool[:n_lines]
        if len(chosen) < C.BOQ_LINES[0]:   # small categories: top up from a sibling
            extra = [m for cc in cats for m in mats_by_cat[cc] if m not in chosen]
            self.rng.shuffle(extra)
            chosen += extra[: C.BOQ_LINES[0] - len(chosen)]
        remaining = max(0.0, proj["budget_tnd"] - proj["spend_tnd"])
        boq_target = max(15_000.0, remaining * self.rng.uniform(0.08, 0.25))
        # Envelope fix (v2.2): quantity floors mean every listed material costs
        # at least ONE unit — so big-ticket items on small budgets silently
        # burst the procurement envelope (bug exposed by reseed: a 333k-TND
        # project accumulated 3.3x its contract). A chain may only include
        # materials it can afford at least one unit of; if none qualify,
        # it takes the single cheapest so tiny projects still procure.
        def _unit_value(mid: int) -> float:
            info = self.material_info[mid]
            return info["ref_price"] * self.escalation(info["category"], req) \
                * C.FX_TO_TND.get(info.get("currency", "TND"), 1.0)
        affordable = [m for m in chosen if _unit_value(m) <= boq_target]
        if not affordable:
            affordable = [min(chosen, key=_unit_value)]
        weights = [self.rng.uniform(0.5, 1.5) for _ in affordable]
        wsum = sum(weights)
        line_ids = []
        for mid, w in zip(affordable, weights):
            info = self.material_info[mid]
            unit_value = info["ref_price"] * self.escalation(info["category"], req)
            qty = self._round_qty((boq_target * w / wsum) / unit_value, info["unit"])
            line_ids.append((self._add("boq_lines", (boq_id, mid, qty)), mid, qty))
        if not validated:
            return
        self._spawn_rfq(boq_id, proj_id, proj, cat, line_ids, val_date)

    def _boq_seq(self, code: str) -> str:
        key = f"boq-{code}"
        self._counters[key] = self._counters.get(key, 0) + 1
        return f"{self._counters[key]:03d}"

    def _round_qty(self, q: float, unit: str) -> float:
        """Round a computed quantity to a realistic figure for its unit."""
        if unit in ("piece", "set", "sheet", "drum"):
            return float(max(1, round(q)))
        if unit == "ton":
            return max(0.5, round(q, 1))
        return float(max(1, round(q)))  # m, kg, liter

    def _spawn_rfq(self, boq_id, proj_id, proj, category, line_ids, val_date) -> None:
        issue = val_date + DAY * self.rng.randint(*C.RFQ_ISSUE_DELAY)
        if issue > C.SIM_NOW:
            return
        due = issue + DAY * self.rng.randint(*C.RFQ_QUOTE_WINDOW)
        year = issue.year
        rfq_id = self._add("rfqs", (self._ref("RFQ", year), boq_id, issue, due, "issued"))
        self._boq_set_status(boq_id, "rfq_issued")

        candidates = [sid for sid, sp in self.supplier_profiles.items()
                      if category in sp["categories"]]
        if len(candidates) < 2:
            candidates += [sid for sid, sp in self.supplier_profiles.items()
                           if sp["categories"] & set(R.DISCIPLINE_TO_CATEGORIES.get("general", []))]
        self.rng.shuffle(candidates)
        n_quotes = min(len(candidates), self.rng.randint(*C.QUOTES_PER_RFQ))
        quoted = []
        base_value = sum(self.material_info[mid]["ref_price"]
                         * self.escalation(self.material_info[mid]["category"], due) * qty
                         for _, mid, qty in line_ids)
        for sid in candidates[:n_quotes]:
            sp = self.supplier_profiles[sid]
            price = base_value * sp["price_factor"] * self.rng.uniform(0.95, 1.12)
            lt = self._tri(C.LEAD_TIME_BY_CATEGORY[category])
            if sp["country"] != "Tunisie":
                lt *= C.IMPORT_LEAD_TIME_FACTOR
            lead = max(3, round(lt))
            tbe = max(30.0, min(98.0, self.rng.gauss(
                C.TBE_MEAN + (sp["quality"] - 0.72) * 40, C.TBE_STD)))
            quoted.append({"sid": sid, "price": price, "lead": lead, "tbe": round(tbe, 1)})
        if due > C.SIM_NOW or not quoted:
            for q in quoted:
                self._add("supplier_quotations", (
                    rfq_id, q["sid"], min(due, C.SIM_NOW), round(q["price"], 2),
                    self._currency_for_supplier(self.supplier_profiles[q["sid"]]["country"]),
                    q["lead"], None, None, "received"))
            return

        min_price = min(q["price"] for q in quoted)
        min_lead = min(q["lead"] for q in quoted)
        for q in quoted:
            ps = 100.0 * min_price / q["price"]
            ls = 100.0 * min_lead / q["lead"]
            q["cbe"] = round(max(20.0, min(99.0,
                C.CBE_PRICE_WEIGHT * ps + C.CBE_LEAD_WEIGHT * ls + self.rng.uniform(-4, 4))), 1)
        qualified = [q for q in quoted if q["tbe"] >= C.TBE_PASS_THRESHOLD]
        winner = max(qualified, key=lambda q: q["cbe"]) if qualified else None
        for q in quoted:
            st = "selected" if winner and q is winner else "rejected"
            self._add("supplier_quotations", (
                rfq_id, q["sid"], due - DAY * self.rng.randint(0, 3), round(q["price"], 2),
                self._currency_for_supplier(self.supplier_profiles[q["sid"]]["country"]),
                q["lead"], q["tbe"], q["cbe"], st))
        if winner is None:
            self._rfq_set_status(rfq_id, "cancelled")
            return
        self._rfq_set_status(rfq_id, "awarded")
        self._spawn_po(proj_id, proj, rfq_id, winner, line_ids, due, category)

    def _boq_set_status(self, boq_id: int, status: str) -> None:
        row = list(self.rows["boqs"][boq_id - 1]); row[7] = status
        self.rows["boqs"][boq_id - 1] = tuple(row)

    def _rfq_set_status(self, rfq_id: int, status: str) -> None:
        row = list(self.rows["rfqs"][rfq_id - 1]); row[4] = status
        self.rows["rfqs"][rfq_id - 1] = tuple(row)

    # -------------------------------------------------------------- PO & flow
    def _spawn_po(self, proj_id, proj, rfq_id, winner, line_ids, due, category) -> None:
        order = due + DAY * self.rng.randint(*C.PO_AWARD_DELAY)
        if order > C.SIM_NOW:
            return
        sp = self.supplier_profiles[winner["sid"]]
        promised = order + DAY * winner["lead"]
        currency = self._currency_for_supplier(sp["country"])
        incoterm = self.rng.choice(["EXW", "DAP"] if sp["country"] == "Tunisie"
                                   else ["CIF", "CPT", "DAP", "DDP"])
        year = order.year
        po_id = self._add("purchase_orders", (
            self._ref("PO", year), proj_id, winner["sid"], rfq_id, order, promised,
            incoterm, currency, 0.0, "issued"))
        po_lines = []
        for _, mid, qty in line_ids:
            info = self.material_info[mid]
            unit_price = round(info["ref_price"] * self.escalation(info["category"], order)
                               * sp["price_factor"] * self.rng.uniform(0.95, 1.10), 2)
            pol_id = self._add("po_lines", (po_id, mid, qty, unit_price))
            self.po_line_info[pol_id] = {"po_id": po_id, "qty": qty, "price": unit_price}
            self.pol_category[pol_id] = info["category"]
            po_lines.append((pol_id, qty, unit_price))
        total = round(sum(q * p for _, q, p in po_lines), 2)
        self.po_info[po_id] = {
            "project_id": proj_id, "supplier_id": winner["sid"], "order": order,
            "promised": promised, "total": total, "currency": currency,
            "lines": po_lines, "delivered_dates": [], "category": category,
        }
        proj["po_ids"].append(po_id)
        proj["spend_tnd"] += total * C.FX_TO_TND[currency]
        self._spawn_shipments(po_id, proj, sp)
        self._spawn_payments(po_id, sp)
        self._finalize_po_status(po_id)

    def _spawn_shipments(self, po_id: int, proj: dict, sp: dict) -> None:
        po = self.po_info[po_id]
        n_split = self._weighted(C.SHIPMENT_SPLIT_WEIGHTS)
        lines = list(po["lines"])
        self.rng.shuffle(lines)
        chunks = [lines[i::n_split] for i in range(n_split)]
        chunks = [ch for ch in chunks if ch]
        dest = proj["site_id"]
        if self.site_info[dest]["type"] == "office":
            dest = 2  # central warehouse
        for k, chunk in enumerate(chunks):
            self._spawn_one_shipment(po_id, po, chunk, sp, dest, k)

    def _p_late(self, sp, requires_customs, dest_country, planned,
                lead_days, mode, category) -> float:
        """v2.2 multi-factor risk process (see config for coefficients)."""
        base = min(max(1.0 - sp["otd"], 0.02), 0.98)
        a = C.RISK_SUPPLIER_WEIGHT * math.log(base / (1.0 - base)) + C.RISK_INTERCEPT
        if requires_customs:
            a += C.RISK_BETA_CUSTOMS
            if dest_country == "Libye":
                a += C.RISK_BETA_LIBYA
                if C.STORY_CUSTOMS_CRISIS_START <= planned <= C.STORY_CUSTOMS_CRISIS_END:
                    a += C.RISK_BETA_CRISIS
        if lead_days > 60:
            a += C.RISK_BETA_LONG_LEAD
        a += C.RISK_BETA_MODE[mode]
        a += C.RISK_BETA_CATEGORY.get(category, 0.0)
        return 1.0 / (1.0 + math.exp(-a))

    def _spawn_one_shipment(self, po_id, po, chunk, sp, dest_site, k) -> None:
        dest_country = self.site_info[dest_site]["country"]
        if sp["country"] in ("Tunisie", "Libye"):
            mode = "road"
        else:
            mode = self.rng.choices(["sea", "air", "multimodal"], weights=[70, 15, 15])[0]
        # v2.2: every partial delivery shares the PO's contractual due date.
        # (Previously later chunks got a "staggered" due date; shipments could
        # then be on-time vs their internal plan yet late vs the promised date
        # used for labels — pure label noise, caught by the oracle audit.)
        planned = po["promised"]
        requires_customs_v2 = sp["country"] != dest_country
        lead_days = (po["promised"] - po["order"]).days
        dominant_cat = self.pol_category.get(chunk[0][0], "consumables") if chunk else "consumables"
        on_time = self.rng.random() >= self._p_late(
            sp, requires_customs_v2, dest_country, planned, lead_days, mode, dominant_cat)
        if on_time:
            actual = planned - DAY * self.rng.randint(0, C.EARLY_DAYS_MAX)
        else:
            extra = self._tri(C.STORY_LATE_EXTRA_DELAY if sp["story_late"] else C.LATE_DELAY_DAYS)
            actual = planned + DAY * max(1, round(extra))
        transit = self.rng.randint(*C.TRANSIT_DAYS[mode])
        requires_customs = sp["country"] != dest_country
        entry = clearance = None
        if requires_customs:
            cd = self._tri(C.CUSTOMS_CLEARANCE_DAYS.get(dest_country, (2, 5, 15)))
            probe = actual - DAY * (round(cd) + self.rng.randint(1, 3))
            if (dest_country == "Libye"
                    and C.STORY_CUSTOMS_CRISIS_START <= probe <= C.STORY_CUSTOMS_CRISIS_END):
                cd *= C.STORY_CUSTOMS_CRISIS_FACTOR
            cdays = max(1, round(cd))
            entry = actual - DAY * (cdays + self.rng.randint(1, 3))
            clearance = entry + DAY * cdays
            actual = max(actual, clearance + DAY)
        ship = actual - DAY * transit
        if ship <= po["order"]:
            ship = po["order"] + DAY
        eta = planned + DAY * self.rng.randint(-2, 3)
        value = sum(q * p for _, q, p in chunk)
        f_lo, f_hi = C.FREIGHT_COST_PCT_OF_VALUE[mode]
        freight = round(value * self.rng.uniform(f_lo, f_hi), 2)

        # status relative to SIM_NOW
        if actual <= C.SIM_NOW:
            status, actual_out = "delivered", actual
            entry_out, clearance_out = entry, clearance
        elif entry and entry <= C.SIM_NOW < clearance:
            status, actual_out = "customs_hold", None
            entry_out, clearance_out = entry, None
        elif ship <= C.SIM_NOW:
            status, actual_out = "in_transit", None
            entry_out = entry if (entry and entry <= C.SIM_NOW) else None
            clearance_out = None
        else:
            status, actual_out, entry_out, clearance_out = "preparing", None, None, None
        year = (ship if ship <= C.SIM_NOW else po["order"]).year
        shp_id = self._add("shipments", (
            self._ref("SHP", year), po_id, dest_site, self._carrier(mode), mode,
            ship if ship <= C.SIM_NOW else None, eta, actual_out,
            requires_customs, entry_out, clearance_out, freight,
            po["currency"], status))
        for pol_id, qty, _price in chunk:
            self._add("shipment_lines", (shp_id, pol_id, qty))
        if status == "delivered":
            po["delivered_dates"].append(actual)
            year_r = actual.year
            qc = self._weighted(C.QC_WEIGHTS)
            self._add("goods_receipts", (
                self._ref("GRN", year_r), shp_id, actual + DAY * self.rng.randint(0, 2),
                dest_site, qc, None))
        else:
            po["delivered_dates"].append(None)

    def _carrier(self, mode: str) -> str:
        pool = {
            "road": ["TransMed Logistics", "Sahel Freight", "Route Sud Express"],
            "sea": ["MedShip Lines", "Carthage Maritime", "Tyrrhenian Cargo"],
            "air": ["AeroFret Nord", "MedAir Cargo"],
            "multimodal": ["GlobalTrans MENA", "Two Seas Logistics"],
        }[mode]
        return self.rng.choice(pool)

    def _spawn_payments(self, po_id: int, sp: dict) -> None:
        po = self.po_info[po_id]
        pattern = self.rng.choices([p for p, _ in C.PAYMENT_PATTERNS],
                                   weights=[w for _, w in C.PAYMENT_PATTERNS])[0]
        delivered = [d for d in po["delivered_dates"] if d]
        last_delivery = max(delivered) if delivered else None
        anchor_end = (last_delivery or po["promised"]) + DAY * self._supplier_terms(po["supplier_id"])
        for i, share in enumerate(pattern):
            if len(pattern) == 1:
                due = anchor_end
            elif i == 0:
                due = po["order"] + DAY * 7
            elif i == len(pattern) - 1:
                due = anchor_end
            else:
                due = po["order"] + (anchor_end - po["order"]) // 2
            amount = round(po["total"] * share, 2)
            if amount <= 0:
                continue
            method = self.rows["suppliers"][po["supplier_id"] - 1][5]
            paid, status = None, "scheduled"
            if due <= C.SIM_NOW:
                if self.rng.random() < C.PAY_ON_TIME_RATE:
                    paid, status = due - DAY * self.rng.randint(0, 5), "paid"
                else:
                    late = due + DAY * max(1, round(self._tri(C.PAY_LATE_DAYS)))
                    if late <= C.SIM_NOW:
                        paid, status = late, "paid"
                    else:
                        status = "overdue"
            year = due.year
            self._add("payments", (
                self._ref("PAY", year), po_id, amount, po["currency"], method,
                due, paid, status))

    def _supplier_terms(self, supplier_id: int) -> int:
        return self.rows["suppliers"][supplier_id - 1][4]

    def _finalize_po_status(self, po_id: int) -> None:
        po = self.po_info[po_id]
        n = len(po["delivered_dates"])
        done = len([d for d in po["delivered_dates"] if d])
        if done == n and n > 0:
            last = max(d for d in po["delivered_dates"] if d)
            status = "closed" if (C.SIM_NOW - last).days > 60 else "delivered"
            # BoQ fulfilled
        elif done > 0:
            status = "partially_delivered"
        else:
            status = "confirmed" if (C.SIM_NOW - po["order"]).days > 10 else "issued"
        row = list(self.rows["purchase_orders"][po_id - 1])
        row[8] = po["total"]
        row[9] = status
        self.rows["purchase_orders"][po_id - 1] = tuple(row)
        if status in ("delivered", "closed"):
            rfq_id = row[3]
            boq_id = self.rows["rfqs"][rfq_id - 1][1]
            self._boq_set_status(boq_id, "fulfilled")

    # -------------------------------------------------------- injected story 4
    def apply_overbudget_story(self) -> int | None:
        """Scale one project's PO prices so spend ≈ 110% of contract value."""
        candidates = [
            (pid, p) for pid, p in self.project_info.items()
            if p["status"] == "completed" and p["scopes"][1]
            and len(p["po_ids"]) >= 4 and 0 < p["spend_tnd"] < p["value_tnd"]
            and 500_000 <= p["value_tnd"] <= 12_000_000
        ]
        if not candidates:
            return None
        pid, proj = max(candidates, key=lambda t: t[1]["spend_tnd"] / t[1]["value_tnd"])
        factor = (C.STORY_OVERBUDGET_TARGET_RATIO * proj["value_tnd"]) / proj["spend_tnd"]
        for po_id in proj["po_ids"]:
            po = self.po_info[po_id]
            new_lines = []
            for pol_id, qty, price in po["lines"]:
                new_price = round(price * factor, 2)
                row = list(self.rows["po_lines"][pol_id - 1]); row[3] = new_price
                self.rows["po_lines"][pol_id - 1] = tuple(row)
                new_lines.append((pol_id, qty, new_price))
            po["lines"] = new_lines
            old_total = po["total"]
            po["total"] = round(sum(q * p for _, q, p in new_lines), 2)
            row = list(self.rows["purchase_orders"][po_id - 1]); row[8] = po["total"]
            self.rows["purchase_orders"][po_id - 1] = tuple(row)
            if old_total > 0:
                scale = po["total"] / old_total
                for i, pay in enumerate(self.rows["payments"]):
                    if pay[1] == po_id:
                        r = list(pay); r[2] = round(r[2] * scale, 2)
                        self.rows["payments"][i] = tuple(r)
        proj["spend_tnd"] = sum(
            self.po_info[p]["total"] * C.FX_TO_TND[self.po_info[p]["currency"]]
            for p in proj["po_ids"])
        return pid

    # --------------------------------------------------------------- assets
    def simulate_assets(self) -> None:
        n_by_cat: dict[str, int] = {}
        for _ in range(C.ASSET_COUNT):
            cat = self._weighted(C.ASSET_CATEGORY_WEIGHTS)
            n_by_cat[cat] = n_by_cat.get(cat, 0) + 1
            i = n_by_cat[cat]
            acq = self._date_between(*C.ASSET_ACQ_WINDOW)
            cost = round(self.rng.uniform(*C.ASSET_COST_RANGE[cat]), 2)
            condition = self._weighted(C.ASSET_CONDITION_WEIGHTS)
            if condition in ("stolen", "lost"):
                status = "retired"
            elif condition == "under_repair":
                status = "under_maintenance"
            else:
                status = self.rng.choices(["available", "assigned"], weights=[45, 55])[0]
            name = f"{cat.replace('_', ' ').title()} #{i:02d}"
            asset_id = self._add("assets", (
                f"AST-{cat[:3].upper()}-{i:03d}", name, cat, acq, cost, "TND",
                condition, status))
            self._spawn_assignments(asset_id, cat, acq, status)
            self._spawn_maintenance(asset_id, cat, acq, condition)

    def _spawn_assignments(self, asset_id, cat, acq, status) -> None:
        if cat in ("it_equipment", "furniture"):
            return
        projects = [(pid, p) for pid, p in self.project_info.items()
                    if p["start"] >= acq and p["status"] != "planning"]
        self.rng.shuffle(projects)
        n = self.rng.randint(0, min(4, len(projects)))
        used = sorted(projects[:n], key=lambda t: t[1]["start"])
        last_end = acq
        for pid, p in used:
            s = max(p["start"], last_end + DAY)
            e_limit = min(p["end"], C.SIM_NOW)
            if s >= e_limit:
                continue
            e = self._date_between(s + DAY, e_limit)
            open_now = (status == "assigned" and p["status"] == "active"
                        and self.rng.random() < 0.5)
            self._add("asset_assignments", (asset_id, pid, s, None if open_now else e))
            if open_now:
                break
            last_end = e

    def _spawn_maintenance(self, asset_id, cat, acq, condition) -> None:
        lo, hi = C.MAINTENANCE_EVENTS_PER_ASSET
        age_years = max(0.2, (C.SIM_NOW - acq).days / 365.25)
        n = min(hi, self._poisson(min(hi, age_years * (1.2 if condition in ("damaged", "under_repair") else 0.6))))
        for _ in range(n):
            when = self._date_between(acq, C.SIM_NOW)
            etype = self.rng.choices(["preventive", "corrective"], weights=[55, 45])[0]
            base = self.rows["assets"][asset_id - 1][4]
            cost = round(float(base) * self.rng.uniform(0.005, 0.06), 2)
            downtime = 0 if etype == "preventive" else self.rng.randint(1, 20)
            self._add("maintenance_events", (
                asset_id, etype, when, cost, "TND", downtime,
                f"{etype.title()} intervention on {self.rows['assets'][asset_id-1][1]}"))

    # ------------------------------------------------------------------- run
    def run(self) -> dict[str, list[tuple]]:
        self.build_reference()
        self.simulate_commercial()
        self.simulate_procurement()
        overbudget_pid = self.apply_overbudget_story()
        self.simulate_assets()
        self._overbudget_project_id = overbudget_pid
        return self.rows
