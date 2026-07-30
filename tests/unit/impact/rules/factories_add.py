"""`AddColumnFacts` builders for the design section 3.7 matrix.

Effective-default classification is the caller's job, so these factories are
where the SQL-shaped cases ("`DEFAULT false`", "`DEFAULT pg_catalog.now()`",
"a domain whose default the MVP allowlist cannot classify") are turned into
the classified axes the engine consumes. `classify_volatility` is the piece of
caller-side logic the `now()` vs `clock_timestamp()` test needs, so it lives
here rather than being inlined per case.
"""

from __future__ import annotations

from pginspect.impact.models.catalog_types import (
    DomainConstraintSnapshot,
    FunctionSnapshot,
    TypeSnapshot,
)
from pginspect.impact.rules.add_column import (
    AddColumnFacts,
    DefaultCoercion,
    DefaultNullability,
    DefaultVolatility,
    EffectiveDefaultKind,
)

DEFAULT_MAJOR = 16
SERVER_MAJORS = (14, 15, 16, 17, 18)

NOW = FunctionSnapshot(
    oid=1299,
    nspname="pg_catalog",
    proname="now",
    proargtypes=(),
    prorettype=1184,
    provolatile="s",
    prokind="f",
)

CLOCK_TIMESTAMP = FunctionSnapshot(
    oid=2648,
    nspname="pg_catalog",
    proname="clock_timestamp",
    proargtypes=(),
    prorettype=1184,
    provolatile="v",
    prokind="f",
)


def classify_volatility(function: FunctionSnapshot) -> DefaultVolatility:
    """Map a resolved allowlisted built-in onto the design section 3.7 axis.

    Only `pg_catalog.now()` and `pg_catalog.clock_timestamp()` are on the
    qualified allowlist, so anything else stays `unknown` even if its
    `provolatile` looks harmless.
    """
    if (function.nspname, function.proname) not in {
        ("pg_catalog", "now"),
        ("pg_catalog", "clock_timestamp"),
    }:
        return "unknown"
    return "proven_volatile" if function.provolatile == "v" else "proven_nonvolatile"


def domain_type(*, with_constraints: bool, has_default: bool = True) -> TypeSnapshot:
    constraints = (
        (
            DomainConstraintSnapshot(
                oid=90001,
                conname="positive_amount_check",
                contype="c",
                conbin_present=True,
            ),
        )
        if with_constraints
        else ()
    )
    return TypeSnapshot(
        oid=80001,
        nspname="public",
        typname="positive_amount",
        typtype="d",
        typcategory="N",
        typbasetype=23,
        typelem=0,
        typarray=0,
        typndims=0,
        typtypmod=-1,
        typlen=4,
        typbyval=True,
        typalign="i",
        typcollation=0,
        typdefaultbin="{CONST :consttype 23}" if has_default else None,
        typdefault="0" if has_default else None,
        domain_not_null=False,
        domain_constraints=constraints,
    )


def _facts(
    *,
    server_major: int = DEFAULT_MAJOR,
    nullable: bool = True,
    indexes_exist: bool = False,
    metrics_present: bool = True,
    n_live_tup: int | None = 1_000,
    effective_default_kind: EffectiveDefaultKind = "null",
    default_volatility: DefaultVolatility = "proven_nonvolatile",
    default_coercion: DefaultCoercion = "proven_valid",
    default_nullability: DefaultNullability = "proven_null",
    domain_has_constraints: bool = False,
    target_type: TypeSnapshot | None = None,
    default_function: FunctionSnapshot | None = None,
    domain_constraints: tuple[DomainConstraintSnapshot, ...] = (),
    index_names: tuple[str, ...] = (),
) -> AddColumnFacts:
    return AddColumnFacts(
        server_major=server_major,
        nullable=nullable,
        indexes_exist=indexes_exist,
        metrics_present=metrics_present,
        n_live_tup=n_live_tup,
        effective_default_kind=effective_default_kind,
        default_volatility=default_volatility,
        default_coercion=default_coercion,
        default_nullability=default_nullability,
        domain_has_constraints=domain_has_constraints,
        target_type=target_type,
        default_function=default_function,
        domain_constraints=domain_constraints,
        index_names=index_names,
    )


