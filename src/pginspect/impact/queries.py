"""Package-owned, allowlisted QuerySpec registry for the impact profile.

Task 4 defined the session/preflight QuerySpecs; Task 5 adds the full
resolution/catalog/dependency/coercion inventory below. This module must
not import psycopg: it holds SQL text and metadata only. Session-profile
execution lives in `pginspect.session`; resolution/catalog execution goes
through `pginspect.impact.query_exec` + an injected `QueryExecutor`.

Every SELECT carries a concrete frozen `row_model` from `query_rows.py`.
The only specs allowed `row_model=None` are the three whose result is
intentionally discarded: `impact.begin_read_only_rr`, `impact.set_timeouts`
and `impact.harden_search_path`.

No query in this module ever calls a `pg_*_is_visible` catalog helper:
resolution ranks candidates using the caller-supplied
`current_schemas(true)` ordering only (design section 2.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, LiteralString

from pginspect.impact.query_rows import (
    CatalogClassOidRow,
    ColumnRow,
    ConstraintRow,
    DependencyEdgeRow,
    DomainConstraintRow,
    FunctionCandidateRow,
    FunctionRow,
    IndexRow,
    PgCastRow,
    PreflightRow,
    RelationCandidateRow,
    RelationMetricsRow,
    RelationRow,
    ResolutionCaptureRow,
    RewriteEvClassRow,
    SafetyVerifyRow,
    TypeCandidateRow,
    TypeRow,
)

CommandKind = Literal["SELECT", "SET", "BEGIN"]


@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    sql: LiteralString
    param_types: tuple[type, ...]
    row_model: type | None
    required_evidence_family: str
    command_kind: CommandKind


IMPACT_BEGIN_READ_ONLY_RR_SQL: LiteralString = "BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ"

# Exact SQL constant (normative, plan Task 4): first SELECT of the impact
# timeline. Bound parameters are `f"{ms}ms"` strings from SessionSafetyConfig;
# never spliced into SQL text.
IMPACT_SET_TIMEOUTS_SQL: LiteralString = """
SELECT
    pg_catalog.set_config('statement_timeout', %s, true),
    pg_catalog.set_config('lock_timeout', %s, true),
    pg_catalog.set_config('idle_in_transaction_session_timeout', %s, true)
"""

# Pre-harden capture: path/schemas/role/db (design section 2). Read before
# search_path is hardened to pg_catalog so unqualified-name resolution can
# rank against the connecting session's own search_path.
IMPACT_CAPTURE_RESOLUTION_CONTEXT_SQL: LiteralString = """
SELECT
    pg_catalog.current_database()::text AS database,
    CURRENT_ROLE::text AS role,
    SESSION_USER::text AS session_user,
    pg_catalog.current_schema()::text AS current_schema,
    pg_catalog.current_schemas(false) AS current_schemas_user,
    pg_catalog.current_schemas(true) AS current_schemas_with_implicit,
    pg_catalog.current_setting('search_path') AS search_path_raw,
    pg_catalog.current_setting('max_identifier_length')::integer
        AS max_identifier_length_bytes
"""

IMPACT_HARDEN_SEARCH_PATH_SQL: LiteralString = "SET LOCAL search_path = pg_catalog"

# Post-harden verification: RO scope, effective search_path, timeouts.
IMPACT_VERIFY_SAFETY_SQL: LiteralString = """
SELECT
    pg_catalog.current_setting('transaction_read_only')::boolean
        AS transaction_read_only,
    pg_catalog.current_setting('transaction_isolation') AS transaction_isolation,
    pg_catalog.current_setting('search_path') AS search_path_raw,
    pg_catalog.current_schemas(false) AS effective_search_path,
    (
        SELECT setting::bigint
        FROM pg_catalog.pg_settings
        WHERE name = 'statement_timeout'
    ) AS statement_timeout_ms,
    (
        SELECT setting::bigint
        FROM pg_catalog.pg_settings
        WHERE name = 'lock_timeout'
    ) AS lock_timeout_ms,
    (
        SELECT setting::bigint
        FROM pg_catalog.pg_settings
        WHERE name = 'idle_in_transaction_session_timeout'
    ) AS idle_in_transaction_session_timeout_ms
