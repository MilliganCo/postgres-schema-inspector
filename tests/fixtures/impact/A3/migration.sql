ALTER TABLE impact_a3.t
  ADD COLUMN seen_at timestamptz DEFAULT pg_catalog.clock_timestamp();
