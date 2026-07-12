-- =============================================================================
-- SupplyScope — schema `erp` : mock ERP of an EPC contractor (GETS-like)
-- File: db/init/02_erp_schema.sql
-- Runs automatically after 01-schemas.sql on first container start.
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
    supplier_id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_code      text NOT NULL UNIQUE,
    name               text NOT NULL,
    country            text NOT NULL,
    city               text,
    payment_terms_days integer NOT NULL DEFAULT 60 CHECK (payment_terms_days >= 0),
    is_active          boolean NOT NULL DEFAULT true,
    created_at         timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE erp.suppliers IS
  'Vendors the contractor buys materials/equipment from. country=Tunisie means local sourcing; other countries mean import (longer lead times, customs).';

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
  'Material/equipment catalog. ref_unit_price is an indicative catalog price; actual transaction prices live in po_lines.unit_price.';

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
-- CLUSTER 2 — TENDERING
-- =============================================================================

CREATE TABLE erp.tenders (
    tender_id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tender_ref          text NOT NULL UNIQUE,
    client_id           integer NOT NULL REFERENCES erp.clients(client_id),
    title               text NOT NULL,
    project_type        text NOT NULL CHECK (project_type IN
                         ('epc','fabrication','maintenance','manpower_supply')),
    issue_date          date NOT NULL,
    submission_deadline date NOT NULL,
    estimated_value     numeric(14,2) CHECK (estimated_value >= 0),
    currency            text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    status              text NOT NULL DEFAULT 'open' CHECK (status IN
                         ('open','awarded','cancelled')),
    CHECK (submission_deadline >= issue_date)
);
COMMENT ON TABLE erp.tenders IS
  'Calls for tender issued by clients, which the contractor may bid on (Tendering department scope).';

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
  'The contractor''s bids in response to tenders. status won/lost drives the tender win-rate KPI; a won proposal typically becomes a project (projects.proposal_id).';
CREATE TRIGGER trg_proposals_touch BEFORE UPDATE ON erp.proposals
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

-- =============================================================================
-- CLUSTER 3 — PROJECTS
-- =============================================================================

