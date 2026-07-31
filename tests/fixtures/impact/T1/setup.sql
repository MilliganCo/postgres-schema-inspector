DROP SCHEMA IF EXISTS impact_t1 CASCADE;
CREATE SCHEMA impact_t1;
CREATE TABLE impact_t1.t (
  id int PRIMARY KEY,
  payload integer NOT NULL
);
CREATE INDEX impact_t1_payload_idx ON impact_t1.t (payload);
