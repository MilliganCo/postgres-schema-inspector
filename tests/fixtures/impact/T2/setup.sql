DROP SCHEMA IF EXISTS impact_t2 CASCADE;
CREATE SCHEMA impact_t2;
CREATE TABLE impact_t2.t (
  id int PRIMARY KEY,
  label text NOT NULL
);
CREATE INDEX impact_t2_label_idx ON impact_t2.t (label);
