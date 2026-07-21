-- =============================================================================
-- SupplyScope — reactivity layer (ADR-004)
-- Statement-level AFTER triggers on every erp table emit a lightweight
-- NOTIFY carrying only the table name (payloads stay far below the 8 KB
-- NOTIFY limit; the engine decides what to re-query). Applied dynamically so
-- future erp tables are covered automatically.
-- =============================================================================

CREATE OR REPLACE FUNCTION erp.notify_data_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('erp_data_change',
                      json_build_object('table', TG_TABLE_NAME)::text);
    RETURN NULL;   -- AFTER statement trigger: return value ignored
END $$;

DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'erp'
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_notify_change
             AFTER INSERT OR UPDATE OR DELETE ON erp.%I
             FOR EACH STATEMENT EXECUTE FUNCTION erp.notify_data_change()', t);
    END LOOP;
END $$;
