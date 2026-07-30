"""Exact `TypeChangeFacts` builders, one per design section 3.6 matrix row.

Every builder returns a fully specified fact set — no partial fixtures, no
placeholder values — so a matrix row's expected verdict can only be produced
by the facts that row is actually about.

Oids and typmods use PostgreSQL's real encodings: `varchar(n)` stores
``n + VARLENA_HEADER`` in `atttypmod`, ``-1`` means "no modifier", and
collation oid ``100`` is ``pg_catalog."default"`` while ``950`` is
``pg_catalog."C"``.
"""

from __future__ import annotations

from pginspect.impact.models.catalog_types import PgCastRow
from pginspect.impact.rules.type_change import TypeChangeFacts

INTEGER_OID = 23
TEXT_OID = 25
VARCHAR_OID = 1043

DEFAULT_COLLATION_OID = 100
C_COLLATION_OID = 950

NO_TYPMOD = -1
VARLENA_HEADER = 4

SUPPORTED_MAJORS = (14, 15, 16, 17, 18)

DOMAIN_TYPE_NAME = "email_address"

#: Live `pg_cast` row proving `text -> varchar` is binary-coercible. Without
#: this row `lookup_coercion` refuses to claim the binary path.
TEXT_TO_VARCHAR_BINARY_CAST = PgCastRow(
    castsource=TEXT_OID,
    casttarget=VARCHAR_OID,
    castfunc=0,
    castcontext="i",
    castmethod="b",
)

#: Explicit-only `text -> integer` row: present in `pg_cast` in no assignment
#: or implicit context, which is exactly what T3's checked-in absence asserts.
TEXT_TO_INTEGER_EXPLICIT_CAST = PgCastRow(
    castsource=TEXT_OID,
    casttarget=INTEGER_OID,
    castfunc=0,
    castcontext="e",
    castmethod="i",
)


def varchar_typmod(length: int) -> int:
    """`atttypmod` PostgreSQL stores for ``varchar(length)``."""
    return length + VARLENA_HEADER


def same_declared_type_no_using(
    *,
    server_major: int = 16,
    affected_indexes_exist: bool = False,
    metrics_present: bool = True,
) -> TypeChangeFacts:
    """`varchar(50)` restated as `varchar(50)`: same name, typmod, collation."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="varchar",
        target_type_name="varchar",
        source_typmod=varchar_typmod(50),
        target_typmod=varchar_typmod(50),
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=DEFAULT_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=metrics_present,
        pg_cast_rows=(),
        table_exists=True,
    )


def unknown_assignment_cast(
    *,
    affected_indexes_exist: bool,
    server_major: int = 16,
) -> TypeChangeFacts:
    """`integer -> numeric`: a pair with no checked-in coercion origin."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="integer",
        target_type_name="numeric",
        source_typmod=NO_TYPMOD,
        target_typmod=NO_TYPMOD,
        source_collation_oid=None,
        target_collation_oid=None,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )


def opaque_using(
    *,
    affected_indexes_exist: bool,
    server_major: int = 16,
) -> TypeChangeFacts:
    """`text -> integer` with an opaque ``USING``.

    The pair on its own is T3 (`would_fail`); the unproven ``USING`` must
    outrank that classification.
    """
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="text",
        target_type_name="integer",
        source_typmod=NO_TYPMOD,
        target_typmod=NO_TYPMOD,
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=None,
        source_is_domain=False,
        target_is_domain=False,
        using_present=True,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(TEXT_TO_INTEGER_EXPLICIT_CAST,),
        table_exists=True,
    )


def proven_rewrite_integer_to_text(
    *,
    affected_indexes_exist: bool,
    server_major: int = 16,
) -> TypeChangeFacts:
    """T1: `integer -> text` via the server's automatic I/O coercion."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="integer",
        target_type_name="text",
        source_typmod=NO_TYPMOD,
        target_typmod=NO_TYPMOD,
        source_collation_oid=None,
        target_collation_oid=DEFAULT_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )


def binary_text_to_varchar(
    *,
    server_major: int,
    affected_indexes_exist: bool,
) -> TypeChangeFacts:
    """T2: `text -> varchar` (unconstrained), same collation, no domain, no USING."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="text",
        target_type_name="varchar",
        source_typmod=NO_TYPMOD,
        target_typmod=NO_TYPMOD,
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=DEFAULT_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(TEXT_TO_VARCHAR_BINARY_CAST,),
        table_exists=True,
    )


def no_assignment_cast_text_to_integer(
    *,
    affected_indexes_exist: bool = False,
    server_major: int = 16,
    table_exists: bool = True,
) -> TypeChangeFacts:
    """T3: `text -> integer` with no ``USING`` and no assignment cast."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="text",
        target_type_name="integer",
        source_typmod=NO_TYPMOD,
        target_typmod=NO_TYPMOD,
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=None,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(TEXT_TO_INTEGER_EXPLICIT_CAST,),
        table_exists=table_exists,
    )


def typmod_widen(
    *,
    affected_indexes_exist: bool,
    server_major: int = 16,
) -> TypeChangeFacts:
    """`varchar(10) -> varchar(20)`: same type, wider modifier."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="varchar",
        target_type_name="varchar",
        source_typmod=varchar_typmod(10),
        target_typmod=varchar_typmod(20),
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=DEFAULT_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )


def typmod_narrow(
    *,
    affected_indexes_exist: bool,
    server_major: int = 16,
) -> TypeChangeFacts:
    """`varchar(20) -> varchar(10)`: same type, narrower modifier."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="varchar",
        target_type_name="varchar",
        source_typmod=varchar_typmod(20),
        target_typmod=varchar_typmod(10),
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=DEFAULT_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )


def collation_change_only(
    *,
    affected_indexes_exist: bool,
    server_major: int = 16,
) -> TypeChangeFacts:
    """`varchar(50)` keeping its modifier but moving from default to `C`."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="varchar",
        target_type_name="varchar",
        source_typmod=varchar_typmod(50),
        target_typmod=varchar_typmod(50),
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=C_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )


def domain_source_to_base(
    *,
    affected_indexes_exist: bool,
    server_major: int = 16,
) -> TypeChangeFacts:
    """Domain `email_address` (over `text`) back down to its base `text`."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name=DOMAIN_TYPE_NAME,
        target_type_name="text",
        source_typmod=NO_TYPMOD,
        target_typmod=NO_TYPMOD,
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=DEFAULT_COLLATION_OID,
        source_is_domain=True,
        target_is_domain=False,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )


def base_to_domain_target(
    *,
    affected_indexes_exist: bool,
    server_major: int = 16,
) -> TypeChangeFacts:
    """Base `text` up into domain `email_address`, whose constraints re-check."""
    return TypeChangeFacts(
        server_major=server_major,
        source_type_name="text",
        target_type_name=DOMAIN_TYPE_NAME,
        source_typmod=NO_TYPMOD,
        target_typmod=NO_TYPMOD,
        source_collation_oid=DEFAULT_COLLATION_OID,
        target_collation_oid=DEFAULT_COLLATION_OID,
        source_is_domain=False,
        target_is_domain=True,
        using_present=False,
        using_identity_proven=False,
        affected_indexes_exist=affected_indexes_exist,
        metrics_present=True,
        pg_cast_rows=(),
        table_exists=True,
    )
