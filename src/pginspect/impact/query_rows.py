"""Concrete, frozen row models for every allowlisted SELECT `QuerySpec`.

Each model's field names are exactly the column aliases of the SQL constant
it decodes, so a drift between the registry SQL and the Python contract is a
decode failure rather than a silent `KeyError` deep inside an analysis rule.

`decode_row` is deliberately strict: unknown columns, missing columns and
values of the wrong Python type are all rejected. Only the three QuerySpecs
whose result is intentionally discarded (`impact.begin_read_only_rr`,
`impact.set_timeouts`, `impact.harden_search_path`) may carry
`row_model=None`.

This module holds data shapes only: no psycopg import, no SQL text, no
query execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from types import MappingProxyType, UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from pginspect.impact.models.catalog_types import PgCastRow

__all__ = [
    "RowDecodeError",
    "decode_row",
    "row_as_mapping",
    "ResolutionCaptureRow",
    "SafetyVerifyRow",
    "PreflightRow",
    "RelationCandidateRow",
    "TypeCandidateRow",
    "FunctionCandidateRow",
    "RelationRow",
    "ColumnRow",
    "TypeRow",
    "DomainConstraintRow",
    "IndexRow",
    "ConstraintRow",
    "FunctionRow",
    "DependencyEdgeRow",
    "RelationMetricsRow",
    "CatalogClassOidRow",
    "PgCastRow",
]


class RowDecodeError(ValueError):
    """Raised when a database row does not match its `QuerySpec.row_model`."""


# --- Session / preflight rows -------------------------------------------------


@dataclass(frozen=True)
class ResolutionCaptureRow:
    """`impact.capture_resolution_context` (pre-harden path/schemas/role/db)."""

    database: str
    role: str
    session_user: str
    current_schema: str | None
    current_schemas_user: tuple[str, ...]
    current_schemas_with_implicit: tuple[str, ...]
    search_path_raw: str
    max_identifier_length_bytes: int


@dataclass(frozen=True)
class SafetyVerifyRow:
    """`impact.verify_safety` (post-harden RO scope, isolation, path, timeouts)."""

    transaction_read_only: bool
    transaction_isolation: str
    search_path_raw: str
    effective_search_path: tuple[str, ...]
    statement_timeout_ms: int
    lock_timeout_ms: int
    idle_in_transaction_session_timeout_ms: int


@dataclass(frozen=True)
class PreflightRow:
    """`impact.preflight_reads` (version/GUC/encoding/isolation/keywords)."""

    server_version: str
    server_version_num: int
    standard_conforming_strings: str
    transaction_read_only: str
    transaction_isolation: str
    server_encoding: str
    client_encoding: str
    in_recovery: bool
    keyword_categories: Mapping[str, str]


# --- Resolution candidate rows ------------------------------------------------


@dataclass(frozen=True)
class RelationCandidateRow:
    """`impact.resolve_relation_candidates`."""

    oid: int
    nspname: str
    relname: str


@dataclass(frozen=True)
class TypeCandidateRow:
    """`impact.resolve_type_candidates`."""

    oid: int
    nspname: str
    typname: str


@dataclass(frozen=True)
class FunctionCandidateRow:
    """`impact.resolve_function_candidates`."""

    oid: int
    nspname: str
    proname: str


# --- Catalog object rows ------------------------------------------------------


@dataclass(frozen=True)
class RelationRow:
    """`impact.fetch_relation`."""

    oid: int
    nspname: str
    relname: str
    relkind: str
    relpersistence: str
    relispartition: bool
    inherits_parents: tuple[int, ...]
    inherits_children: tuple[int, ...]


@dataclass(frozen=True)
class ColumnRow:
    """`impact.fetch_columns`."""

    attnum: int
    attname: str
    type_oid: int
    typmod: int
    attndims: int
    attnotnull: bool
    attisdropped: bool
    identity: str
    generated: str
    default_bin: str | None
    collation_oid: int | None


@dataclass(frozen=True)
class TypeRow:
    """`impact.fetch_type`."""

    oid: int
    nspname: str
    typname: str
    typtype: str
    typcategory: str
    typbasetype: int
    typelem: int
    typarray: int
    typndims: int
    typtypmod: int
    typlen: int
    typbyval: bool
    typalign: str
    typcollation: int
    typdefaultbin: str | None
    typdefault: str | None
    domain_not_null: bool


@dataclass(frozen=True)
class DomainConstraintRow:
    """`impact.fetch_domain_constraints`."""

    oid: int
    conname: str
    contype: str
    conbin_present: bool


@dataclass(frozen=True)
class IndexRow:
    """`impact.fetch_indexes`."""

    oid: int
    nspname: str
    relname: str
    indrelid: int
    indisunique: bool
    indisprimary: bool
    indisexclusion: bool
    indkey_attnums: tuple[int, ...]
    indisvalid: bool
    predicate_present: bool
    is_constraint_backed: bool


@dataclass(frozen=True)
class ConstraintRow:
    """`impact.fetch_constraints`."""

    oid: int
    conname: str
    contype: str
    conrelid: int
    confrelid: int
    conkey_attnums: tuple[int, ...]
    confkey_attnums: tuple[int, ...]
    confupdtype: str
    confdeltype: str


@dataclass(frozen=True)
class FunctionRow:
    """`impact.fetch_function`."""

    oid: int
    nspname: str
    proname: str
    proargtypes: tuple[int, ...]
    prorettype: int
    provolatile: str
    prokind: str


@dataclass(frozen=True)
class DependencyEdgeRow:
    """`impact.fetch_dependency_edges`."""

    classid: int
    objid: int
    objsubid: int
    refclassid: int
    refobjid: int
    refobjsubid: int
    deptype: str


@dataclass(frozen=True)
class CatalogClassOidRow:
    """`impact.fetch_pg_class_classoid` — live OID of `pg_catalog.pg_class`."""

    classoid: int


@dataclass(frozen=True)
class RelationMetricsRow:
    """`impact.fetch_relation_metrics`."""

    pg_relation_size: int
    pg_total_relation_size: int
    indexes_size: int
    n_live_tup: int | None


# --- Strict decoding ----------------------------------------------------------


def _decode_value(annotation: Any, value: object, field_name: str) -> Any:
    origin = get_origin(annotation)

    if origin is Literal:
        allowed = get_args(annotation)
        if value in allowed:
            return value
        raise RowDecodeError(f"field {field_name!r}: {value!r} is not one of {allowed!r}")

    if origin is Union or origin is UnionType:
        args = get_args(annotation)
        if value is None:
            if type(None) in args:
                return None
            raise RowDecodeError(f"field {field_name!r} must not be null")
        non_null = [arg for arg in args if arg is not type(None)]
        if len(non_null) != 1:
            raise RowDecodeError(f"field {field_name!r} has an unsupported annotation")
        return _decode_value(non_null[0], value, field_name)

    if origin is tuple:
        args = get_args(annotation)
        if len(args) != 2 or args[1] is not Ellipsis:
            raise RowDecodeError(f"field {field_name!r} has an unsupported tuple annotation")
        # PostgreSQL arrays arrive as lists; the model contract is immutable.
        if not isinstance(value, (list, tuple)):
            raise RowDecodeError(
                f"field {field_name!r} expected an array, got {type(value).__name__}"
            )
        return tuple(_decode_value(args[0], item, field_name) for item in value)

    if isinstance(origin, type) and issubclass(origin, Mapping):
        key_annotation, value_annotation = get_args(annotation)
        if not isinstance(value, Mapping):
            raise RowDecodeError(f"field {field_name!r} expected a mapping")
        return MappingProxyType(
            {
                _decode_value(key_annotation, key, field_name): _decode_value(
                    value_annotation, item, field_name
                )
                for key, item in value.items()
            }
        )

    if annotation is bool:
        if isinstance(value, bool):
            return value
        raise RowDecodeError(f"field {field_name!r} expected bool, got {type(value).__name__}")

    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RowDecodeError(f"field {field_name!r} expected int, got {type(value).__name__}")
        return value

    if annotation is str:
        if isinstance(value, str):
            return value
        raise RowDecodeError(f"field {field_name!r} expected str, got {type(value).__name__}")

    raise RowDecodeError(f"field {field_name!r} has an unsupported annotation {annotation!r}")


def decode_row(model: type[Any], row: Mapping[str, object]) -> Any:
    """Decode one database row into `model`, rejecting any shape drift.

    Missing columns, unexpected columns and values whose Python type does not
    match the model annotation are all `RowDecodeError`s: a QuerySpec whose
    SQL stops matching its `row_model` fails loudly at the seam.
    """
    try:
        field_names = tuple(field.name for field in fields(model))
    except TypeError:
        raise RowDecodeError(f"{model!r} is not a row model dataclass") from None

    unexpected = sorted(set(row) - set(field_names))
    if unexpected:
        raise RowDecodeError(f"{model.__name__}: unexpected columns {unexpected}")
    missing = sorted(set(field_names) - set(row))
    if missing:
        raise RowDecodeError(f"{model.__name__}: missing columns {missing}")

    hints = get_type_hints(model)
    decoded = {name: _decode_value(hints[name], row[name], name) for name in field_names}
    return model(**decoded)


def row_as_mapping(row: Any) -> Mapping[str, object]:
    """Expose a decoded row model as an immutable column mapping."""
    try:
        field_names = tuple(field.name for field in fields(row))
    except TypeError:
        raise RowDecodeError(f"{row!r} is not a row model instance") from None
    return MappingProxyType({name: getattr(row, name) for name in field_names})
