-- What each team spends: a ledger, quotas, and a budget that survives a restart.
--
--   * usage has one row per request to a door that spends (run, chat, speak), written BEFORE the work
--     (a reservation, under a lock, so concurrent requests cannot both squeeze under a limit) and filled
--     in when it ends. Tokens the provider reported are kept apart from the estimate made from characters.
--   * a team may override the default quotas: teams.quotas = {"run": {"user": 20, "team": 100}, ...}
--   * deleting a run clears usage.run_id (the id is a link to content that no longer exists); the numbers stay.

ALTER TABLE teams ADD COLUMN quotas jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE usage (
    id              bigserial PRIMARY KEY,
    at              timestamptz NOT NULL DEFAULT now(),
    team_id         uuid NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
    user_id         uuid,
    kind            text NOT NULL CHECK (kind IN ('run', 'chat', 'speak')),
    run_id          text,
    input_chars     integer NOT NULL DEFAULT 0,
    result_chars    integer,
    tokens_in       integer,           -- what the provider reported; NULL when it reported nothing
    tokens_out      integer,
    model_calls     integer NOT NULL DEFAULT 0,
    measured_calls  integer NOT NULL DEFAULT 0,   -- model calls whose tokens the provider reported
    est_tokens_in   integer,           -- an estimate: characters / 4. Never added to the measured columns.
    est_tokens_out  integer,
    outcome         text
);
CREATE INDEX usage_user_kind_at ON usage (team_id, user_id, kind, at DESC);
CREATE INDEX usage_team_kind_at ON usage (team_id, kind, at DESC);

ALTER TABLE usage ENABLE ROW LEVEL SECURITY;
CREATE POLICY team_isolation ON usage
    USING (team_id = NULLIF(current_setting('app.current_team', true), '')::uuid)
    WITH CHECK (team_id = NULLIF(current_setting('app.current_team', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE ON usage TO vishap_hub_app;
GRANT USAGE ON SEQUENCE usage_id_seq TO vishap_hub_app;

-- The server may count across teams for the global budget, and nothing more than a count.
CREATE FUNCTION hub_global_usage(p_kind text, p_hours integer)
RETURNS TABLE (requests bigint, chars bigint, retry_after integer)
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT count(*), coalesce(sum(input_chars), 0)::bigint,
           greatest(1, ceil(extract(epoch FROM (min(at) + make_interval(hours => p_hours) - now()))))::integer
    FROM usage WHERE kind = p_kind AND at > now() - make_interval(hours => p_hours);
$$;
REVOKE ALL ON FUNCTION hub_global_usage(text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hub_global_usage(text, integer) TO vishap_hub_app;

-- Expired runs: the same purge as before, and the usage rows that pointed at them let go of the id.
CREATE OR REPLACE FUNCTION hub_purge_expired()
RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    WITH gone AS (
        DELETE FROM runs WHERE expires_at <= now() RETURNING team_id, run_id
    ), unlinked AS (
        UPDATE usage u SET run_id = NULL FROM gone WHERE u.team_id = gone.team_id AND u.run_id = gone.run_id
        RETURNING 1
    ), logged AS (
        INSERT INTO audit_log (team_id, action, detail)
        SELECT team_id, 'run.expired', jsonb_build_object('count', count(*)) FROM gone GROUP BY team_id
        RETURNING 1
    )
    SELECT count(*)::integer FROM gone;
$$;

-- hub_authenticate now also says what the team's quotas are.
DROP FUNCTION hub_authenticate(text);
CREATE FUNCTION hub_authenticate(p_hash text)
RETURNS TABLE (key_id uuid, user_id uuid, team_id uuid, role text, user_name text, retention_days integer, quotas jsonb)
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    WITH k AS (
        UPDATE api_keys SET last_used_at = now()
        WHERE key_hash = p_hash AND revoked_at IS NULL
        RETURNING id, api_keys.user_id
    )
    SELECT k.id, u.id, u.team_id, u.role, u.name, t.retention_days, t.quotas
    FROM k
    JOIN users u ON u.id = k.user_id AND u.disabled_at IS NULL
    JOIN teams t ON t.id = u.team_id;
$$;
REVOKE ALL ON FUNCTION hub_authenticate(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hub_authenticate(text) TO vishap_hub_app;
