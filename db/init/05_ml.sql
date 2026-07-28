-- =============================================================================
-- SupplyScope — schema `ml` : machine-learning registry and predictions.
-- Design principle: MODEL OUTPUTS ARE FIRST-CLASS QUERYABLE DATA.
--   * agent_reader gets SELECT here (unlike `app`), so the NL agent can answer
--     risk questions through its ordinary SQL path — no bespoke ML plumbing.
--   * the predictions table carries the same NOTIFY triggers as erp tables,
--     so charts built on model outputs refresh live like any other chart.
-- =============================================================================
CREATE SCHEMA ml;
GRANT USAGE ON SCHEMA ml TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA ml GRANT SELECT ON TABLES TO agent_reader;

CREATE TABLE ml.models (
    model_id    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name  text NOT NULL,             -- e.g. 'delivery_risk'
    task        text NOT NULL CHECK (task IN ('classification','regression')),
    algo        text NOT NULL,             -- winning algorithm of this version
    version     integer NOT NULL,
    trained_at  timestamptz NOT NULL DEFAULT now(),
    split_date  date,                      -- time-based split boundary
    train_rows  integer,
    test_rows   integer,
    metrics     jsonb,                     -- winning model's test metrics
    comparison  jsonb,                     -- full baseline-ladder comparison
    feature_importance jsonb,              -- permutation importance (test set)
    artifact_path text,
    is_active   boolean NOT NULL DEFAULT false,
    UNIQUE (model_name, version)
);
COMMENT ON TABLE ml.models IS
  'Registry of trained ML models: versions, time-based evaluation metrics, baseline comparisons (logistic regression vs random forest vs multilayer perceptron), and permutation feature importances.';

CREATE TABLE ml.delivery_risk (
    prediction_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_id   integer NOT NULL,
    shipment_ref  text NOT NULL,
    po_id         integer NOT NULL,
    po_number     text NOT NULL,
    project_code  text,
    supplier_name text NOT NULL,
    promised_delivery_date date,
    status        text,
    probability   numeric(5,4) NOT NULL CHECK (probability BETWEEN 0 AND 1),
    risk_band     text NOT NULL CHECK (risk_band IN ('high','medium','low')),
    model_version integer NOT NULL,
    scored_at     timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE ml.delivery_risk IS
  'Late-delivery risk predictions for OPEN (undelivered) shipments, produced by the active delivery_risk model. probability = predicted chance the shipment misses its promised date; risk_band: high >= 0.7, medium >= 0.4, low < 0.4. Refreshed by each batch scoring run; join erp.purchase_orders/erp.shipments via po_id/shipment_id for detail.';
COMMENT ON COLUMN ml.delivery_risk.probability IS 'Model-estimated probability of late delivery (0..1).';

-- Reactivity: predictions participate in the live-refresh mechanism
CREATE TRIGGER trg_notify_change
AFTER INSERT OR UPDATE OR DELETE ON ml.delivery_risk
FOR EACH STATEMENT EXECUTE FUNCTION erp.notify_data_change();
CREATE TRIGGER trg_notify_change
AFTER INSERT OR UPDATE OR DELETE ON ml.models
FOR EACH STATEMENT EXECUTE FUNCTION erp.notify_data_change();
