"""SQL ↔ catalog type-name aliases for PostgreSQL base types.

`pg_type.typname` stores internal names (`int4`, `bool`). Migration SQL and
the T1–T3 coercion matrix use SQL names (`integer`, `boolean`). Resolution
looks up catalog names; rule engines compare SQL names.
"""

from __future__ import annotations

__all__ = ["catalog_typname", "sql_typname"]

# SQL name (normalized) → pg_type.typname
_SQL_TO_CATALOG: dict[str, str] = {
    "integer": "int4",
    "int": "int4",
    "smallint": "int2",
    "bigint": "int8",
    "boolean": "bool",
    "real": "float4",
    "double precision": "float8",
    "character": "bpchar",
    "character varying": "varchar",
    "char": "bpchar",
}

# pg_type.typname → SQL name used by coercion / rule keys
_CATALOG_TO_SQL: dict[str, str] = {
    "int2": "smallint",
    "int4": "integer",
    "int8": "bigint",
    "bool": "boolean",
    "float4": "real",
    "float8": "double precision",
    "bpchar": "character",
    "varchar": "varchar",
}


def catalog_typname(sql_or_catalog_name: str) -> str:
    """Return the `pg_type.typname` to look up for a migration type token."""
    normalized = sql_or_catalog_name.strip().lower()
    return _SQL_TO_CATALOG.get(normalized, normalized)


def sql_typname(catalog_or_sql_name: str) -> str:
    """Return the SQL-facing type name used by coercion / TYPE rule keys."""
    normalized = catalog_or_sql_name.strip().lower()
    return _CATALOG_TO_SQL.get(normalized, normalized)
