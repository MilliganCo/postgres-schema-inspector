"""ResolutionContext contract and pure preflight evaluation gates.

This module must not import psycopg or hold any connection/cursor state; the
DB-facing session establishment lives in `pginspect.session`. Only PostgreSQL
majors 14 through 18 are in scope for change-impact analysis (design section
2 / plan Task 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pginspect.impact.models.result import ImpactConnectionContext

SUPPORTED_SERVER_MAJORS: frozenset[int] = frozenset({14, 15, 16, 17, 18})

_EXPECTED_TRANSACTION_ISOLATION = "repeatable read"
_EXPECTED_ENCODING = "UTF8"
_ON = "on"


@dataclass(frozen=True)
class ResolutionContext:
    """Facts captured before search_path is hardened to `pg_catalog`.

    `current_schemas_user` excludes the implicit `pg_catalog` entry
    (`current_schemas(false)`); `current_schemas_with_implicit` includes it
    (`current_schemas(true)`) and is what unqualified-name resolution ranks
    against (design section 2).
    """

    database: str
    role: str
    session_user: str
    current_schema: str | None
    current_schemas_user: tuple[str, ...]
    current_schemas_with_implicit: tuple[str, ...]
    search_path_raw: str
    max_identifier_length_bytes: int
    server_major: int
    server_version_num: int
    keyword_categories: Mapping[str, str]


@dataclass(frozen=True)
class PreflightGateFailure:
    check_id: str
    detail: str


@dataclass(frozen=True)
class PreflightEvaluation:
    incomplete: bool
    failures: tuple[PreflightGateFailure, ...]


def evaluate_preflight_gates(context: ImpactConnectionContext) -> PreflightEvaluation:
    """Evaluate the normative Task-4 preflight incompleteness gates.

    Incomplete when: unsupported `server_major`; `standard_conforming_strings`
    is not `on`; `transaction_read_only` is not `on`; `transaction_isolation`
    is not `repeatable read`; or either encoding is not `UTF8`.
    """
    failures: list[PreflightGateFailure] = []

    if context.server_major not in SUPPORTED_SERVER_MAJORS:
        failures.append(
            PreflightGateFailure(
                check_id="server_major",
                detail=f"unsupported server_major={context.server_major}",
            )
        )
    if context.standard_conforming_strings != _ON:
        failures.append(
            PreflightGateFailure(
                check_id="standard_conforming_strings",
                detail=(f"standard_conforming_strings={context.standard_conforming_strings}"),
            )
        )
    if context.transaction_read_only != _ON:
        failures.append(
            PreflightGateFailure(
                check_id="transaction_read_only",
                detail=f"transaction_read_only={context.transaction_read_only}",
            )
        )
    if context.transaction_isolation != _EXPECTED_TRANSACTION_ISOLATION:
        failures.append(
            PreflightGateFailure(
                check_id="transaction_isolation",
                detail=f"transaction_isolation={context.transaction_isolation}",
            )
        )
    if (
        context.server_encoding != _EXPECTED_ENCODING
        or context.client_encoding != _EXPECTED_ENCODING
    ):
        failures.append(
            PreflightGateFailure(
                check_id="encoding",
                detail=(
                    f"server_encoding={context.server_encoding} "
                    f"client_encoding={context.client_encoding}"
                ),
            )
        )

    return PreflightEvaluation(incomplete=bool(failures), failures=tuple(failures))
