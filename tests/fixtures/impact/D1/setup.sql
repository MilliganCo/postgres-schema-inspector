DROP SCHEMA IF EXISTS impact_d1 CASCADE;
CREATE SCHEMA impact_d1;
CREATE TABLE impact_d1.t (
  id int PRIMARY KEY,
  obsolete text
);
CREATE INDEX impact_d1_obsolete_idx ON impact_d1.t (obsolete);
