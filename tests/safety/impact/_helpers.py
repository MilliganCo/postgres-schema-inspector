"""Shared helpers for impact safety gates (plan Task 13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pginspect.impact.query_exec import QueryExecutionEvent
from pginspect.impact.queries import IMPACT_QUERY_REGISTRY

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "impact"
CANARY_MIGRATION = (
    "ALTER TABLE impact_t1.t ALTER COLUMN payload TYPE text; "
    "-- CANARY_MIGRATION_MUST_NEVER_EXECUTE"
)


@dataclass
class RecordingBag:
    events: list[QueryExecutionEvent] = field(default_factory=list)

    def __call__(self, event: QueryExecutionEvent) -> None:
        self.events.append(event)


def canary_migration_path(tmp_path: Path) -> Path:
    path = tmp_path / "canary_migration.sql"
    path.write_text(CANARY_MIGRATION + "\n", encoding="utf-8")
    return path


def assert_migration_absent_from_sql(events: list[QueryExecutionEvent]) -> None:
    for event in events:
        assert "CANARY_MIGRATION_MUST_NEVER_EXECUTE" not in event.sql_text
        assert "ALTER TABLE impact_t1.t ALTER COLUMN payload TYPE text" not in event.sql_text
        assert event.sql_text == IMPACT_QUERY_REGISTRY[event.query_id].sql


def assert_allowlisted(events: list[QueryExecutionEvent]) -> None:
    for event in events:
        assert event.query_id in IMPACT_QUERY_REGISTRY
        assert event.sql_text is IMPACT_QUERY_REGISTRY[event.query_id].sql or (
            event.sql_text == IMPACT_QUERY_REGISTRY[event.query_id].sql
        )


def install_executor_recorder(monkeypatch: Any, recorder: RecordingBag) -> None:
    """Record every allowlisted execution without changing production source."""
    from pginspect.impact import query_exec
    import pginspect.session as session_mod

    original = query_exec.execute_allowlisted

    def wrapped(session: Any, query_id: str, params: tuple[Any, ...] = (), **kwargs: Any) -> Any:
        kwargs = dict(kwargs)
        prior = kwargs.get("recorder")

        def combined(event: QueryExecutionEvent) -> None:
            recorder(event)
            if prior is not None:
                prior(event)

        kwargs["recorder"] = combined
        return original(session, query_id, params, **kwargs)

    monkeypatch.setattr(query_exec, "execute_allowlisted", wrapped)
    monkeypatch.setattr(session_mod, "execute_allowlisted", wrapped)
