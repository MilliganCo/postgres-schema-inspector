from __future__ import annotations

from pginspect.impact.analysis_unit import AnalysisUnit, AnalysisUnitFamily, SourceSpan
from pginspect.impact.models.enums import AnalysisStatus
from pginspect.impact.sequence import SEQUENCE_DEPENDENCY_LIMITATION, apply_sequence_constraints


def _unit(
    *,
    statement_index: int,
    family: AnalysisUnitFamily,
    analysis_status: AnalysisStatus = AnalysisStatus.ANALYZED,
    table_oid: int | None = 10,
    table_schema: str | None = "public",
    table_name: str | None = "t",
    column_attnum: int | None = None,
    column_normalized_name: str | None = "x",
    limitations: tuple[str, ...] = (),
) -> AnalysisUnit:
    return AnalysisUnit(
        statement_index=statement_index,
        source_span=SourceSpan(statement_index, statement_index, 0, 10),
        statement_fingerprint=f"sha256:{statement_index:016d}",
        sanitized_preview=f"statement {statement_index}",
        family=family,
        ast=object(),
        analysis_status=analysis_status,
        table_oid=table_oid,
        table_schema=table_schema,
        table_name=table_name,
        column_attnum=column_attnum,
        column_normalized_name=column_normalized_name,
        resolution_payload=None,
        evidence_ids=(),
        requires_virtual_schema_state=False,
        limitations=limitations,
    )


def test_add_then_alter_same_table_oid_and_column() -> None:
    span = SourceSpan(1, 1, 0, 10)
    u1 = AnalysisUnit(
        statement_index=1,
        source_span=span,
        statement_fingerprint="sha256:aaaaaaaaaaaaaaaa",
        sanitized_preview="ALTER TABLE t ADD COLUMN x int",
        family="add",
        ast=object(),
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=10,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="x",
        resolution_payload=None,
        evidence_ids=(),
        requires_virtual_schema_state=True,
        limitations=(),
    )
    u2 = AnalysisUnit(
        statement_index=2,
        source_span=SourceSpan(2, 2, 11, 20),
        statement_fingerprint="sha256:bbbbbbbbbbbbbbbb",
        sanitized_preview="ALTER TABLE t ALTER COLUMN x TYPE text",
        family="type",
        ast=object(),
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=10,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="x",
        resolution_payload=None,
        evidence_ids=(),
        requires_virtual_schema_state=False,
        limitations=(),
    )
    out = apply_sequence_constraints((u1, u2))
    assert out[0].analysis_status == AnalysisStatus.ANALYZED
    assert out[1].analysis_status == AnalysisStatus.UNSUPPORTED_SEQUENCE


def test_add_then_drop_same_column_marks_the_drop() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="add"),
            _unit(statement_index=2, family="drop"),
        )
    )
    assert out[0].analysis_status is AnalysisStatus.ANALYZED
    assert out[1].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE


def test_drop_then_later_reference_to_same_column_is_unsupported_sequence() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="drop"),
            _unit(statement_index=2, family="type"),
        )
    )
    assert out[0].analysis_status is AnalysisStatus.ANALYZED
    assert out[1].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE


def test_drop_then_re_add_same_column_is_unsupported_sequence() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="drop"),
            _unit(statement_index=2, family="add"),
        )
    )
    assert out[1].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE


def test_type_then_later_type_on_same_column_is_unsupported_sequence() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="type"),
            _unit(statement_index=2, family="type"),
        )
    )
    assert out[0].analysis_status is AnalysisStatus.ANALYZED
    assert out[1].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE


def test_type_then_later_drop_on_same_column_is_unsupported_sequence() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="type"),
            _unit(statement_index=2, family="drop"),
        )
    )
    assert out[1].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE


def test_every_later_dependent_in_a_chain_is_marked() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="add"),
            _unit(statement_index=2, family="type"),
            _unit(statement_index=3, family="drop"),
        )
    )
    assert [unit.analysis_status for unit in out] == [
        AnalysisStatus.ANALYZED,
        AnalysisStatus.UNSUPPORTED_SEQUENCE,
        AnalysisStatus.UNSUPPORTED_SEQUENCE,
    ]


def test_different_columns_on_same_table_stay_analyzed() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="add", column_normalized_name="x"),
            _unit(statement_index=2, family="type", column_normalized_name="y"),
        )
    )
    assert [unit.analysis_status for unit in out] == [
        AnalysisStatus.ANALYZED,
        AnalysisStatus.ANALYZED,
    ]


