# Impact Demo-proof protocol (design §5.7)

**Status:** recording protocol for the private-repository prototype  
**Does not authorize:** publication, `PUBLICATION_APPROVED`, Foundation status change, or automated human study execution.

## Purpose

Provide redacted text reports for human Demo-proof using fixtures **T1**, **A4**, and **D2**, recorded against one commit and one PostgreSQL major.

Human criteria (design §5.7) remain **manual**:

```text
participants: 5 backend developers
not involved in implementation
no prior coaching
exact reports from recorded commit + PostgreSQL major
```

Comprehension check:

1. Can this merge as-is?
2. What is the main production risk?
3. What action is proposed before merge?
4. Would they run such a report themselves?

Success (thesis): all five understand the risk; ≥4 would run the tool before merge.

This document does **not** automate the human study.

## Recording inputs

Environment (never argv for credentials/admin DSN):

```text
PGINSPECT_TEST_DSN          admin DSN for fixture setup/teardown
PGINSPECT_RECORDING_MAJOR   expected live major (e.g. 16)
PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD
                            subject libpq env for pginspect impact
```

Unset `PGOPTIONS` so a leaked `search_path` cannot skew catalog resolution.

## Exact commands

```bash
python scripts/record_impact_demo.py --fixture T1 --out docs/superpowers/demos/recordings/T1.txt
python scripts/record_impact_demo.py --fixture A4 --out docs/superpowers/demos/recordings/A4.txt
python scripts/record_impact_demo.py --fixture D2 --out docs/superpowers/demos/recordings/D2.txt
```

`MANIFEST.json` stores `recorded_against_commit` = Task 14 HEAD. The Task 15 commit SHA is **not** written into the manifest.

## Redaction

Committed reports must not contain:

```text
password=
PGPASSWORD
:5432/
/home/
C:\
```

Diagnostic stderr sidecars (`*.stderr.txt`) are local-only and must not be committed.
