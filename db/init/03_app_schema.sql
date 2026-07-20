-- =============================================================================
-- SupplyScope — schema `app` : application data (users, conversations,
-- messages, saved charts). The agent_reader role has NO access here (ADR-006).
-- =============================================================================
SET search_path TO app, public;

CREATE TABLE app.users (
    user_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    display_name  text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE app.users IS 'Application accounts (business users of the assistant).';

CREATE TABLE app.conversations (
    conversation_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         integer NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
    title           text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_conversations_user ON app.conversations(user_id, updated_at DESC);

CREATE TABLE app.messages (
    message_id      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id integer NOT NULL REFERENCES app.conversations(conversation_id) ON DELETE CASCADE,
    role            text NOT NULL CHECK (role IN ('user','assistant')),
    content         text NOT NULL,
    sql_query       text,
    chart           jsonb,
    result_meta     jsonb,   -- {columns, preview_rows, row_count, truncated, duration_ms, attempts, failed}
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_conversation ON app.messages(conversation_id, message_id);
COMMENT ON COLUMN app.messages.result_meta IS
  'Execution metadata + a bounded preview of result rows for UI redisplay; full data is re-obtained by re-running sql_query.';

CREATE TABLE app.saved_charts (
    chart_id    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     integer NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
    title       text NOT NULL,
    sql_query   text NOT NULL,
    chart_spec  jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_saved_charts_user ON app.saved_charts(user_id);
COMMENT ON TABLE app.saved_charts IS
  'Pinned visualizations = (sql_query, chart_spec) pairs. The Phase-4 reactivity engine re-executes sql_query on data changes and pushes fresh rows to subscribed clients.';