CREATE TABLE erp.projects (
    project_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_code     text NOT NULL UNIQUE,
    name             text NOT NULL,
    client_id        integer NOT NULL REFERENCES erp.clients(client_id),
    site_id          integer NOT NULL REFERENCES erp.sites(site_id),
    proposal_id      integer REFERENCES erp.proposals(proposal_id),
    project_type     text NOT NULL CHECK (project_type IN
                      ('epc','fabrication','maintenance','manpower_supply')),
    contract_value   numeric(14,2) NOT NULL CHECK (contract_value >= 0),
    currency         text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    start_date       date NOT NULL,
    planned_end_date date NOT NULL,
    actual_end_date  date,
    status           text NOT NULL DEFAULT 'planning' CHECK (status IN
                      ('planning','active','on_hold','completed','cancelled')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (planned_end_date >= start_date)
);
COMMENT ON TABLE erp.projects IS
  'Execution projects (codes like JI2047/SOR2352). Procurement documents (requisitions, POs) always belong to a project.';
COMMENT ON COLUMN erp.projects.contract_value IS 'Contract value with the client; compare with total procurement spend for margin-erosion analyses.';
CREATE TRIGGER trg_projects_touch BEFORE UPDATE ON erp.projects
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

-- =============================================================================
-- CLUSTER 4 — PROCUREMENT CHAIN
--   material_requisitions → rfqs → supplier_quotations → purchase_orders
--   → po_lines → shipments (+lines) → goods_receipts
-- =============================================================================

CREATE TABLE erp.material_requisitions (
    mr_id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mr_ref         text NOT NULL UNIQUE,
    project_id     integer NOT NULL REFERENCES erp.projects(project_id),
    discipline     text NOT NULL CHECK (discipline IN
                    ('civil','mechanical','piping','electrical','instrumentation','hse','general')),
    request_date   date NOT NULL,
    needed_by_date date NOT NULL,
    status         text NOT NULL DEFAULT 'draft' CHECK (status IN
                    ('draft','approved','rfq_issued','fulfilled','cancelled')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (needed_by_date >= request_date)
);
COMMENT ON TABLE erp.material_requisitions IS
  'Material Requisition (MR): engineering''s formal request for materials on a project. Start of the procurement chain.';
CREATE TRIGGER trg_mr_touch BEFORE UPDATE ON erp.material_requisitions
    FOR EACH ROW EXECUTE FUNCTION erp.touch_updated_at();

CREATE TABLE erp.mr_lines (
    mr_line_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mr_id       integer NOT NULL REFERENCES erp.material_requisitions(mr_id) ON DELETE CASCADE,
    material_id integer NOT NULL REFERENCES erp.materials(material_id),
    quantity    numeric(14,3) NOT NULL CHECK (quantity > 0),
    UNIQUE (mr_id, material_id)
);
COMMENT ON TABLE erp.mr_lines IS 'Line items of a material requisition (material + quantity).';

CREATE TABLE erp.rfqs (
    rfq_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rfq_ref    text NOT NULL UNIQUE,
    mr_id      integer NOT NULL REFERENCES erp.material_requisitions(mr_id),
    issue_date date NOT NULL,
    due_date   date NOT NULL,
    status     text NOT NULL DEFAULT 'issued' CHECK (status IN
                ('issued','quotes_received','awarded','cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (due_date >= issue_date)
);
COMMENT ON TABLE erp.rfqs IS
  'Request For Quotation sent to several suppliers to fulfil a material requisition.';
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
    status          text NOT NULL DEFAULT 'received' CHECK (status IN
                     ('received','selected','rejected')),
    UNIQUE (rfq_id, supplier_id)
);
COMMENT ON TABLE erp.supplier_quotations IS
  'Supplier offers in response to an RFQ (simplified to header level: total price + promised lead time). The selected quotation leads to a purchase order.';

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
  'Purchase Order (PO): the contractor''s firm order to a supplier for a project. Central table of procurement analytics. total_amount = sum of its po_lines.';
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
-- CLUSTER 5 — ASSETS
-- =============================================================================

CREATE TABLE erp.assets (
    asset_id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_code       text NOT NULL UNIQUE,
    name             text NOT NULL,
    category         text NOT NULL CHECK (category IN
                      ('crane','welding_set','generator','vehicle','test_equipment',
                       'compressor','scaffolding','pump')),
    acquisition_date date NOT NULL,
    acquisition_cost numeric(14,2) NOT NULL CHECK (acquisition_cost >= 0),
    currency         text NOT NULL DEFAULT 'TND' CHECK (currency IN ('TND','EUR','USD','LYD')),
    status           text NOT NULL DEFAULT 'available' CHECK (status IN
                      ('available','assigned','under_maintenance','retired')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE erp.assets IS
  'Contractor-owned equipment (cranes, welding sets, generators...) assignable to projects.';
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
CREATE INDEX idx_mr_project            ON erp.material_requisitions(project_id);
CREATE INDEX idx_mr_lines_mr           ON erp.mr_lines(mr_id);
CREATE INDEX idx_mr_lines_material     ON erp.mr_lines(material_id);
CREATE INDEX idx_rfqs_mr               ON erp.rfqs(mr_id);
CREATE INDEX idx_quotes_rfq            ON erp.supplier_quotations(rfq_id);
CREATE INDEX idx_quotes_supplier       ON erp.supplier_quotations(supplier_id);
CREATE INDEX idx_po_project            ON erp.purchase_orders(project_id);
CREATE INDEX idx_po_supplier           ON erp.purchase_orders(supplier_id);
CREATE INDEX idx_po_status             ON erp.purchase_orders(status);
CREATE INDEX idx_po_order_date         ON erp.purchase_orders(order_date);
CREATE INDEX idx_po_lines_po           ON erp.po_lines(po_id);
CREATE INDEX idx_po_lines_material     ON erp.po_lines(material_id);
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
