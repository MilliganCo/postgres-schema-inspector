# pginspect Change Impact — Product Thesis & Discovery Design

**Date:** 2026-07-22 (amended 2026-07-23)  
**Status:** approved product thesis (pre-design)  
**Command concept:** `pginspect impact`  
**Related:** Foundation remains **code-complete** until private remote, GHA PG 14–18, and human gates close `FOUNDATION_COMPLETE`. This document does not authorize product implementation beyond discovery planning.

---

## 1. Problem

A backend developer without a dedicated DBA authors `migration.sql` and, before merge or deploy, cannot confidently answer:

- Will this take a dangerous lock?
- Will it rewrite a large table?
- Which dependencies will block the change, be dropped via `CASCADE`, or require a coordinated rollout?
- Is there a safer expand/contract path?

Existing tooling often monitors a live database or lints SQL style. It less often answers: **what will this proposed change do to this live schema before it runs?**

**Market hypothesis (not a proven market fact):** existing tools do not combine *proposed migration + live catalog + explainable pre-execution impact* well enough for this job-to-be-done.

---

## 2. Target user

### Primary

**Backend developer without a dedicated DBA.**

- Concrete input: `migration.sql`
- Concrete fear: lock, rewrite, downtime, painful rollback
- Moment of use: before merge or before deploy
- Value is visible without a monitoring stack

### Job-to-be-done

> Before merging a migration, understand whether it may block production, rewrite a large table, hit dependency walls, or require a safer staged rollout plan.

### Secondary readers of the same report

- **Tech lead / reviewer** — PR review gate
- **Platform / SRE** — release risk gate

---

## 3. Product direction

### Differentiator (hypothesis-led)

Not another general `doctor` / health checklist.

**Change-first diagnostics:**

```text
proposed change + live schema → consequences before execution
```

### First interface

```text
pginspect impact migration.sql [connection options]
```

### Explicitly not the first product core

- General `pginspect doctor` as the hero feature
- HypoPG / Index Lab as the entry wedge
- Workload monitoring daemon
- AI-generated SQL execution
- Automatic apply / executable generated migrations
- Full SQL migration engine

---

## 4. Discovery stages (locked)

| Stage | Decision |
| --- | --- |
| 1. User | Backend without DBA (primary) |
| 2. Three migration families | See §5 |
| 3. Inputs | Live read-only PostgreSQL + local `migration.sql` |
| 4. Report | Summary + per-statement cards; JSON for CI |
| 5. Prototype engine | Parser + live catalog only |
| 6. Thesis success | Demo-proof (§8); accuracy-first later |

---

## 5. Three demo migration families

### 5.1 `ALTER TABLE ... ALTER COLUMN ... TYPE`

Show:

- predicted lock level
- table rewrite risk
- affected indexes / constraints
- safer expand/contract path (recommendation only)

### 5.2 `ALTER TABLE ... ADD COLUMN ... DEFAULT / NOT NULL`

Show:

- PostgreSQL version sensitivity
- default expression class
- metadata-only vs scan/rewrite paths
- staged rollout when needed

### 5.3 `ALTER TABLE ... DROP COLUMN` (primary dependency demo)

Show catalog dependencies: views, constraints, functions, and related ownership edges.

**Optional add-on:** limited `DROP INDEX` analysis for constraint ownership and catalog dependencies only.  
Do **not** claim which live queries use the index without workload data.

---

## 6. Inputs and hard boundaries (MVP)

### Required

```text
migration.sql          required
live PostgreSQL        required
connection             read-only diagnostic session (Foundation layer)
```

### Forbidden in MVP

```text
executing the migration
creating temporary objects / dry-run DDL
EXPLAIN as the impact engine
workload / pg_stat_statements analysis
HypoPG
schema-dump / offline fallback
```

**Offline/degraded mode** may be a later product mode; it is out of this thesis and must not drive architecture now.

### Evidence sources

```text
migration.sql
+ live catalog snapshot
→ impact report
```

Predictions are based on SQL syntax, PostgreSQL version, and catalog evidence. The product must expose **confidence** and **limitations**. Absolute certainty of lock/rewrite behavior is not promised.

### Version matrix (first prototype)

PostgreSQL **14–18**, aligned with Foundation support. Other majors are out of prototype scope.

---

## 7. Impact report shape

### Text UX

