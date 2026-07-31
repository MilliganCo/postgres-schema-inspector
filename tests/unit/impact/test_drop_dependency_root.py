"""DROP COLUMN dependency root uses live pg_class classoid (Layer D Blocker B)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pginspect.impact.catalog import (
    drop_column_dependency_root,
    fetch_pg_class_classoid,
    gather_dependency_edges,
)
from pginspect.impact.models.catalog_types import ColumnSnapshot, RelationSnapshot
from pginspect.impact.models.enums import AnalysisStatus
from pginspect.impact.parser.ast import (
    Identifier,
    QualifiedName,
    SourceSpan,
    SupportedAlterDrop,
    TableRef,
    Token,
    TokenKind,
)
from pginspect.impact.preflight import ResolutionContext
from pginspect.impact.resolve import RelationResolution
from pginspect.impact.run import _build_unit_for_statement
from pginspect.impact.models.result import ImpactConnectionContext


def _ident(name: str) -> Identifier:
    tok = Token(TokenKind.WORD, name, name.lower(), SourceSpan(1, 1, 0, len(name)))
    return Identifier(
        raw_token_private=tok,
        value=name,
        quoted=False,
        normalized_value=name.lower(),
        source_span=tok.span,
    )


def test_drop_column_dependency_root_requires_nonzero_classoid() -> None:
    root = drop_column_dependency_root(pg_class_classoid=1259, relation_oid=42, column_attnum=3)
    assert root == (1259, 42, 3)
    assert root[0] != 0
    assert root[2] != 0  # column-level, not relation-level objsubid=0


def test_drop_column_dependency_root_rejects_zero_classoid() -> None:
    with pytest.raises(ValueError, match="classoid"):
        drop_column_dependency_root(pg_class_classoid=0, relation_oid=42, column_attnum=3)


def test_drop_column_dependency_root_rejects_relation_level_objsubid() -> None:
    with pytest.raises(ValueError, match="attnum"):
        drop_column_dependency_root(pg_class_classoid=1259, relation_oid=42, column_attnum=0)


def test_fetch_pg_class_classoid_reads_registry_query() -> None:
    executor = MagicMock()
    executor.fetch_one.return_value = {"classoid": 1259}
    assert fetch_pg_class_classoid(executor) == 1259
    executor.fetch_one.assert_called_once_with("impact.fetch_pg_class_classoid", ())


def test_fetch_pg_class_classoid_missing_row_is_none() -> None:
    executor = MagicMock()
    executor.fetch_one.return_value = None
    assert fetch_pg_class_classoid(executor) is None


def test_gather_receives_classoid_objid_attnum_params() -> None:
    recorded: list[tuple[Any, ...]] = []

    class _Exec:
        def fetch_all(self, query_id: str, params: tuple[Any, ...]) -> list[dict[str, object]]:
            recorded.append((query_id, params))
            return []

        def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> None:
            return None

    edges, truncated = gather_dependency_edges(_Exec(), roots=((1259, 42, 3),), max_edges=10)
    assert edges == ()
    assert truncated is False
    assert recorded[0][0] == "impact.fetch_dependency_edges"
    classid, objid, objsubid, _limit = recorded[0][1]
    assert classid == 1259
    assert objid == 42
    assert objsubid == 3


def test_build_unit_passes_live_classoid_into_dependency_bfs() -> None:
    from pginspect.impact.parse_local import LocalStatement

    stmt = LocalStatement(
        statement_index=1,
        is_control=False,
        start_line=1,
        end_line=1,
        tokens=(),
        statement_fingerprint="sha256:0000000000000001",
        sanitized_preview="ALTER TABLE public.t DROP COLUMN c",
    )
    ast = SupportedAlterDrop(
        table=TableRef(
            if_exists=False,
            qualified_name=QualifiedName(
                schema=_ident("public"), name=_ident("t"), normalized="public.t"
            ),
        ),
        column=_ident("c"),
        if_exists=False,
        drop_behavior_written="default",
        effective_behavior="restrict",
    )
    relation = RelationSnapshot(
        oid=42,
        nspname="public",
        relname="t",
        relkind="r",
        relpersistence="p",
        relispartition=False,
        inherits_parents=(),
        inherits_children=(),
        columns=(
            ColumnSnapshot(
                attnum=3,
                attname="c",
                type_oid=23,
                typmod=-1,
                attndims=0,
                attnotnull=False,
                attisdropped=False,
                identity="",
                generated="",
                default_bin=None,
                collation_oid=None,
            ),
        ),
        indexes=(),
        constraints=(),
    )
    context = ResolutionContext(
        database="db",
        role="r",
        session_user="r",
        current_schema="public",
        current_schemas_user=("public",),
        current_schemas_with_implicit=("pg_catalog", "public"),
        search_path_raw='"public"',
        max_identifier_length_bytes=63,
        server_major=16,
        server_version_num=160000,
        keyword_categories={},
    )
    connection_context = ImpactConnectionContext(
        server_version="16.0",
        server_version_num=160000,
        server_major=16,
        database="db",
        role="r",
        session_user="r",
        current_schema="public",
        search_path_raw='"public"',
        standard_conforming_strings="on",
        server_encoding="UTF8",
        client_encoding="UTF8",
        transaction_isolation="repeatable read",
        transaction_read_only="on",
        in_recovery=False,
        max_identifier_length=63,
    )
    recorded_roots: list[tuple[int, int, int]] = []

    class _Exec:
        def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> dict[str, object] | None:
            if query_id == "impact.fetch_pg_class_classoid":
                return {"classoid": 1259}
            if query_id == "impact.fetch_relation_metrics":
                return None
            return None

        def fetch_all(self, query_id: str, params: tuple[Any, ...]) -> list[dict[str, object]]:
            if query_id == "impact.fetch_dependency_edges":
                recorded_roots.append((params[0], params[1], params[2]))
            return []

    from unittest.mock import patch

    with (
        patch("pginspect.impact.run.classify_noncontrol_statement", return_value=ast),
        patch(
            "pginspect.impact.run.resolve_relation",
            return_value=RelationResolution("resolved", 42, "public", "t", None),
        ),
        patch("pginspect.impact.run.fetch_relation_snapshot", return_value=relation),
        patch("pginspect.impact.run.fetch_relation_metrics", return_value=None),
        patch(
            "pginspect.impact.run.gather_dependency_edges",
            side_effect=lambda executor, roots, max_edges=10_000: (
                recorded_roots.extend(roots) or ((), False)
            ),
        ),
    ):
        unit = _build_unit_for_statement(
            stmt,
            context=context,
            executor=_Exec(),
            connection_context=connection_context,
        )

    assert unit.analysis_status is AnalysisStatus.ANALYZED
    assert recorded_roots == [(1259, 42, 3)]


def test_missing_classoid_yields_unsupported_evidence_without_bfs() -> None:
    from pginspect.impact.parse_local import LocalStatement
    from unittest.mock import patch

    stmt = LocalStatement(
        statement_index=1,
        is_control=False,
        start_line=1,
        end_line=1,
        tokens=(),
        statement_fingerprint="sha256:0000000000000001",
        sanitized_preview="ALTER TABLE public.t DROP COLUMN c",
    )
    ast = SupportedAlterDrop(
        table=TableRef(
            if_exists=False,
            qualified_name=QualifiedName(
                schema=_ident("public"), name=_ident("t"), normalized="public.t"
            ),
        ),
        column=_ident("c"),
        if_exists=False,
        drop_behavior_written="default",
        effective_behavior="restrict",
    )
    relation = RelationSnapshot(
        oid=42,
        nspname="public",
        relname="t",
        relkind="r",
        relpersistence="p",
        relispartition=False,
        inherits_parents=(),
        inherits_children=(),
        columns=(
            ColumnSnapshot(
                attnum=3,
                attname="c",
                type_oid=23,
                typmod=-1,
                attndims=0,
                attnotnull=False,
                attisdropped=False,
                identity="",
                generated="",
                default_bin=None,
                collation_oid=None,
            ),
        ),
        indexes=(),
        constraints=(),
    )
    context = ResolutionContext(
        database="db",
        role="r",
        session_user="r",
        current_schema="public",
        current_schemas_user=("public",),
        current_schemas_with_implicit=("pg_catalog", "public"),
        search_path_raw='"public"',
        max_identifier_length_bytes=63,
        server_major=16,
        server_version_num=160000,
        keyword_categories={},
    )
    connection_context = ImpactConnectionContext(
        server_version="16.0",
        server_version_num=160000,
        server_major=16,
        database="db",
        role="r",
        session_user="r",
        current_schema="public",
        search_path_raw='"public"',
        standard_conforming_strings="on",
        server_encoding="UTF8",
        client_encoding="UTF8",
        transaction_isolation="repeatable read",
        transaction_read_only="on",
        in_recovery=False,
        max_identifier_length=63,
    )
    bfs = MagicMock()

    with (
        patch("pginspect.impact.run.classify_noncontrol_statement", return_value=ast),
        patch(
            "pginspect.impact.run.resolve_relation",
            return_value=RelationResolution("resolved", 42, "public", "t", None),
        ),
        patch("pginspect.impact.run.fetch_relation_snapshot", return_value=relation),
        patch("pginspect.impact.run.fetch_relation_metrics", return_value=None),
        patch("pginspect.impact.run.fetch_pg_class_classoid", return_value=None),
        patch("pginspect.impact.run.gather_dependency_edges", bfs),
    ):
        unit = _build_unit_for_statement(
            stmt,
            context=context,
            executor=MagicMock(),
            connection_context=connection_context,
        )

    assert unit.analysis_status is AnalysisStatus.UNSUPPORTED_EVIDENCE
    bfs.assert_not_called()
