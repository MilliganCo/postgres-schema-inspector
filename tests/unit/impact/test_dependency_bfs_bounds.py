"""Bounded dependency BFS (design section 2.8): max edges + truncation flag."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pginspect.impact.catalog import MAX_DEPENDENCY_EDGES, gather_dependency_edges


class _ChainExecutor:
    """Simulates a long dependency chain: each visited node has exactly one child."""

    def __init__(self, chain_length: int) -> None:
        self._chain_length = chain_length

    def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None:
        raise AssertionError("fetch_one should not be used for dependency BFS")

    def fetch_all(self, query_id: str, params: tuple[Any, ...]) -> Sequence[Mapping[str, object]]:
        assert query_id == "impact.fetch_dependency_edges"
        refclassid, refobjid, refobjsubid, _limit = params
        next_objid = refobjid + 1
        if next_objid > self._chain_length:
            return ()
        return (
            {
                "classid": 2618,
                "objid": next_objid,
                "objsubid": 0,
                "refclassid": refclassid,
                "refobjid": refobjid,
                "refobjsubid": refobjsubid,
                "deptype": "n",
            },
        )


class _WideExecutor:
    """Simulates one root with many direct dependents in a single row batch."""

    def __init__(self, fanout: int) -> None:
        self._fanout = fanout
        self.calls = 0

    def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None:
        raise AssertionError("fetch_one should not be used for dependency BFS")

    def fetch_all(self, query_id: str, params: tuple[Any, ...]) -> Sequence[Mapping[str, object]]:
        self.calls += 1
        if self.calls > 1:
            return ()
        refclassid, refobjid, refobjsubid, _limit = params
        return tuple(
            {
                "classid": 1259,
                "objid": 1000 + i,
                "objsubid": 0,
                "refclassid": refclassid,
                "refobjid": refobjid,
                "refobjsubid": refobjsubid,
                "deptype": "a",
            }
            for i in range(self._fanout)
        )


def test_small_graph_is_complete_and_not_truncated() -> None:
    executor = _ChainExecutor(chain_length=3)
    edges, truncated = gather_dependency_edges(executor, roots=[(1259, 0, 0)], max_edges=10_000)
    assert len(edges) == 3
    assert truncated is False


def test_default_max_edges_matches_normative_bound() -> None:
    assert MAX_DEPENDENCY_EDGES == 10_000


def test_chain_longer_than_bound_is_truncated_at_exactly_max_edges() -> None:
    executor = _ChainExecutor(chain_length=50)
    edges, truncated = gather_dependency_edges(executor, roots=[(1259, 0, 0)], max_edges=10)
    assert len(edges) == 10
    assert truncated is True


def test_wide_fanout_beyond_bound_is_truncated() -> None:
    executor = _WideExecutor(fanout=25)
    edges, truncated = gather_dependency_edges(executor, roots=[(1259, 1, 0)], max_edges=10)
    assert len(edges) == 10
    assert truncated is True


def test_wide_fanout_within_bound_is_not_truncated() -> None:
    executor = _WideExecutor(fanout=5)
    edges, truncated = gather_dependency_edges(executor, roots=[(1259, 1, 0)], max_edges=10)
    assert len(edges) == 5
    assert truncated is False


def test_dependency_edge_bucket_classification_internal_automatic_and_default() -> None:
    class _OneShotExecutor:
        def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
            self._rows = rows
            self._served = False

        def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None:
            raise AssertionError("unused")

        def fetch_all(
            self, query_id: str, params: tuple[Any, ...]
        ) -> Sequence[Mapping[str, object]]:
            if self._served:
                return ()
            self._served = True
            return self._rows

    rows: tuple[Mapping[str, object], ...] = (
        {
            "classid": 1,
            "objid": 10,
            "objsubid": 0,
            "refclassid": 1259,
            "refobjid": 1,
            "refobjsubid": 0,
            "deptype": "i",
        },
        {
            "classid": 1,
            "objid": 11,
            "objsubid": 0,
            "refclassid": 1259,
            "refobjid": 1,
            "refobjsubid": 0,
            "deptype": "a",
        },
        {
            "classid": 1,
            "objid": 12,
            "objsubid": 0,
            "refclassid": 1259,
            "refobjid": 1,
            "refobjsubid": 0,
            "deptype": "n",
        },
    )
    executor = _OneShotExecutor(rows)
    edges, truncated = gather_dependency_edges(executor, roots=[(1259, 1, 0)], max_edges=10_000)
    assert truncated is False
    buckets = {edge.objid: edge.bucket for edge in edges}
    assert buckets[10] == "internal"
    assert buckets[11] == "automatic"
    assert buckets[12] == "external_blocking"


def test_gather_dependency_edges_deduplicates_visited_targets() -> None:
    """A diamond-shaped dependency graph must not be traversed twice from the same node."""

    class _DiamondExecutor:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int, int]] = []

        def fetch_one(self, query_id: str, params: tuple[Any, ...]) -> Mapping[str, object] | None:
            raise AssertionError("unused")

        def fetch_all(
            self, query_id: str, params: tuple[Any, ...]
        ) -> Sequence[Mapping[str, object]]:
            refclassid, refobjid, refobjsubid, _limit = params
            self.calls.append((refclassid, refobjid, refobjsubid))
            if (refclassid, refobjid, refobjsubid) == (1259, 1, 0):
                return (
                    {
                        "classid": 1259,
                        "objid": 2,
                        "objsubid": 0,
                        "refclassid": 1259,
                        "refobjid": 1,
                        "refobjsubid": 0,
                        "deptype": "n",
                    },
                    {
                        "classid": 1259,
                        "objid": 3,
                        "objsubid": 0,
                        "refclassid": 1259,
                        "refobjid": 1,
                        "refobjsubid": 0,
                        "deptype": "n",
                    },
                )
            if (refclassid, refobjid, refobjsubid) in {(1259, 2, 0), (1259, 3, 0)}:
                return (
                    {
                        "classid": 1259,
                        "objid": 4,
                        "objsubid": 0,
                        "refclassid": refclassid,
                        "refobjid": refobjid,
                        "refobjsubid": refobjsubid,
                        "deptype": "n",
                    },
                )
            return ()

    executor = _DiamondExecutor()
    edges, truncated = gather_dependency_edges(executor, roots=[(1259, 1, 0)], max_edges=10_000)
    assert truncated is False
    # (1259, 4, 0) is reached from both (1259,2,0) and (1259,3,0) but is only
    # ever visited (queried as a frontier node) once, not twice.
    node_4_visits = sum(1 for call in executor.calls if call == (1259, 4, 0))
    assert node_4_visits == 1
