"""JSON renderer for CommandResult (canonical Foundation presentation)."""

from __future__ import annotations

import json
from typing import cast

from pginspect.models.result import CommandResult, command_result_adapter


def render_json(result: CommandResult) -> str:
    """Serialize ``result`` as one JSON object with indent=2, sorted keys, trailing newline."""
    payload = command_result_adapter.dump_python(result, mode="json")
    return (
        json.dumps(
            cast(object, payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
