DROP SCHEMA IF EXISTS impact_a3 CASCADE;
CREATE SCHEMA impact_a3;
CREATE TABLE impact_a3.t (id int PRIMARY KEY);
CREATE INDEX impact_a3_id_idx ON impact_a3.t (id);
