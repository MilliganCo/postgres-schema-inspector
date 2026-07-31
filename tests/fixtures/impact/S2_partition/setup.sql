DROP SCHEMA IF EXISTS impact_s2_p CASCADE;
CREATE SCHEMA impact_s2_p;
CREATE TABLE impact_s2_p.t (id int NOT NULL, payload int) PARTITION BY RANGE (id);
CREATE TABLE impact_s2_p.t_p1 PARTITION OF impact_s2_p.t FOR VALUES FROM (0) TO (1000);
