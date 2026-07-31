DROP SCHEMA IF EXISTS impact_d2 CASCADE;
CREATE SCHEMA impact_d2;
CREATE TABLE impact_d2.t (
  id int PRIMARY KEY,
  secret text
);
CREATE VIEW impact_d2.v AS SELECT id, secret FROM impact_d2.t;