"""

# version/GUC/encoding/isolation/keywords (design section 2 / plan Task 4).
IMPACT_PREFLIGHT_READS_SQL: LiteralString = """
SELECT
    pg_catalog.current_setting('server_version') AS server_version,
    pg_catalog.current_setting('server_version_num')::integer AS server_version_num,
    pg_catalog.current_setting('standard_conforming_strings')
        AS standard_conforming_strings,
    pg_catalog.current_setting('transaction_read_only') AS transaction_read_only,
    pg_catalog.current_setting('transaction_isolation') AS transaction_isolation,
    pg_catalog.current_setting('server_encoding') AS server_encoding,
    pg_catalog.current_setting('client_encoding') AS client_encoding,
    pg_catalog.pg_is_in_recovery() AS in_recovery,
    (
        SELECT pg_catalog.jsonb_object_agg(word, catcode)
        FROM pg_catalog.pg_get_keywords()
    ) AS keyword_categories
"""

_IMPACT_SESSION_QUERY_SPECS: tuple[QuerySpec, ...] = (
    QuerySpec(
        query_id="impact.begin_read_only_rr",
        sql=IMPACT_BEGIN_READ_ONLY_RR_SQL,
        param_types=(),
        row_model=None,
        required_evidence_family="session",
        command_kind="BEGIN",
    ),
    QuerySpec(
        query_id="impact.set_timeouts",
        sql=IMPACT_SET_TIMEOUTS_SQL,
        param_types=(str, str, str),
        row_model=None,
        required_evidence_family="session",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.capture_resolution_context",
        sql=IMPACT_CAPTURE_RESOLUTION_CONTEXT_SQL,
        param_types=(),
        row_model=ResolutionCaptureRow,
        required_evidence_family="resolution",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.harden_search_path",
        sql=IMPACT_HARDEN_SEARCH_PATH_SQL,
        param_types=(),
        row_model=None,
        required_evidence_family="session",
        command_kind="SET",
    ),
    QuerySpec(
        query_id="impact.verify_safety",
        sql=IMPACT_VERIFY_SAFETY_SQL,
        param_types=(),
        row_model=SafetyVerifyRow,
        required_evidence_family="session",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.preflight_reads",
        sql=IMPACT_PREFLIGHT_READS_SQL,
        param_types=(),
        row_model=PreflightRow,
        required_evidence_family="preflight",
        command_kind="SELECT",
    ),
)

# --- Resolution QuerySpecs (design section 2.4): rank candidates against a
# caller-supplied schema ordering. Never `pg_*_is_visible`.

IMPACT_RESOLVE_RELATION_CANDIDATES_SQL: LiteralString = """
SELECT
    c.oid AS oid,
    n.nspname AS nspname,
    c.relname AS relname
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%s)
  AND c.relname = %s
"""

IMPACT_RESOLVE_TYPE_CANDIDATES_SQL: LiteralString = """
SELECT
    t.oid AS oid,
    n.nspname AS nspname,
    t.typname AS typname
FROM pg_catalog.pg_type t
JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = ANY(%s)
  AND t.typname = %s
"""

IMPACT_RESOLVE_FUNCTION_CANDIDATES_SQL: LiteralString = """
SELECT
    p.oid AS oid,
    n.nspname AS nspname,
    p.proname AS proname
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = ANY(%s)
  AND p.proname = %s
  AND CASE
        WHEN COALESCE(array_length(%s::oid[], 1), 0) = 0 THEN p.pronargs = 0
        ELSE p.proargtypes::oid[] = %s::oid[]
      END
"""

# --- Catalog object QuerySpecs (design section 2.8): one relation/type/
# function/domain-constraint/index/constraint per allowlisted query_id.

IMPACT_FETCH_RELATION_SQL: LiteralString = """
SELECT
    c.oid AS oid,
    n.nspname AS nspname,
    c.relname AS relname,
    c.relkind AS relkind,
    c.relpersistence AS relpersistence,
    c.relispartition AS relispartition,
    COALESCE(
        (
            SELECT array_agg(i.inhparent ORDER BY i.inhseqno)
            FROM pg_catalog.pg_inherits i
            WHERE i.inhrelid = c.oid
        ),
        ARRAY[]::oid[]
    ) AS inherits_parents,
    COALESCE(
        (
            SELECT array_agg(i2.inhrelid)
            FROM pg_catalog.pg_inherits i2
            WHERE i2.inhparent = c.oid
        ),
        ARRAY[]::oid[]
    ) AS inherits_children
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.oid = %s
"""

IMPACT_FETCH_COLUMNS_SQL: LiteralString = """
SELECT
    a.attnum AS attnum,
    a.attname AS attname,
    a.atttypid AS type_oid,
    a.atttypmod AS typmod,
    a.attndims AS attndims,
    a.attnotnull AS attnotnull,
    a.attisdropped AS attisdropped,
    a.attidentity AS identity,
    a.attgenerated AS generated,
    ad.adbin::text AS default_bin,
    a.attcollation AS collation_oid
