DROP SCHEMA IF EXISTS impact_s2_i CASCADE;
CREATE SCHEMA impact_s2_i;
CREATE TABLE impact_s2_i.parent (id int PRIMARY KEY, payload int);
CREATE TABLE impact_s2_i.child () INHERITS (impact_s2_i.parent);