def test_same_column_name_on_different_tables_stays_analyzed() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="add", table_oid=10, table_name="t"),
            _unit(statement_index=2, family="type", table_oid=11, table_name="other"),
        )
    )
    assert [unit.analysis_status for unit in out] == [
        AnalysisStatus.ANALYZED,
        AnalysisStatus.ANALYZED,
    ]


def test_column_attnum_identity_matches_when_names_differ() -> None:
    out = apply_sequence_constraints(
        (
            _unit(
                statement_index=1,
                family="type",
                column_attnum=3,
                column_normalized_name="x",
            ),
            _unit(
                statement_index=2,
                family="drop",
                column_attnum=3,
                column_normalized_name="renamed",
            ),
        )
    )
    assert out[1].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE


def test_qualified_name_identity_is_used_when_table_oid_is_missing() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="add", table_oid=None),
            _unit(statement_index=2, family="type", table_oid=None),
        )
    )
    assert out[1].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE


def test_units_without_any_identity_never_match() -> None:
    out = apply_sequence_constraints(
        (
            _unit(
                statement_index=1,
                family="add",
                table_oid=None,
                table_schema=None,
                table_name=None,
                column_normalized_name=None,
            ),
            _unit(
                statement_index=2,
                family="type",
                table_oid=None,
                table_schema=None,
                table_name=None,
                column_normalized_name=None,
            ),
        )
    )
    assert [unit.analysis_status for unit in out] == [
        AnalysisStatus.ANALYZED,
        AnalysisStatus.ANALYZED,
    ]


def test_unsupported_parser_prior_unit_is_not_a_mutator() -> None:
    out = apply_sequence_constraints(
        (
            _unit(
                statement_index=1,
                family="unsupported_parser",
                analysis_status=AnalysisStatus.UNSUPPORTED_PARSER,
            ),
            _unit(statement_index=2, family="type"),
        )
    )
    assert out[1].analysis_status is AnalysisStatus.ANALYZED


def test_already_unsupported_later_unit_keeps_its_original_status() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="add"),
            _unit(
                statement_index=2,
                family="type",
                analysis_status=AnalysisStatus.UNSUPPORTED_RESOLUTION,
            ),
        )
    )
    assert out[1].analysis_status is AnalysisStatus.UNSUPPORTED_RESOLUTION
    assert out[1].limitations == ()


def test_marked_unit_preserves_every_other_field() -> None:
    prior = _unit(statement_index=1, family="add")
    later = _unit(statement_index=2, family="type")
    out = apply_sequence_constraints((prior, later))
    marked = out[1]
    assert marked.statement_index == 2
    assert marked.source_span == later.source_span
    assert marked.statement_fingerprint == later.statement_fingerprint
    assert marked.sanitized_preview == later.sanitized_preview
    assert marked.family == later.family
    assert marked.ast is later.ast
    assert marked.table_oid == later.table_oid
    assert marked.column_normalized_name == later.column_normalized_name
    assert marked.evidence_ids == later.evidence_ids


def test_marked_unit_gains_the_sequence_limitation_once() -> None:
    out = apply_sequence_constraints(
        (
            _unit(statement_index=1, family="add"),
            _unit(
                statement_index=2,
                family="type",
                limitations=(SEQUENCE_DEPENDENCY_LIMITATION,),
            ),
            _unit(statement_index=3, family="drop", limitations=("pre-existing",)),
        )
    )
    assert out[0].limitations == ()
    assert out[1].limitations == (SEQUENCE_DEPENDENCY_LIMITATION,)
    assert out[2].limitations == ("pre-existing", SEQUENCE_DEPENDENCY_LIMITATION)


def test_units_are_ordered_by_statement_index_not_input_position() -> None:
    later = _unit(statement_index=2, family="type")
    prior = _unit(statement_index=1, family="add")
    out = apply_sequence_constraints((later, prior))
    assert out[0].statement_index == 2
    assert out[0].analysis_status is AnalysisStatus.UNSUPPORTED_SEQUENCE
    assert out[1].statement_index == 1
    assert out[1].analysis_status is AnalysisStatus.ANALYZED


def test_empty_input_returns_empty_tuple() -> None:
    assert apply_sequence_constraints(()) == ()


def test_single_unit_is_returned_unchanged() -> None:
    only = _unit(statement_index=1, family="type")
    assert apply_sequence_constraints((only,)) == (only,)