```text
Summary
  overall_risk
  critical_count
  warning_count
  statement_count
  exit_code

Statement N
  SQL
  Risk: critical | warning | safe | unsupported
  Lock: ...
  Table rewrite: yes | no | possible
  Affected objects: ...
  Why: ...
  Safer rollout: ...   # advisory only
```

### JSON UX

Stable machine-readable per-statement report for CI / PR automation.

### Schema policy (deliberately non-premature)

Foundation schemas `1.0` remain **immutable**.  
`impact` receives a separate versioned contract and/or new minor schema versions. Exact model shapes are deferred to the **impact design** document.

### Incomplete analysis

An `unsupported` (or otherwise unanalyzed) statement must **not** yield a green success:

- the report is **incomplete**
- exit code must **not** be `0`
- provisional safe choice until impact design: **exit `3`** (analysis could not complete)
- precise `outcome` / model validators belong in the next design-spec

### Exit policy (provisional, Foundation-aligned)

```text
0   no risks found; analysis complete
1   warnings present; analysis complete
2   critical risks present; analysis complete
3   analysis incomplete (unsupported statements, DB/file/operational failure)
4   CLI / local input error
5   internal error
130 interrupted
```

### Safer rollout recommendations

Advisory only:

```text
no generated migration execution
no automatic apply
recommendations include assumptions and preconditions
```

---

## 8. Prototype engine (Stage 5)

```text
migration.sql
→ parse supported DDL families
→ resolve affected objects
→ read version, sizes, dependencies from catalog
→ compute lock / rewrite / dependency risk
→ emit explainable safer-rollout advice
```

Unsupported statements receive an honest `unsupported` status and force incomplete analysis semantics (§7).

---

## 9. Thesis success criteria (Stage 6 — Demo-proof)

### Technical asserts on fixed fixtures

1. Correctly flags lock/rewrite for `ALTER COLUMN TYPE` when expected.
2. Distinguishes metadata-only `ADD COLUMN` from scan/rewrite cases (version-aware).
3. Surfaces real catalog dependencies for `DROP COLUMN`.
4. Does not emit false `critical` on a known-safe fixture.
5. Proposes a concrete safer rollout (with assumptions), not a generic platitude.

### Human check

Five independent backend developers receive SQL + report **without** prior coaching.

Success:

- all five understand the risk from the report alone;
- at least **4 of 5** say they would run the tool before merge.

### Later gates (not thesis gates)

- **Accuracy-first** — required before treating `impact` as a reliable shipped feature.
- **Real PR workflow** — adoption check after a convincing prototype.

---

## 10. Competitive framing (hypothesis)

| Class of tool | Typical strength | Typical gap for this JTBD |
| --- | --- | --- |
| Live DB monitors / advisors | Current health, bloat, locks *now* | Weak on *proposed* not-yet-applied DDL |
| SQL linters / migration reviewers | Style, some static danger patterns | Weak live sizes/version/catalog coupling |
| Schema diff / migrate runners | Apply & track migrations | Often execute or assume apply; thin pre-impact story |

**pginspect impact** aims at the gap: proposed file + live catalog → explainable pre-execution impact.

This framing is a product hypothesis to validate via Demo-proof, not a claim of market proof.

---

## 11. Parallel Foundation close track

Independent of this thesis:

1. Create private `MilliganCo/postgres-schema-inspector`
2. Review diff/history; Gitleaks + TruffleHog
3. Push `main`
4. Green GHA on PostgreSQL 14–18
5. Close human security gates; archive or exception legacy
6. Only then mark true `FOUNDATION_COMPLETE`
7. Do **not** change visibility or start publication earlier

Current local state remains **Foundation code-complete**.

---

## 12. Next document (not this one)

After thesis approval as a file, the next artifact is an **impact design** covering:

- parser boundary and supported/unsupported grammar
- risk rule tables (lock/rewrite/deps) with confidence/limitations
- catalog queries and privilege-aware skips
- incomplete-analysis / `unsupported` semantics and exit/outcome mapping
- `ImpactCommandResult` / finding contracts (without mutating Foundation `1.0`)

**No implementation plan yet.**

---

## Document control

| Item | Value |
| --- | --- |
| Path | `docs/superpowers/specs/2026-07-22-change-impact-product-thesis.md` |
| Primary user | Backend developer without DBA |
| Hero command | `pginspect impact migration.sql` |
| Prototype PG majors | 14–18 |
| Thesis gate | Demo-proof (§9) |
| Next | Impact design-spec |
