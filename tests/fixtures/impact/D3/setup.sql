DROP SCHEMA IF EXISTS impact_d3 CASCADE;
CREATE SCHEMA impact_d3;
CREATE TABLE impact_d3.t (
  id int PRIMARY KEY,
  secret text
);
CREATE VIEW impact_d3.v AS SELECT id, secret FROM impact_d3.t;
