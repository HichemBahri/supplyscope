-- =============================================================================
-- SupplyScope — schema `erp` v2 : mock ERP of an EPC contractor (GETS-like)
-- File: db/init/02_erp_schema.sql
-- Runs automatically after 01-schemas.sql on first container start.
--
-- v2 changes (from interviews with two GETS IT-team members):
--  * material_requisitions/mr_lines renamed to boqs/boq_lines (Bill of
--    Quantities — the company's actual vocabulary), with explicit
--    Engineering-validation fields (Engineering confirms every BoQ, even on
--    procurement-only projects).
--  * Contract scope is a combination of Engineering / Procurement /
--    Construction flags on tenders and projects (offers may cover any subset).
--  * supplier_quotations carry TBE (Technical Bid Evaluation, by Engineering)
--    and CBE (Commercial Bid Evaluation, by Supply Chain) scores.
--  * suppliers carry a preferred payment method; new `payments` table tracks
--    PO payment schedule/settlement (Finance involvement).
--  * assets extended to general company equipment (IT, furniture, tooling)
--    with a physical `condition` register (good/damaged/stolen/...).
--
-- Department ownership convention (encoded in workflow, not in a table):
--   Tendering  → tenders, proposals (client AWARD = proposal won)
--   Engineering→ BoQ validation, TBE
--   SupplyChain→ RFQs, CBE, POs, shipments, receipts, asset register
--   Finance    → payments
--
-- Design notes
--  * Business keys (codes/refs) are UNIQUE TEXT; surrogate PKs are identities.
--  * Statuses are TEXT + CHECK (readable by schema introspection; easy to evolve).
--  * Every table/column that matters carries a COMMENT: the Phase-2 agent
--    discovers the schema by introspection, so comments double as
--    always-in-sync documentation for the LLM.
--  * Transactional tables carry updated_at maintained by a trigger — later
--    reused by the Phase-4 reactivity engine.
--  * Money: NUMERIC(14,2) + ISO currency code (TND/EUR/USD/LYD).
-- =============================================================================

SET search_path TO erp, public;

-- -----------------------------------------------------------------------------
-- Housekeeping: auto-maintained updated_at
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION erp.touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

-- =============================================================================
-- CLUSTER 1 — REFERENCE DATA
-- =============================================================================

CREATE TABLE erp.clients (
    client_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_code   text NOT NULL UNIQUE,
    name          text NOT NULL,
    country       text NOT NULL,
    sector        text NOT NULL CHECK (sector IN
                    ('oil_gas','power','infrastructure','industrial','government')),
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE erp.clients IS
  'Companies that award tenders/projects to the EPC contractor (e.g. field operators, national oil companies, international EPC majors).';
COMMENT ON COLUMN erp.clients.sector IS 'Client industry sector.';

CREATE TABLE erp.suppliers (
    supplier_id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_code            text NOT NULL UNIQUE,
    name                     text NOT NULL,
    country                  text NOT NULL,
    city                     text,
    payment_terms_days       integer NOT NULL DEFAULT 60 CHECK (payment_terms_days >= 0),
    preferred_payment_method text NOT NULL DEFAULT 'bank_transfer' CHECK (preferred_payment_method IN
                              ('bank_transfer','letter_of_credit','check','promissory_note')),
    is_active                boolean NOT NULL DEFAULT true,
    created_at               timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE erp.suppliers IS
  'Vendors the contractor buys materials/equipment from. country=Tunisie means local sourcing; other countries mean import (longer lead times, customs).';
COMMENT ON COLUMN erp.suppliers.preferred_payment_method IS
  'How this supplier prefers to be paid; actual PO payments are recorded in erp.payments. letter_of_credit is typical for foreign suppliers.';

CREATE TABLE erp.materials (
    material_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    material_code   text NOT NULL UNIQUE,
    name            text NOT NULL,
    category        text NOT NULL CHECK (category IN
                     ('piping','valves','steel','electrical','instrumentation',
                      'coatings','welding_consumables','mechanical_equipment','safety')),
    unit            text NOT NULL CHECK (unit IN
                     ('piece','m','kg','ton','liter','set','drum','sheet')),
    ref_unit_price  numeric(14,2) NOT NULL CHECK (ref_unit_price >= 0),
    currency        text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD'))
);
COMMENT ON TABLE erp.materials IS
  'Material/equipment catalog for project procurement. ref_unit_price is an indicative catalog price; actual transaction prices live in po_lines.unit_price.';

CREATE TABLE erp.sites (
    site_id    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_code  text NOT NULL UNIQUE,
    name       text NOT NULL,
    country    text NOT NULL,
    region     text,
    site_type  text NOT NULL CHECK (site_type IN
                ('fabrication_shop','field_site','warehouse','office'))
);
COMMENT ON TABLE erp.sites IS
  'Physical locations: the Sfax fabrication shop and warehouse, plus client field sites (Tunisia and Libya). Shipments to Libyan field sites cross a border and require customs clearance.';

-- =============================================================================
-- CLUSTER 2 — TENDERING (Tendering department)
-- =============================================================================

CREATE TABLE erp.tenders (
    tender_id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tender_ref          text NOT NULL UNIQUE,
    client_id           integer NOT NULL REFERENCES erp.clients(client_id),
    title               text NOT NULL,
    scope_engineering   boolean NOT NULL DEFAULT false,
    scope_procurement   boolean NOT NULL DEFAULT false,
    scope_construction  boolean NOT NULL DEFAULT false,
    issue_date          date NOT NULL,
    submission_deadline date NOT NULL,
    estimated_value     numeric(14,2) CHECK (estimated_value >= 0),
    currency            text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    status              text NOT NULL DEFAULT 'open' CHECK (status IN
                         ('open','awarded','cancelled')),
    CHECK (submission_deadline >= issue_date),
    CHECK (scope_engineering OR scope_procurement OR scope_construction)
);
COMMENT ON TABLE erp.tenders IS
  'Calls for tender issued by clients, which the contractor may bid on (Tendering department scope). The requested scope is any combination of Engineering / Procurement / Construction (E, P, C, EP, PC, EPC...).';
COMMENT ON COLUMN erp.tenders.scope_procurement IS
  'True if the tender includes a procurement (material supply) scope. A procurement-only tender means the contractor is hired just to buy and deliver materials.';

CREATE TABLE erp.proposals (
    proposal_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tender_id       integer NOT NULL REFERENCES erp.tenders(tender_id),
    submitted_date  date,
    proposed_value  numeric(14,2) CHECK (proposed_value >= 0),
    currency        text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    status          text NOT NULL DEFAULT 'draft' CHECK (status IN
                     ('draft','submitted','won','lost','withdrawn')),
    decision_date   date,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE erp.proposals IS
  'The contractor''s bids in response to tenders, prepared by Tendering with Engineering input. status=won means the client AWARDED the contract to the contractor (decision_date = award date); the won proposal becomes a project (projects.proposal_id) and is handed off to Supply Chain.';
CREATE TRIGGER trg_proposals_touch BEFORE UPDATE ON erp.proposals
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

-- =============================================================================
-- CLUSTER 3 — PROJECTS
-- =============================================================================

CREATE TABLE erp.projects (
    project_id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_code       text NOT NULL UNIQUE,
    name               text NOT NULL,
    client_id          integer NOT NULL REFERENCES erp.clients(client_id),
    site_id            integer NOT NULL REFERENCES erp.sites(site_id),
    proposal_id        integer REFERENCES erp.proposals(proposal_id),
    scope_engineering  boolean NOT NULL DEFAULT false,
    scope_procurement  boolean NOT NULL DEFAULT false,
    scope_construction boolean NOT NULL DEFAULT false,
    contract_value     numeric(14,2) NOT NULL CHECK (contract_value >= 0),
    currency           text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    start_date         date NOT NULL,
    planned_end_date   date NOT NULL,
    actual_end_date    date,
    status             text NOT NULL DEFAULT 'planning' CHECK (status IN
                        ('planning','active','on_hold','completed','cancelled')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (planned_end_date >= start_date),
    CHECK (scope_engineering OR scope_procurement OR scope_construction)
);
COMMENT ON TABLE erp.projects IS
  'Execution projects (codes like JI2047/SOR2352), created from won (awarded) proposals. Scope flags say which of Engineering / Procurement / Construction the contract covers. Procurement documents (BoQs, POs) always belong to a project.';
COMMENT ON COLUMN erp.projects.contract_value IS 'Contract value with the client; compare with total procurement spend for margin-erosion analyses.';
CREATE TRIGGER trg_projects_touch BEFORE UPDATE ON erp.projects
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

-- =============================================================================
-- CLUSTER 4 — PROCUREMENT CHAIN (Supply Chain department, with Engineering
--             validation/TBE and Finance payments)
--   boqs → rfqs → supplier_quotations (TBE/CBE) → purchase_orders
--   → po_lines → shipments (+lines) → goods_receipts ; payments per PO
-- =============================================================================

CREATE TABLE erp.boqs (
    boq_id                 integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    boq_ref                text NOT NULL UNIQUE,
    project_id             integer NOT NULL REFERENCES erp.projects(project_id),
    discipline             text NOT NULL CHECK (discipline IN
                            ('civil','mechanical','piping','electrical','instrumentation','hse','general')),
    request_date           date NOT NULL,
    needed_by_date         date NOT NULL,
    engineering_validated  boolean NOT NULL DEFAULT false,
    validation_date        date,
    status                 text NOT NULL DEFAULT 'draft' CHECK (status IN
                            ('draft','approved','rfq_issued','fulfilled','cancelled')),
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CHECK (needed_by_date >= request_date),
    CHECK (NOT engineering_validated OR validation_date IS NOT NULL),
    CHECK (validation_date IS NULL OR validation_date >= request_date)
);
COMMENT ON TABLE erp.boqs IS
  'Bill of Quantities (BoQ): the itemized list of materials needed for a project. Always validated by the Engineering department (engineering_validated/validation_date) before Supply Chain may source it — even on procurement-only projects. Start of the procurement chain.';
COMMENT ON COLUMN erp.boqs.engineering_validated IS
  'True once Engineering has technically confirmed the BoQ; Supply Chain only issues RFQs for validated BoQs.';
CREATE TRIGGER trg_boqs_touch BEFORE UPDATE ON erp.boqs
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

CREATE TABLE erp.boq_lines (
    boq_line_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    boq_id      integer NOT NULL REFERENCES erp.boqs(boq_id) ON DELETE CASCADE,
    material_id integer NOT NULL REFERENCES erp.materials(material_id),
    quantity    numeric(14,3) NOT NULL CHECK (quantity > 0),
    UNIQUE (boq_id, material_id)
);
COMMENT ON TABLE erp.boq_lines IS 'Line items of a Bill of Quantities (material + quantity).';

CREATE TABLE erp.rfqs (
    rfq_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rfq_ref    text NOT NULL UNIQUE,
    boq_id     integer NOT NULL REFERENCES erp.boqs(boq_id),
    issue_date date NOT NULL,
    due_date   date NOT NULL,
    status     text NOT NULL DEFAULT 'issued' CHECK (status IN
                ('issued','quotes_received','awarded','cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (due_date >= issue_date)
);
COMMENT ON TABLE erp.rfqs IS
  'Request For Quotation ("consultation") sent by Supply Chain to several suppliers to source a validated BoQ. status=awarded means a supplier was selected after TBE/CBE evaluation.';
CREATE TRIGGER trg_rfqs_touch BEFORE UPDATE ON erp.rfqs
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

CREATE TABLE erp.supplier_quotations (
    quotation_id    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rfq_id          integer NOT NULL REFERENCES erp.rfqs(rfq_id),
    supplier_id     integer NOT NULL REFERENCES erp.suppliers(supplier_id),
    quote_date      date NOT NULL,
    quoted_total    numeric(14,2) NOT NULL CHECK (quoted_total >= 0),
    currency        text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    lead_time_days  integer NOT NULL CHECK (lead_time_days >= 0),
    tbe_score       numeric(5,2) CHECK (tbe_score BETWEEN 0 AND 100),
    cbe_score       numeric(5,2) CHECK (cbe_score BETWEEN 0 AND 100),
    status          text NOT NULL DEFAULT 'received' CHECK (status IN
                     ('received','selected','rejected')),
    UNIQUE (rfq_id, supplier_id)
);
COMMENT ON TABLE erp.supplier_quotations IS
  'Supplier offers in response to an RFQ (simplified to header level: total price + promised lead time). Each offer is evaluated twice: TBE = Technical Bid Evaluation score (by Engineering; below ~70 is technically disqualified) and CBE = Commercial Bid Evaluation score (by Supply Chain: price, terms, lead time). status=selected means the PO was awarded to this supplier.';
COMMENT ON COLUMN erp.supplier_quotations.tbe_score IS 'Technical Bid Evaluation score 0-100, assessed by Engineering; NULL until evaluated.';
COMMENT ON COLUMN erp.supplier_quotations.cbe_score IS 'Commercial Bid Evaluation score 0-100, assessed by Supply Chain; NULL until evaluated.';

CREATE TABLE erp.purchase_orders (
    po_id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    po_number              text NOT NULL UNIQUE,
    project_id             integer NOT NULL REFERENCES erp.projects(project_id),
    supplier_id            integer NOT NULL REFERENCES erp.suppliers(supplier_id),
    rfq_id                 integer REFERENCES erp.rfqs(rfq_id),
    order_date             date NOT NULL,
    promised_delivery_date date NOT NULL,
    incoterm               text CHECK (incoterm IN ('EXW','FCA','CPT','CIF','DAP','DDP')),
    currency               text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    total_amount           numeric(14,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    status                 text NOT NULL DEFAULT 'draft' CHECK (status IN
                            ('draft','issued','confirmed','partially_delivered',
                             'delivered','closed','cancelled')),
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CHECK (promised_delivery_date >= order_date)
);
COMMENT ON TABLE erp.purchase_orders IS
  'Purchase Order (PO): the contractor''s firm order to the supplier selected after TBE/CBE, for a project. Central table of procurement analytics. total_amount = sum of its po_lines. Payment settlement is tracked in erp.payments.';
COMMENT ON COLUMN erp.purchase_orders.promised_delivery_date IS
  'Contractual delivery date; compare with shipments.actual_delivery_date for the on-time-delivery (OTD) KPI.';
CREATE TRIGGER trg_po_touch BEFORE UPDATE ON erp.purchase_orders
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

CREATE TABLE erp.po_lines (
    po_line_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    po_id       integer NOT NULL REFERENCES erp.purchase_orders(po_id) ON DELETE CASCADE,
    material_id integer NOT NULL REFERENCES erp.materials(material_id),
    quantity    numeric(14,3) NOT NULL CHECK (quantity > 0),
    unit_price  numeric(14,2) NOT NULL CHECK (unit_price >= 0),
    line_total  numeric(14,2) GENERATED ALWAYS AS (round(quantity * unit_price, 2)) STORED,
    UNIQUE (po_id, material_id)
);
COMMENT ON TABLE erp.po_lines IS
  'PO line items. unit_price is the actual transaction price (compare with materials.ref_unit_price for price-variance analyses).';

CREATE TABLE erp.payments (
    payment_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payment_ref text NOT NULL UNIQUE,
    po_id       integer NOT NULL REFERENCES erp.purchase_orders(po_id),
    amount      numeric(14,2) NOT NULL CHECK (amount > 0),
    currency    text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    method      text NOT NULL CHECK (method IN
                 ('bank_transfer','letter_of_credit','check','promissory_note')),
    due_date    date NOT NULL,
    paid_date   date,
    status      text NOT NULL DEFAULT 'scheduled' CHECK (status IN
                 ('scheduled','paid','overdue','cancelled')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (status <> 'paid' OR paid_date IS NOT NULL),
    CHECK (paid_date IS NULL OR status IN ('paid','cancelled'))
);
COMMENT ON TABLE erp.payments IS
  'Payment schedule and settlement of purchase orders (Finance department). A PO may be paid in several installments (advance + on-delivery + retention). status=overdue means due_date has passed without payment; method usually follows suppliers.preferred_payment_method.';
COMMENT ON COLUMN erp.payments.due_date IS 'Contractual payment due date (typically order/delivery date + supplier payment terms).';
CREATE TRIGGER trg_payments_touch BEFORE UPDATE ON erp.payments
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

CREATE TABLE erp.shipments (
    shipment_id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_ref          text NOT NULL UNIQUE,
    po_id                 integer NOT NULL REFERENCES erp.purchase_orders(po_id),
    destination_site_id   integer NOT NULL REFERENCES erp.sites(site_id),
    carrier               text,
    transport_mode        text NOT NULL CHECK (transport_mode IN ('road','sea','air','multimodal')),
    ship_date             date,
    eta_date              date,
    actual_delivery_date  date,
    requires_customs      boolean NOT NULL DEFAULT false,
    customs_entry_date    date,
    customs_clearance_date date,
    freight_cost          numeric(14,2) CHECK (freight_cost >= 0),
    currency              text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    status                text NOT NULL DEFAULT 'preparing' CHECK (status IN
                           ('preparing','in_transit','customs_hold','delivered','cancelled')),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (customs_clearance_date IS NULL OR customs_entry_date IS NULL
           OR customs_clearance_date >= customs_entry_date)
);
COMMENT ON TABLE erp.shipments IS
  'Physical deliveries fulfilling a PO (a PO may be split into several shipments). Cross-border shipments (e.g. Sfax to Libyan field sites) have requires_customs=true; customs_clearance_date - customs_entry_date measures customs delay.';
CREATE TRIGGER trg_shipments_touch BEFORE UPDATE ON erp.shipments
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

CREATE TABLE erp.shipment_lines (
    shipment_line_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_id      integer NOT NULL REFERENCES erp.shipments(shipment_id) ON DELETE CASCADE,
    po_line_id       integer NOT NULL REFERENCES erp.po_lines(po_line_id),
    quantity         numeric(14,3) NOT NULL CHECK (quantity > 0),
    UNIQUE (shipment_id, po_line_id)
);
COMMENT ON TABLE erp.shipment_lines IS
  'Quantities of each PO line carried by a shipment; enables partial deliveries and in-transit quantity analyses.';

CREATE TABLE erp.goods_receipts (
    gr_id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gr_ref       text NOT NULL UNIQUE,
    shipment_id  integer NOT NULL UNIQUE REFERENCES erp.shipments(shipment_id),
    receipt_date date NOT NULL,
    site_id      integer NOT NULL REFERENCES erp.sites(site_id),
    qc_status    text NOT NULL DEFAULT 'pending' CHECK (qc_status IN
                  ('pending','accepted','accepted_with_reserve','rejected')),
    remarks      text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE erp.goods_receipts IS
  'Goods Receipt Note (GRN): formal reception + QC of a delivered shipment at a site/warehouse.';
CREATE TRIGGER trg_gr_touch BEFORE UPDATE ON erp.goods_receipts
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

-- =============================================================================
-- CLUSTER 5 — ASSETS & COMPANY EQUIPMENT (Supply Chain asset register)
-- =============================================================================

CREATE TABLE erp.assets (
    asset_id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_code       text NOT NULL UNIQUE,
    name             text NOT NULL,
    category         text NOT NULL CHECK (category IN
                      ('crane','welding_set','generator','vehicle','test_equipment',
                       'compressor','scaffolding','pump',
                       'it_equipment','furniture','tooling')),
    acquisition_date date NOT NULL,
    acquisition_cost numeric(14,2) NOT NULL CHECK (acquisition_cost >= 0),
    currency         text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    condition        text NOT NULL DEFAULT 'good' CHECK (condition IN
                      ('good','fair','damaged','under_repair','stolen','lost')),
    status           text NOT NULL DEFAULT 'available' CHECK (status IN
                      ('available','assigned','under_maintenance','retired')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE erp.assets IS
  'Company asset register managed by Supply Chain: production equipment (cranes, welding sets, generators...) AND general equipment (IT hardware, furniture, tooling). `condition` is the physical-state register (good/damaged/stolen/...); `status` is the availability lifecycle.';
COMMENT ON COLUMN erp.assets.condition IS 'Physical state as registered by Supply Chain inspections; independent from availability status.';
CREATE TRIGGER trg_assets_touch BEFORE UPDATE ON erp.assets
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

CREATE TABLE erp.asset_assignments (
    assignment_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id      integer NOT NULL REFERENCES erp.assets(asset_id),
    project_id    integer NOT NULL REFERENCES erp.projects(project_id),
    start_date    date NOT NULL,
    end_date      date,
    CHECK (end_date IS NULL OR end_date >= start_date)
);
COMMENT ON TABLE erp.asset_assignments IS
  'Periods during which an asset is mobilized on a project (end_date NULL = currently assigned). Basis of the asset-utilization KPI.';

CREATE TABLE erp.maintenance_events (
    event_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id      integer NOT NULL REFERENCES erp.assets(asset_id),
    event_type    text NOT NULL CHECK (event_type IN ('preventive','corrective')),
    event_date    date NOT NULL,
    cost          numeric(14,2) NOT NULL CHECK (cost >= 0),
    currency      text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    downtime_days integer NOT NULL DEFAULT 0 CHECK (downtime_days >= 0),
    description   text
);
COMMENT ON TABLE erp.maintenance_events IS
  'Maintenance interventions on assets; corrective events with high downtime indicate unreliable equipment.';

-- =============================================================================
-- INDEXES (foreign keys + frequent analytical filters)
-- =============================================================================
CREATE INDEX idx_tenders_client        ON erp.tenders(client_id);
CREATE INDEX idx_tenders_status        ON erp.tenders(status);
CREATE INDEX idx_proposals_tender      ON erp.proposals(tender_id);
CREATE INDEX idx_proposals_status      ON erp.proposals(status);
CREATE INDEX idx_projects_client       ON erp.projects(client_id);
CREATE INDEX idx_projects_site         ON erp.projects(site_id);
CREATE INDEX idx_projects_status       ON erp.projects(status);
CREATE INDEX idx_boqs_project          ON erp.boqs(project_id);
CREATE INDEX idx_boq_lines_boq         ON erp.boq_lines(boq_id);
CREATE INDEX idx_boq_lines_material    ON erp.boq_lines(material_id);
CREATE INDEX idx_rfqs_boq              ON erp.rfqs(boq_id);
CREATE INDEX idx_quotes_rfq            ON erp.supplier_quotations(rfq_id);
CREATE INDEX idx_quotes_supplier       ON erp.supplier_quotations(supplier_id);
CREATE INDEX idx_po_project            ON erp.purchase_orders(project_id);
CREATE INDEX idx_po_supplier           ON erp.purchase_orders(supplier_id);
CREATE INDEX idx_po_status             ON erp.purchase_orders(status);
CREATE INDEX idx_po_order_date         ON erp.purchase_orders(order_date);
CREATE INDEX idx_po_lines_po           ON erp.po_lines(po_id);
CREATE INDEX idx_po_lines_material     ON erp.po_lines(material_id);
CREATE INDEX idx_payments_po           ON erp.payments(po_id);
CREATE INDEX idx_payments_status       ON erp.payments(status);
CREATE INDEX idx_payments_due          ON erp.payments(due_date);
CREATE INDEX idx_shipments_po          ON erp.shipments(po_id);
CREATE INDEX idx_shipments_dest        ON erp.shipments(destination_site_id);
CREATE INDEX idx_shipments_status      ON erp.shipments(status);
CREATE INDEX idx_shipment_lines_shp    ON erp.shipment_lines(shipment_id);
CREATE INDEX idx_shipment_lines_pol    ON erp.shipment_lines(po_line_id);
CREATE INDEX idx_gr_site               ON erp.goods_receipts(site_id);
CREATE INDEX idx_assign_asset          ON erp.asset_assignments(asset_id);
CREATE INDEX idx_assign_project        ON erp.asset_assignments(project_id);
CREATE INDEX idx_maint_asset           ON erp.maintenance_events(asset_id);
CREATE INDEX idx_maint_date            ON erp.maintenance_events(event_date);
