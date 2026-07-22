-- pginspect Foundation CI / local integration fixture
-- Spec: design §12 (CI write enforcement / safety probes); plan Task 15 §12.9 roles.
--
-- Purpose
-- -------
-- Throwaway PostgreSQL only. Creates:
--   * roles  pginspect_test (subject) and pginspect_admin (observer)
--   * schema pginspect_probe
--   * table  pginspect_probe.write_probe  (persistent sentinel row)
--
-- Subject role receives REAL write grants (INSERT/UPDATE/DELETE/TRUNCATE/CREATE)
-- so safety probes fail with SQLSTATE 25006 (read_only_sql_transaction), never 42501
-- (insufficient_privilege). Observer verifies the sentinel row is unchanged after each probe.
--
-- Passwords below are disposable CI fixtures — not production secrets (A-14 canary-safe).
-- Apply as a superuser (e.g. postgres) from PGINSPECT_TEST_DSN before integration/safety runs.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pginspect_admin') THEN
    CREATE ROLE pginspect_admin LOGIN PASSWORD 'pginspect_admin_ci';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pginspect_test') THEN
    CREATE ROLE pginspect_test LOGIN PASSWORD 'pginspect_test_ci';
  END IF;
END
$$;

GRANT pginspect_admin TO CURRENT_USER;
GRANT pginspect_test TO CURRENT_USER;

CREATE SCHEMA IF NOT EXISTS pginspect_probe AUTHORIZATION pginspect_admin;

CREATE TABLE IF NOT EXISTS pginspect_probe.write_probe (
  id integer PRIMARY KEY,
  payload text NOT NULL
);

-- Sentinel row observed by safety suite after every adversarial statement.
INSERT INTO pginspect_probe.write_probe (id, payload)
VALUES (1, 'sentinel-unchanged')
ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload;

REVOKE ALL ON SCHEMA pginspect_probe FROM PUBLIC;
REVOKE ALL ON TABLE pginspect_probe.write_probe FROM PUBLIC;

GRANT USAGE ON SCHEMA pginspect_probe TO pginspect_test;
GRANT USAGE ON SCHEMA pginspect_probe TO pginspect_admin;

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
  ON TABLE pginspect_probe.write_probe TO pginspect_test;
GRANT CREATE ON SCHEMA pginspect_probe TO pginspect_test;

GRANT SELECT ON TABLE pginspect_probe.write_probe TO pginspect_admin;

-- Allow subject/observer to CONNECT to the current database.
DO $$
DECLARE
  dbname text := current_database();
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO pginspect_test', dbname);
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO pginspect_admin', dbname);
END
$$;
