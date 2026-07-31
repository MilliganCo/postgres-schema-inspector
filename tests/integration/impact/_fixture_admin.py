"""Admin helpers for impact live fixtures (plan Task 12)."""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
from psycopg import sql

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

SUBJECT_ROLE = "pginspect_test"

# Only schemas belonging to committed impact fixtures may be dropped by helpers.
FIXTURE_SCHEMA_REGISTRY: frozenset[str] = frozenset(
    {
        "impact_t1",
        "impact_t2",
        "impact_t3",
        "impact_a1",
        "impact_a2",
        "impact_a3",
        "impact_a4",
        "impact_a5",
        "impact_d1",
        "impact_d2",
        "impact_d3",
        "impact_x1",
        "impact_s2_a",
        "impact_s2_b",
        "impact_s2_p",
        "impact_s2_i",
        "impact_s2_m",
        "impact_s2_scs",
    }
)

FIXTURE_SCHEMAS_BY_ID: dict[str, tuple[str, ...]] = {
    "T1": ("impact_t1",),
    "T2": ("impact_t2",),
    "T3": ("impact_t3",),
    "A1": ("impact_a1",),
    "A2": ("impact_a2",),
    "A3": ("impact_a3",),
    "A4": ("impact_a4",),
    "A5": ("impact_a5",),
    "D1": ("impact_d1",),
    "D2": ("impact_d2",),
    "D3": ("impact_d3",),
    "X1": ("impact_x1",),
    "S2_shadow": ("impact_s2_a", "impact_s2_b"),
    "S2_partition": ("impact_s2_p",),
    "S2_inherit": ("impact_s2_i",),
    "S2_missing_if_exists": ("impact_s2_m",),
    "S2_scs_off": ("impact_s2_scs",),
    "S2_rollback": ("impact_t1",),
}


def apply_setup_sql(admin_dsn: str, setup_path: Path) -> None:
    sql_text = setup_path.read_text(encoding="utf-8")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql_text)
        # Plan setup.sql is exact and omits grants; subject needs USAGE so
        # captured current_schemas(true) can rank fixture schemas.
        for schema in sorted(FIXTURE_SCHEMA_REGISTRY):
            row = conn.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname = %s",
                (schema,),
            ).fetchone()
            if row is None:
                continue
            conn.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema),
                    sql.Identifier(SUBJECT_ROLE),
                )
            )
            conn.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                    sql.Identifier(schema),
                    sql.Identifier(SUBJECT_ROLE),
                )
            )


def drop_schema(admin_dsn: str, schema: str) -> None:
    if schema not in FIXTURE_SCHEMA_REGISTRY or _SCHEMA_RE.fullmatch(schema) is None:
        raise ValueError(f"refusing to drop non-registry schema: {schema!r}")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


def drop_fixture_schemas(admin_dsn: str, fixture_id: str) -> None:
    for schema in FIXTURE_SCHEMAS_BY_ID[fixture_id]:
        drop_schema(admin_dsn, schema)
