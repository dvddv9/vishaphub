-- Teams, people, keys, runs and the audit trail.
--
-- Applied by `python -m hub.admin migrate`, as the owner of the database. The server never runs
-- this: it connects as vishap_hub_app, which can reach only what is granted at the bottom.
--
--   * runs and audit_log carry a team_id and a row-level-security policy on it, so a query that
--     forgets its WHERE team_id = ... still sees one team only. The role is NOSUPERUSER NOBYPASSRLS.
--   * teams, users and api_keys are not granted to the server at all. It finds out who a key
--     belongs to through hub_authenticate(), which returns that one answer and nothing else.
--   * the server can add to audit_log and read its own team's rows; it cannot change or delete one.
--   * expired runs are removed by hub_purge_expired(), the only way the server deletes across teams.

CREATE TABLE teams (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text NOT NULL UNIQUE,
    retention_days integer CHECK (retention_days IS NULL OR retention_days BETWEEN 1 AND 3650),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     uuid NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
    name        text NOT NULL,
    role        text NOT NULL CHECK (role IN ('owner', 'member', 'viewer')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz,
    UNIQUE (team_id, name)
);

CREATE TABLE api_keys (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    prefix       text NOT NULL,
    key_hash     text NOT NULL UNIQUE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    revoked_at   timestamptz,
    last_used_at timestamptz
);

CREATE TABLE runs (
    team_id    uuid NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
    run_id     text NOT NULL,
    creators   uuid[] NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    verdict    text,
    ok         boolean,
    plan       jsonb,
    summary    text,
    result     jsonb NOT NULL,
    cost       jsonb,
    PRIMARY KEY (team_id, run_id)
);
CREATE INDEX runs_team_created ON runs (team_id, created_at DESC);
CREATE INDEX runs_expiry ON runs (expires_at);

-- No foreign key on team_id: deleting a team must not delete its audit trail unless the operator
-- asks for that explicitly (hub.admin purge-team --include-audit).
CREATE TABLE audit_log (
    id      bigserial PRIMARY KEY,
    at      timestamptz NOT NULL DEFAULT now(),
    team_id uuid NOT NULL,
    user_id uuid,
    key_id  uuid,
    action  text NOT NULL,
    target  text,
    ip      text,
    detail  jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX audit_team_at ON audit_log (team_id, id DESC);

-- ---- the server's role -----------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vishap_hub_app') THEN
        CREATE ROLE vishap_hub_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO vishap_hub_app;

ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY team_isolation ON runs
    USING (team_id = NULLIF(current_setting('app.current_team', true), '')::uuid)
    WITH CHECK (team_id = NULLIF(current_setting('app.current_team', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON runs TO vishap_hub_app;

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY team_isolation ON audit_log
    USING (team_id = NULLIF(current_setting('app.current_team', true), '')::uuid)
    WITH CHECK (team_id = NULLIF(current_setting('app.current_team', true), '')::uuid);
GRANT SELECT, INSERT ON audit_log TO vishap_hub_app;
GRANT USAGE ON SEQUENCE audit_log_id_seq TO vishap_hub_app;

-- Who does this key belong to? One answer, no table access. Also stamps last_used_at.
CREATE FUNCTION hub_authenticate(p_hash text)
RETURNS TABLE (key_id uuid, user_id uuid, team_id uuid, role text, user_name text, retention_days integer)
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    WITH k AS (
        UPDATE api_keys SET last_used_at = now()
        WHERE key_hash = p_hash AND revoked_at IS NULL
        RETURNING id, api_keys.user_id
    )
    SELECT k.id, u.id, u.team_id, u.role, u.name, t.retention_days
    FROM k
    JOIN users u ON u.id = k.user_id AND u.disabled_at IS NULL
    JOIN teams t ON t.id = u.team_id;
$$;
REVOKE ALL ON FUNCTION hub_authenticate(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hub_authenticate(text) TO vishap_hub_app;

-- Retention: remove every expired run, whatever its team, and leave one audit row per team.
CREATE FUNCTION hub_purge_expired()
RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    WITH gone AS (
        DELETE FROM runs WHERE expires_at <= now() RETURNING team_id
    ), logged AS (
        INSERT INTO audit_log (team_id, action, detail)
        SELECT team_id, 'run.expired', jsonb_build_object('count', count(*)) FROM gone GROUP BY team_id
        RETURNING 1
    )
    SELECT count(*)::integer FROM gone;
$$;
REVOKE ALL ON FUNCTION hub_purge_expired() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hub_purge_expired() TO vishap_hub_app;