def coercion_invalid(*, indexes_exist: bool = True) -> AddColumnFacts:
    """`ADD COLUMN n integer DEFAULT 'not-a-number'` — the DEFAULT cannot be coerced."""
    return _facts(
        indexes_exist=indexes_exist,
        index_names=("t_id_idx",) if indexes_exist else (),
        effective_default_kind="column_expression",
        default_coercion="proven_invalid",
        default_nullability="proven_nonnull",
    )


def a1_nullable_no_default() -> AddColumnFacts:
    """A1 — `ADD COLUMN note text` on a plain (non-domain) type."""
    return _facts(effective_default_kind="null")


def a2_nullable_const_default() -> AddColumnFacts:
    """A2 — `ADD COLUMN flag boolean DEFAULT false`."""
    return _facts(
        effective_default_kind="column_expression",
        default_nullability="proven_nonnull",
    )


def nullable_domain_default_nonvolatile() -> AddColumnFacts:
    """No written DEFAULT, but the domain supplies a classifiable constant one."""
    return _facts(
        effective_default_kind="domain_expression",
        default_nullability="proven_nonnull",
        target_type=domain_type(with_constraints=False),
    )


def unknown_domain_default(*, indexes_exist: bool) -> AddColumnFacts:
    """Domain default present but outside the MVP allowlist / coercion rules."""
    return _facts(
        indexes_exist=indexes_exist,
        index_names=("t_id_idx",) if indexes_exist else (),
        effective_default_kind="domain_expression",
        default_volatility="unknown",
        default_coercion="unknown",
        default_nullability="unknown",
        target_type=domain_type(with_constraints=False),
    )


def constrained_domain(*, indexes_exist: bool) -> AddColumnFacts:
    """Domain type carrying a CHECK constraint, which forces a rewrite on 14-18."""
    target = domain_type(with_constraints=True)
    return _facts(
        indexes_exist=indexes_exist,
        index_names=("t_id_idx",) if indexes_exist else (),
        effective_default_kind="domain_expression",
        default_nullability="proven_nonnull",
        domain_has_constraints=True,
        target_type=target,
        domain_constraints=target.domain_constraints,
    )


def now_default() -> AddColumnFacts:
    """`ADD COLUMN seen_at timestamptz DEFAULT pg_catalog.now()` — stable, not volatile."""
    return _facts(
        indexes_exist=True,
        index_names=("t_id_idx",),
        effective_default_kind="column_expression",
        default_volatility=classify_volatility(NOW),
        default_nullability="proven_nonnull",
        default_function=NOW,
    )


def clock_timestamp_default(*, indexes_exist: bool) -> AddColumnFacts:
    """A3 — `ADD COLUMN seen_at timestamptz DEFAULT pg_catalog.clock_timestamp()`."""
    return _facts(
        indexes_exist=indexes_exist,
        index_names=("impact_a3_id_idx",) if indexes_exist else (),
        effective_default_kind="column_expression",
        default_volatility=classify_volatility(CLOCK_TIMESTAMP),
        default_nullability="proven_nonnull",
        default_function=CLOCK_TIMESTAMP,
    )


def explicit_default_null() -> AddColumnFacts:
    """`ADD COLUMN note text DEFAULT NULL` — written, but still an effective NULL."""
    return _facts(effective_default_kind="explicit_null")


def not_null_proven_nonnull_default() -> AddColumnFacts:
    """`ADD COLUMN flag boolean NOT NULL DEFAULT false`."""
    return _facts(
        nullable=False,
        effective_default_kind="column_expression",
        default_nullability="proven_nonnull",
    )


def not_null_unknown_nullability_default() -> AddColumnFacts:
    """NOT NULL with a classifiable default whose nullability is not proven."""
    return _facts(
        nullable=False,
        effective_default_kind="column_expression",
        default_nullability="unknown",
    )


def a4_not_null_no_default() -> AddColumnFacts:
    """A4 — `ADD COLUMN required_col text NOT NULL`, no metrics collected."""
    return _facts(
        nullable=False,
        metrics_present=False,
        n_live_tup=None,
        effective_default_kind="null",
    )


def a5_not_null_no_default_empty_stats() -> AddColumnFacts:
    """A5 — same statement as A4 after ANALYZE reported `n_live_tup = 0`."""
    return _facts(
        nullable=False,
        metrics_present=True,
        n_live_tup=0,
        effective_default_kind="null",
    )
