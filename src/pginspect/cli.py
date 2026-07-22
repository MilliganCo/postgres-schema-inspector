from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Stub until Task 13. Returns 0 for --help-less version probe if needed."""
    from pginspect._version import get_app_version

    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv[0] in {"version", "--version"}:
        print(f"pginspect {get_app_version()}")
        return 0
    print("CLI not fully implemented yet", file=sys.stderr)
    return 4
