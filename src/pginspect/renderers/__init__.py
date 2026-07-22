"""Pure string renderers for CommandResult (no I/O, no connections)."""

from __future__ import annotations

from pginspect.renderers.json import render_json
from pginspect.renderers.text import escape_terminal_value, render_text, render_text_debug

__all__ = [
    "escape_terminal_value",
    "render_json",
    "render_text",
    "render_text_debug",
]