FROM pg_catalog.pg_attribute a
LEFT JOIN pg_catalog.pg_attrdef ad
    ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
WHERE a.attrelid = %s
  AND a.attnum > 0
ORDER BY a.attnum
"""

IMPACT_FETCH_TYPE_SQL: LiteralString = """
SELECT
    t.oid AS oid,
    n.nspname AS nspname,
    t.typname AS typname,
    t.typtype AS typtype,
    t.typcategory AS typcategory,
    t.typbasetype AS typbasetype,
    t.typelem AS typelem,
    t.typarray AS typarray,
    t.typndims AS typndims,
    t.typtypmod AS typtypmod,
    t.typlen AS typlen,
    t.typbyval AS typbyval,
    t.typalign AS typalign,
    t.typcollation AS typcollation,
    t.typdefaultbin AS typdefaultbin,
    t.typdefault AS typdefault,
    t.typnotnull AS domain_not_null
FROM pg_catalog.pg_type t
JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
WHERE t.oid = %s
"""

IMPACT_FETCH_DOMAIN_CONSTRAINTS_SQL: LiteralString = """
SELECT
    c.oid AS oid,
    c.conname AS conname,
    c.contype AS contype,
    (c.conbin IS NOT NULL) AS conbin_present
FROM pg_catalog.pg_constraint c
WHERE c.contypid = %s
ORDER BY c.oid
"""

IMPACT_FETCH_INDEXES_SQL: LiteralString = """
SELECT
    ci.oid AS oid,
    n.nspname AS nspname,
    ci.relname AS relname,
    i.indrelid AS indrelid,
    i.indisunique AS indisunique,
    i.indisprimary AS indisprimary,
    i.indisexclusion AS indisexclusion,
    i.indkey::int2[]::int[] AS indkey_attnums,
    i.indisvalid AS indisvalid,
    (i.indpred IS NOT NULL) AS predicate_present,
    EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint con
        WHERE con.conindid = ci.oid
    ) AS is_constraint_backed
FROM pg_catalog.pg_index i
JOIN pg_catalog.pg_class ci ON ci.oid = i.indexrelid
JOIN pg_catalog.pg_namespace n ON n.oid = ci.relnamespace
WHERE i.indrelid = %s
ORDER BY ci.oid
"""

IMPACT_FETCH_CONSTRAINTS_SQL: LiteralString = """
SELECT
    c.oid AS oid,
    c.conname AS conname,
    c.contype AS contype,
    c.conrelid AS conrelid,
    c.confrelid AS confrelid,
    COALESCE(c.conkey, ARRAY[]::int2[])::int[] AS conkey_attnums,
    COALESCE(c.confkey, ARRAY[]::int2[])::int[] AS confkey_attnums,
    c.confupdtype AS confupdtype,
    c.confdeltype AS confdeltype
FROM pg_catalog.pg_constraint c
WHERE c.conrelid = %s
ORDER BY c.oid
"""

IMPACT_FETCH_FUNCTION_SQL: LiteralString = """
SELECT
    p.oid AS oid,
    n.nspname AS nspname,
    p.proname AS proname,
    COALESCE(p.proargtypes::oid[], ARRAY[]::oid[]) AS proargtypes,
    p.prorettype AS prorettype,
    p.provolatile AS provolatile,
    p.prokind AS prokind
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
WHERE p.oid = %s
"""

# Bounded BFS batch: dependents of one (refclassid, refobjid, refobjsubid)
# object address, capped at the caller-supplied edge limit (design section
# 2.8 default 10_000 across the whole traversal).
IMPACT_FETCH_DEPENDENCY_EDGES_SQL: LiteralString = """
SELECT
    d.classid AS classid,
    d.objid AS objid,
    d.objsubid AS objsubid,
    d.refclassid AS refclassid,
    d.refobjid AS refobjid,
    d.refobjsubid AS refobjsubid,
    d.deptype AS deptype
FROM pg_catalog.pg_depend d
WHERE d.refclassid = %s
  AND d.refobjid = %s
  AND d.refobjsubid = %s
ORDER BY d.classid, d.objid, d.objsubid
LIMIT %s
"""

# Live OID of pg_catalog.pg_class for pg_depend.classid / refclassid roots
# (design section 2.8). Never hardcode a numeric catalog OID.
IMPACT_FETCH_PG_CLASS_CLASSOID_SQL: LiteralString = """
SELECT c.oid AS classoid
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'pg_catalog'
  AND c.relname = 'pg_class'
