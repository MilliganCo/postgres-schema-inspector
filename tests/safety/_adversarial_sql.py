"""Adversarial write SQL for safety probes (test-only; not packaged in the wheel).

Each statement targets ``pginspect_probe.write_probe`` (or creates a throwaway
table in that schema). Subject role has real write grants so failures must be
SQLSTATE ``25006`` (read-only transaction), never ``42501``.
"""

from __future__ import annotations

from typing import Final

# Expected SQLSTATE when DiagnosticSession has established read-only transaction.
READONLY_SQLSTATE: Final[str] = "25006"

ADVERSARIAL_PROBES: Final[tuple[tuple[str, str], ...]] = (
    (
        "insert",
        "INSERT INTO pginspect_probe.write_probe (id, payload) VALUES (999, 'adversarial')",
    ),
    (
        "update",
        "UPDATE pginspect_probe.write_probe SET payload = 'adversarial' WHERE id = 1",
    ),
    (
        "delete",
        "DELETE FROM pginspect_probe.write_probe WHERE id = 1",
    ),
    (
        "truncate",
        "TRUNCATE TABLE pginspect_probe.write_probe",
    ),
    (
        "create_table",
        "CREATE TABLE pginspect_probe.adversarial_tmp (id integer PRIMARY KEY)",
    ),
)
