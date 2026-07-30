"""Package-owned, allowlisted QuerySpec registry for the impact session profile.

Only session/preflight QuerySpecs are defined in this module for Task 4; the
full catalog inventory (resolution/catalog/dependency/coercion QuerySpecs)
is added by Task 5. This module must not import psycopg: it holds SQL text
and metadata only. Execution lives in `pginspect.session`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, LiteralString

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
        row_model=None,
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
        row_model=None,
        required_evidence_family="session",
        command_kind="SELECT",
    ),
    QuerySpec(
        query_id="impact.preflight_reads",
        sql=IMPACT_PREFLIGHT_READS_SQL,
        param_types=(),
        row_model=None,
        required_evidence_family="preflight",
        command_kind="SELECT",
    ),
)

IMPACT_QUERY_REGISTRY: Mapping[str, QuerySpec] = MappingProxyType(
    {spec.query_id: spec for spec in _IMPACT_SESSION_QUERY_SPECS}
)
