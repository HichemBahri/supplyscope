-- =============================================================================
-- SupplyScope — schema `app` : application data (users, conversations,
-- messages, saved charts). The agent_reader role has NO access here (ADR-006).
-- =============================================================================
SET search_path TO app, public;

CREATE TABLE app.users (
    user_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    first_name    text NOT NULL,
    last_name     text NOT NULL,
    job_title     text NOT NULL,
    department    text NOT NULL DEFAULT 'Supply Chain' CHECK (department IN
                   ('Supply Chain','Tendering','Engineering','Finance','IT','Management')),
    role          text NOT NULL DEFAULT 'analyst' CHECK (role IN ('admin','analyst')),
    avatar        bytea,
    avatar_mime   text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE app.users IS
  'Employee accounts. The first registered user becomes admin (bootstrap); admins manage all accounts. Avatar stored inline (<=2MB) with its MIME type.';

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

-- ---------------------------------------------------------------------------
-- Phase 6.2 — collaborative dashboards
-- ---------------------------------------------------------------------------
CREATE TABLE app.dashboards (
    dashboard_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id     integer NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
    title        text NOT NULL,
    description  text,
    is_shared    boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE app.dashboards IS
  'Named collections of saved charts. is_shared=true (admin action) publishes the dashboard read-only to every employee; everyone may comment on it.';
CREATE INDEX idx_dashboards_owner ON app.dashboards(owner_id);
CREATE INDEX idx_dashboards_shared ON app.dashboards(is_shared) WHERE is_shared;

CREATE TABLE app.dashboard_charts (
    dashboard_id integer NOT NULL REFERENCES app.dashboards(dashboard_id) ON DELETE CASCADE,
    chart_id     integer NOT NULL REFERENCES app.saved_charts(chart_id) ON DELETE CASCADE,
    position     integer NOT NULL DEFAULT 0,
    PRIMARY KEY (dashboard_id, chart_id)
);

CREATE TABLE app.dashboard_comments (
    comment_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dashboard_id integer NOT NULL REFERENCES app.dashboards(dashboard_id) ON DELETE CASCADE,
    user_id      integer NOT NULL REFERENCES app.users(user_id) ON DELETE CASCADE,
    content      text NOT NULL CHECK (length(content) BETWEEN 1 AND 2000),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_comments_dashboard ON app.dashboard_comments(dashboard_id, comment_id);
