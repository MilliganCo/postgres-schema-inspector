# Impact Demo-proof results — round 1

**Status:** pending  
**Formal sessions started:** no  
**Authorized scope:** docs-only internal draft — methodology lock before formal round

This file is an internal working document. Do not send the scoring rubric or expected
answers to participants. Do not include personal names, emails, or company names.

```text
Formal Demo-proof: not started
T1 / A4 / D2 recordings: unchanged
LLM dry-run: not part of formal sample
```

## Materials

```text
materials_sha: ea331adad1bf114d22c1c5d0877dbebd2467fafd
recorded_against_commit: 96d61a741a37710ae9e76c32cf75f7380bee86db
postgresql_major: 16

files:
  docs/superpowers/demos/recordings/T1.txt
  docs/superpowers/demos/recordings/A4.txt
  docs/superpowers/demos/recordings/D2.txt
```

## Eligibility criteria

A participant is eligible only when all of the following are true:

- backend developer
- PostgreSQL experience
- at least 3 migration reviews / approvals / production runs in the previous 12 months
- not involved in `pginspect` implementation
- has not previously seen the recordings or scoring answers

Screening happens before materials are sent. Failed screening is not a formal
Demo-proof session.

## Pilot — excluded

```text
P0 — pilot / excluded
qualification: insufficient migration-review experience
formal sample: excluded
observations retained for usability signal only:
  - T1 interpreted as possible data loss
  - D2 interpreted as potentially applicable
```

P0 answers are not scored against the formal pass criteria and do not count toward
`5/5` or `would use`.

## Formal participants

Use IDs `P1`–`P5` only. No names, emails, or companies.

Cell values for T1 / A4 / D2: `pass` | `fail` | `pending`  
Would use: `yes` | `no` | `unsure` | `pending`

| ID | Eligibility confirmed | T1 | A4 | D2 | Would use | Notes |
|----|-----------------------|----|----|----|-----------|-------|
| P1 | pending | pending | pending | pending | pending | |
| P2 | pending | pending | pending | pending | pending | |
| P3 | pending | pending | pending | pending | pending | |
| P4 | pending | pending | pending | pending | pending | |
| P5 | pending | pending | pending | pending | pending | |

## Raw responses

Store verbatim answers without personal data. Redact any accidental identifiers.

### P1

Eligibility confirmed:

#### T1

1.
2.
3.

#### A4

1.
2.
3.

#### D2

1.
2.
3.

Would use:  
Unclear terms:

### P2

Eligibility confirmed:

#### T1

1.
2.
3.

#### A4

1.
2.
3.

#### D2

1.
2.
3.

Would use:  
Unclear terms:

### P3

Eligibility confirmed:

#### T1

1.
2.
3.

#### A4

1.
2.
3.

#### D2

1.
2.
3.

Would use:  
Unclear terms:

### P4

Eligibility confirmed:

#### T1

1.
2.
3.

#### A4

1.
2.
3.

#### D2

1.
2.
3.

Would use:  
Unclear terms:

### P5

Eligibility confirmed:

#### T1

1.
2.
3.

#### A4

1.
2.
3.

#### D2

1.
2.
3.

Would use:  
Unclear terms:

## Internal scoring rubric

**Do not send this section to participants.**

```text
T1 pass:
  participant understands the statement can run,
  but requires a full rewrite and a heavy AccessExclusiveLock

A4 pass:
  participant understands the statement may fail
  when the table contains rows (NOT NULL without effective DEFAULT)

D2 pass:
  participant understands PostgreSQL rejects the statement
  under RESTRICT because of a catalog-proven dependency

Would-use pass cell:
  explicit "yes"
```

Different remediation advice is allowed. Exact SQL recipes are not required.
Main outcome and primary production risk must be correct.

## Pass / fail rule for the round

```text
Demo-proof passed:
  5/5 correctly understood T1, A4, and D2
  at least 4/5 answered "yes" to using the tool before merge/deploy

Demo-proof failed:
  at least one eligible participant misunderstood the primary risk
  OR fewer than 4 participants answered "yes" to using the tool
```

Complete all five formal sessions even if an early participant fails: remaining
answers are needed for diagnosis. Do not change recordings mid-round.

## Verdict

```text
Demo-proof: pending
risk understood: 0/5
would use yes: 0/5

next action after round closes:
  if passed  → product validation affirmed; plan next product stage
  if failed  → revise human-readable renderer, regenerate T1/A4/D2,
               run round 2 with five new eligible participants
```

## Constraints unchanged

```text
PUBLICATION_APPROVED=false
repository visibility=PRIVATE
Foundation A-10=open
ready_for_foundation_complete=false
legacy repository=not archived
release/PyPI=not authorized
```
