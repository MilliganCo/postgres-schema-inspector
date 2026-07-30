"""Unit tests for `impact.catalog` gatherers (design section 2.8).

Fully mocked `QueryExecutor`: no live PostgreSQL. Verifies the row-to-
snapshot mapping for RelationSnapshot/TypeSnapshot/FunctionSnapshot/
RelationMetrics and that missing rows surface as `None` rather than being
silently invented.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pginspect.impact.catalog import (
    fetch_function_snapshot,
    fetch_pg_cast_rows,
    fetch_relation_metrics,
    fetch_relation_snapshot,
    fetch_type_snapshot,
)
from pginspect.impact.models.catalog_types import PgCastRow


class _FakeExecutor:
    def __init__(
        self,
        one_responses: Mapping[str, Mapping[str, object] | None] | None = None,
        all_responses: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    ) -> None:
        self._one = one_responses or {}
        self._all = all_responses or {}
        self.fetch_one_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None:
        self.fetch_one_calls.append((query_id, params))
        return self._one.get(query_id)

    def fetch_all(self, query_id: str, params: tuple[Any, ...]) -> Sequence[Mapping[str, object]]:
        self.fetch_all_calls.append((query_id, params))
        return self._all.get(query_id, ())


_RELATION_ROW: dict[str, object] = {
    "oid": 100,
    "nspname": "impact_t1",
    "relname": "t",
    "relkind": "r",
    "relpersistence": "p",
    "relispartition": False,
    "inherits_parents": [],
    "inherits_children": [],
}

_COLUMN_ROW: dict[str, object] = {
    "attnum": 2,
    "attname": "payload",
    "type_oid": 23,
    "typmod": -1,
    "attndims": 0,
    "attnotnull": True,
    "attisdropped": False,
    "identity": "",
    "generated": "",
    "default_bin": None,
    "collation_oid": None,
}

_INDEX_ROW: dict[str, object] = {
    "oid": 200,
    "nspname": "impact_t1",
    "relname": "impact_t1_payload_idx",
    "indrelid": 100,
    "indisunique": False,
    "indisprimary": False,
    "indisexclusion": False,
    "indkey_attnums": [2],
    "indisvalid": True,
    "predicate_present": False,
    "is_constraint_backed": False,
}

_CONSTRAINT_ROW: dict[str, object] = {
    "oid": 300,
    "conname": "t_pkey",
    "contype": "p",
    "conrelid": 100,
    "confrelid": 0,
    "conkey_attnums": [1],
    "confkey_attnums": [],
    "confupdtype": " ",
    "confdeltype": " ",
}


def test_fetch_relation_snapshot_assembles_columns_indexes_constraints() -> None:
    executor = _FakeExecutor(
        one_responses={"impact.fetch_relation": _RELATION_ROW},
        all_responses={
            "impact.fetch_columns": [_COLUMN_ROW],
            "impact.fetch_indexes": [_INDEX_ROW],
            "impact.fetch_constraints": [_CONSTRAINT_ROW],
        },
    )
    snapshot = fetch_relation_snapshot(executor, 100)
    assert snapshot is not None
    assert snapshot.oid == 100
    assert snapshot.nspname == "impact_t1"
    assert snapshot.relkind == "r"
    assert len(snapshot.columns) == 1
    assert snapshot.columns[0].attname == "payload"
    assert snapshot.columns[0].attnotnull is True
    assert len(snapshot.indexes) == 1
    assert snapshot.indexes[0].relname == "impact_t1_payload_idx"
    assert snapshot.indexes[0].indkey_attnums == (2,)
    assert len(snapshot.constraints) == 1
    assert snapshot.constraints[0].contype == "p"
    assert executor.fetch_one_calls == [("impact.fetch_relation", (100,))]


def test_fetch_relation_snapshot_returns_none_when_relation_missing() -> None:
    executor = _FakeExecutor(one_responses={"impact.fetch_relation": None})
    assert fetch_relation_snapshot(executor, 999) is None
    # Missing core row must short-circuit: no wasted column/index/constraint reads.
    assert executor.fetch_all_calls == []


_TYPE_ROW: dict[str, object] = {
    "oid": 23,
    "nspname": "pg_catalog",
    "typname": "int4",
    "typtype": "b",
    "typcategory": "N",
    "typbasetype": 0,
    "typelem": 0,
    "typarray": 1007,
    "typndims": 0,
    "typtypmod": -1,
    "typlen": 4,
    "typbyval": True,
    "typalign": "i",
    "typcollation": 0,
    "typdefaultbin": None,
    "typdefault": None,
    "domain_not_null": False,
}

_DOMAIN_CONSTRAINT_ROW: dict[str, object] = {
    "oid": 400,
    "conname": "positive_amount",
    "contype": "c",
    "conbin_present": True,
}


def test_fetch_type_snapshot_base_type_has_no_domain_constraints() -> None:
    executor = _FakeExecutor(
        one_responses={"impact.fetch_type": _TYPE_ROW},
        all_responses={"impact.fetch_domain_constraints": []},
    )
    snapshot = fetch_type_snapshot(executor, 23)
    assert snapshot is not None
    assert snapshot.typname == "int4"
    assert snapshot.typtype == "b"
    assert snapshot.domain_constraints == ()


def test_fetch_type_snapshot_domain_type_includes_constraints() -> None:
    domain_row = {
        **_TYPE_ROW,
        "oid": 50000,
        "typname": "positive_int",
        "typtype": "d",
        "typbasetype": 23,
    }
    executor = _FakeExecutor(
        one_responses={"impact.fetch_type": domain_row},
        all_responses={"impact.fetch_domain_constraints": [_DOMAIN_CONSTRAINT_ROW]},
    )
    snapshot = fetch_type_snapshot(executor, 50000)
    assert snapshot is not None
    assert snapshot.typtype == "d"
    assert len(snapshot.domain_constraints) == 1
    assert snapshot.domain_constraints[0].conname == "positive_amount"
    assert snapshot.domain_constraints[0].conbin_present is True


def test_fetch_type_snapshot_returns_none_when_missing() -> None:
    executor = _FakeExecutor(one_responses={"impact.fetch_type": None})
    assert fetch_type_snapshot(executor, 999999) is None


_FUNCTION_ROW: dict[str, object] = {
    "oid": 9999,
    "nspname": "pg_catalog",
    "proname": "clock_timestamp",
    "proargtypes": [],
    "prorettype": 1184,
    "provolatile": "v",
    "prokind": "f",
}


def test_fetch_function_snapshot_volatile_clock_timestamp() -> None:
    executor = _FakeExecutor(one_responses={"impact.fetch_function": _FUNCTION_ROW})
    snapshot = fetch_function_snapshot(executor, 9999)
    assert snapshot is not None
    assert snapshot.proname == "clock_timestamp"
    assert snapshot.provolatile == "v"


def test_fetch_function_snapshot_returns_none_when_missing() -> None:
    executor = _FakeExecutor(one_responses={"impact.fetch_function": None})
    assert fetch_function_snapshot(executor, 1) is None


def test_fetch_relation_metrics_maps_n_live_tup_null_to_none() -> None:
    executor = _FakeExecutor(
        one_responses={
            "impact.fetch_relation_metrics": {
                "pg_relation_size": 8192,
                "pg_total_relation_size": 16384,
                "indexes_size": 8192,
                "n_live_tup": None,
            }
        }
    )
    metrics = fetch_relation_metrics(executor, 100)
    assert metrics is not None
    assert metrics.pg_relation_size == 8192
    assert metrics.n_live_tup is None
    assert metrics.stats_freshness == "estimated"


def test_fetch_pg_cast_rows_never_fabricates_a_row_when_none_exist() -> None:
    executor = _FakeExecutor(all_responses={"impact.fetch_pg_cast": []})
    rows = fetch_pg_cast_rows(executor, 25, 23)
    assert rows == ()
    assert executor.fetch_all_calls == [("impact.fetch_pg_cast", (25, 23))]


def test_fetch_pg_cast_rows_maps_live_row() -> None:
    executor = _FakeExecutor(
        all_responses={
            "impact.fetch_pg_cast": [
                {
                    "castsource": 25,
                    "casttarget": 1043,
                    "castfunc": 0,
                    "castcontext": "i",
                    "castmethod": "b",
                }
            ]
        }
    )
    rows = fetch_pg_cast_rows(executor, 25, 1043)
    assert rows == (
        PgCastRow(castsource=25, casttarget=1043, castfunc=0, castcontext="i", castmethod="b"),
    )
