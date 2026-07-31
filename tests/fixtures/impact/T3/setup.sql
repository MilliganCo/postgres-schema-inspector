DROP SCHEMA IF EXISTS impact_t3 CASCADE;
CREATE SCHEMA impact_t3;
CREATE TABLE impact_t3.t (
  id int PRIMARY KEY,
  payload text NOT NULL
);