"""

IMPACT_FETCH_REWRITE_EV_CLASS_SQL: LiteralString = """
SELECT r.ev_class AS ev_class
FROM pg_catalog.pg_rewrite r
WHERE r.oid = %s
"""

IMPACT_FETCH_RELATION_METRICS_SQL: LiteralString = """
WITH target AS (SELECT %s::oid AS relid)
SELECT
    pg_catalog.pg_relation_size(target.relid) AS pg_relation_size,
    pg_catalog.pg_total_relation_size(target.relid) AS pg_total_relation_size,
    pg_catalog.pg_indexes_size(target.relid) AS indexes_size,
    (
        SELECT s.n_live_tup
        FROM pg_catalog.pg_stat_all_tables s
        WHERE s.relid = target.relid
    ) AS n_live_tup
FROM target
"""

IMPACT_FETCH_PG_CAST_SQL: LiteralString = """
SELECT
    c.castsource AS castsource,
    c.casttarget AS casttarget,
    c.castfunc AS castfunc,
    c.castcontext AS castcontext,
    c.castmethod AS castmethod
FROM pg_catalog.pg_cast c
WHERE c.castsource = %s
  AND c.casttarget = %s
"""

_IMPACT_CATALOG_QUERY_SPECS: tuple[QuerySpec, ...] = (
    QuerySpec(
        query_id="impact.resolve_relation_candidates",
        sql=IMPACT_RESOLVE_RELATION_CANDIDATES_SQL,
        param_types=(tuple, str),
        row_model=RelationCandidateRow,
        required_evidence_family="resolution",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.resolve_type_candidates",
        sql=IMPACT_RESOLVE_TYPE_CANDIDATES_SQL,
        param_types=(tuple, str),
        row_model=TypeCandidateRow,
        required_evidence_family="resolution",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.resolve_function_candidates",
        sql=IMPACT_RESOLVE_FUNCTION_CANDIDATES_SQL,
        param_types=(tuple, str, tuple, tuple),
        row_model=FunctionCandidateRow,
        required_evidence_family="resolution",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_relation",
        sql=IMPACT_FETCH_RELATION_SQL,
        param_types=(int,),
        row_model=RelationRow,
        required_evidence_family="catalog_object",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_columns",
        sql=IMPACT_FETCH_COLUMNS_SQL,
        param_types=(int,),
        row_model=ColumnRow,
        required_evidence_family="catalog_object",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_type",
        sql=IMPACT_FETCH_TYPE_SQL,
        param_types=(int,),
        row_model=TypeRow,
        required_evidence_family="catalog_object",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_domain_constraints",
        sql=IMPACT_FETCH_DOMAIN_CONSTRAINTS_SQL,
        param_types=(int,),
        row_model=DomainConstraintRow,
        required_evidence_family="catalog_object",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_indexes",
        sql=IMPACT_FETCH_INDEXES_SQL,
        param_types=(int,),
        row_model=IndexRow,
        required_evidence_family="catalog_object",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_constraints",
        sql=IMPACT_FETCH_CONSTRAINTS_SQL,
        param_types=(int,),
        row_model=ConstraintRow,
        required_evidence_family="catalog_object",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_function",
        sql=IMPACT_FETCH_FUNCTION_SQL,
        param_types=(int,),
        row_model=FunctionRow,
        required_evidence_family="catalog_object",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_dependency_edges",
        sql=IMPACT_FETCH_DEPENDENCY_EDGES_SQL,
        param_types=(int, int, int, int),
        row_model=DependencyEdgeRow,
        required_evidence_family="dependency_edge",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_pg_class_classoid",
        sql=IMPACT_FETCH_PG_CLASS_CLASSOID_SQL,
        param_types=(),
        row_model=CatalogClassOidRow,
        required_evidence_family="catalog_object",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_rewrite_ev_class",
        sql=IMPACT_FETCH_REWRITE_EV_CLASS_SQL,
        param_types=(int,),
        row_model=RewriteEvClassRow,
        required_evidence_family="dependency_edge",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_relation_metrics",
        sql=IMPACT_FETCH_RELATION_METRICS_SQL,
        param_types=(int,),
        row_model=RelationMetricsRow,
        required_evidence_family="metric_observation",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.fetch_pg_cast",
        sql=IMPACT_FETCH_PG_CAST_SQL,
        param_types=(int, int),
        row_model=PgCastRow,
        required_evidence_family="coercion",
        command_kind="SELECT",
    ),
)

IMPACT_QUERY_REGISTRY: Mapping[str, QuerySpec] = MappingProxyType(
    {spec.query_id: spec for spec in (*_IMPACT_SESSION_QUERY_SPECS, *_IMPACT_CATALOG_QUERY_SPECS)}
)
