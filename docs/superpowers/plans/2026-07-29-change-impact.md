# pginspect Change Impact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** approved implementation plan  
**Goal:** Deliver `pginspect impact MIGRATION.sql` for PostgreSQL 14–18 analyzing ALTER COLUMN TYPE, ADD COLUMN, and DROP COLUMN against a live read-only catalog without ever executing migration SQL.  
**Architecture:** Local lexical phase produces `LocalParsedScript`; DB phase calls `DiagnosticSession.establish_impact_profile` (`READ ONLY REPEATABLE READ` before any SELECT, pre-hardening capture, then harden), classifies with major-aware grammar, resolves via captured `current_schemas(true)`, gathers package-owned catalog evidence, applies sequence constraints on `AnalysisUnit`s, runs TYPE/ADD/DROP rule engines, and emits `ImpactCommandResult` schema `0.1`.  
**Tech Stack:** Python ≥3.11, psycopg 3 (only via `connection.py`/`session.py`), Typer, Rich, Pydantic v2, pytest, Ruff, mypy strict, GitHub Actions, Docker PostgreSQL 14–18.

**Normative contracts (do not reopen product decisions without a discovered contradiction):**

- `docs/superpowers/specs/2026-07-22-change-impact-product-thesis.md` (approved)
- `docs/superpowers/specs/2026-07-23-change-impact-design.md` (approved design)

**Out of authorization for this plan document itself:** product implementation, commits, pushes, Foundation status changes, publication, archiving legacy.

## Shell convention

All verification commands in this plan are **portable Python** (or `pytest` / `ruff` / `mypy` / `git`) unless a step is explicitly labeled `PowerShell only`. Do not mix ad-hoc Bash/`Test-Path` into executable steps.

## Global Constraints

- PostgreSQL majors in scope: **14–18** only; unsupported major → incomplete exit 3 at preflight.
- Migration file is **never** executed; migration text/preview/token spans never reach executable SQL text.
- Object names from migration may appear only as **bound parameter values**, never spliced into SQL text and never as a whole migration statement query.
- Foundation schemas `Finding`/`CommandResult` **1.0** are immutable; impact uses `urn:pginspect:schema:impact-command-result:0.1` and `urn:pginspect:schema:impact-statement-card:0.1`.
- Reuse Foundation `ExecutionError` **exactly** (`pginspect.models.execution_error.ExecutionError`). Do not fork, subclass-for- widenschema, or add impact-only fields to it.
- `impact/*` must not import `psycopg`, hold raw connection/cursor, or expose public `execute()`.
- All catalog SQL is package-owned `LiteralString`, schema-qualified, allowlisted by `query_id`.
- Impact session timeline is normative (Task 4): BEGIN → stamp `catalog_snapshot_at` → first SELECT is `impact.set_timeouts` via `set_config(..., true)` → capture → harden → verify → preflight. `connect-test` profile and establish/verify SQL fingerprints must not change.
- After harden: never call `pg_*_is_visible` (enforced by AST/source boundary test).
- Privilege policy B: every analyzed card includes exact limitation string  
  `Authorization failures are not modeled; analysis assumes sufficient privileges.`
- Exit aggregation (§3.9): any `unsupported_*` or preflight incomplete → 3; else `would_fail` or critical → 2; else warning → 1; else 0.
- Local/CLI usage failures → process exit **4**, **no** `ImpactCommandResult`.
- Expected DB/runtime analysis failure → `outcome=failed` result with exit **3**.
- Internal modeled failure → `outcome=failed` result with exit **5**.
- Catastrophic wrapper/serialization failure → process exit **5**, **no** result.
- KeyboardInterrupt → process exit **130**, **no** result.
- No `--dsn` / `--password`; Foundation connection options only.
- `DROP INDEX` deferred — no grammar/module/rules.
- Public models: `extra=forbid`, `frozen=True`, `allow_inf_nan=False`.
- One commit per completed task; disjoint file ownership for parallel agents.
- Layer reviews: after Task 3; after Task 5; after **all of** Tasks 7+8+9; after Task 11; after Task 13; after Task 15 + full CI re-gate on Task-15 SHA.
- Default `pytest` remains `tests/unit` only (F-01).

## Subagent-Driven Development rules

1. One task = one subagent = one commit after green tests for that task.
2. TDD: failing test → minimal implementation → green → commit.
3. Never assign two concurrent agents overlapping paths in a task’s **Files** block.
4. Stop at each layer-review checkpoint until approved.
5. Do not invent product behavior absent from the approved design; escalate contradictions.
6. Code marked `pseudocode` is illustrative only. Every other command, file body, and assertion in a step is normative and copyable.

## File map (target)

```text
src/pginspect/
  session.py
  cli.py
  impact/
    __init__.py
    cli.py
    input.py
    run.py
    preflight.py
    parse_local.py              # LocalParsedScript assembly from input+parser
    analysis_unit.py            # AnalysisUnit / ResolvedStatement (pre-card)
    resolve.py
    catalog.py
    queries.py                  # QuerySpec registry
    query_exec.py               # Task 5: QuerySpec execution + recorder callback
    sequence.py
    parser/
      __init__.py
      split.py
      tokens.py
      control.py
      classify.py
      grammar_alter.py
      ast.py
    rules/
      __init__.py               # created in Task 5 with coercion.py
      coercion.py
      severity.py               # created in Task 6 (shared)
      type_change.py            # Task 7
      add_column.py             # Task 8
      drop_column.py            # Task 9
    models/
      __init__.py
      enums.py
      scalars.py                # JSONScalar
      evidence.py
      card.py
      result.py
      catalog_types.py
    renderers/
      __init__.py
      text.py
      json.py
docs/schemas/
  impact-command-result/0.1.schema.json
  impact-statement-card/0.1.schema.json
tests/
  unit/impact/
  integration/impact/
  safety/impact/
  fixtures/impact/<id>/{setup.sql,migration.sql,expected/}
  fixtures/impact/keywords/pg{14,15,16,17,18}.json
scripts/export_schemas.py
scripts/compare_schemas_export.py
scripts/record_impact_demo.py
scripts/capture_pg_keywords.py
```

## Traceability matrix

| Design section | Task(s) | Test layer | Acceptance evidence |
| --- | --- | --- | --- |
| Thesis hero + forbidden MVP | 0, 11, 13 | boundaries + safety | migration never in executable SQL text |
| §0.1 pipeline | 2, 4, 5, 6, 10 | unit + integration | stage/query-id order |
| §1 input/lexer/control/limits | 2 | unit X2/X3 + limits | exit 4; `LocalParsedScript` |
| §1b grammar | 3 | unit grammar × majors 14–18 | keyword fixtures |
| §1.6 sequence | 6 | unit on `AnalysisUnit` | before cards |
| §2 session/preflight/resolution | 4, 5, 12 | unit + live | RR; capture; harden |
| §2.8–2.9 catalog + coercion | 5 | unit + integration | T1–T3 coercion complete |
| §3.6–3.8 full rule matrices | 7, 8, 9 | unit full matrix | not only Demo fixtures |
| §3.9 / §4 contract | 1, 10, 14 | validators + schema | `ExecutionError` reuse |
| §5 CLI/streams | 11 | unit CLI | path/SQL absent; exits |
| §5.5–5.7 Demo-proof | 12, 15 | integration + recordings | T1/A4/D2 protocol |
| §2.10 / §5.6 safety | 13 | safety + AST | allowlist binding |
| §6 deferred | all | absence tests | no DROP INDEX |

## Dependency graph

```text
Task 0
  → Task 1 (contracts)
      → Task 2 (local parse) ──────────────────────────────┐
          → Task 3 (grammar, keyword fixtures 14–18)        │
              → Layer review A                              │
  → Task 4 (impact profile API) ← also needs Task 1         │
      → Task 5 (resolve/catalog/coercion + rules/__init__ + query_exec recorder)  │
          → Layer review B                                  │
                  → Task 6 (sequence on AnalysisUnit + severity.py + shared rule contracts)
                      → Variant B worktrees: Task 7, Task 8, Task 9 (isolated)
                      → cherry-pick 7 then 8 then 9 on main → unified rules tests
                      → Layer review C
                          → Task 10 (orchestration → ImpactCommandResult)
                              → Task 11 (CLI/renderers)
                                  → Layer review D
                                      → Task 12 (live fixtures + §2 live)
                                      → Task 13 (safety; exact seams only)
                                          → Layer review E
                                              → Task 14 (schemas/CI/docs)
                                                  → Task 15 (Demo-proof recordings)
                                                      → Final CI re-gate on Task-15 SHA
```

## Parallelism (corrected)

| Window | Parallel? | Ownership rule |
| --- | --- | --- |
| Tasks 7, 8, 9 | **Variant B — isolated worktrees** (see below) | Disjoint files only; never concurrent commits in one working tree |
| Task 12 then Task 13 | **Serial only** — Task 13 is tests-only and may import Task 12 helpers |
| Any other pair | **No** | Especially `session.py`, `cli.py`, `queries.py`, `export_schemas.py` |

### Variant B — Tasks 7∥8∥9 integration sequence (normative)

After Task 6 is committed at SHA `TASK6_SHA`:

```bash
git fetch origin
git worktree add ../psi-impact-task7 -b impact/task-7-type TASK6_SHA
git worktree add ../psi-impact-task8 -b impact/task-8-add TASK6_SHA
git worktree add ../psi-impact-task9 -b impact/task-9-drop TASK6_SHA
```

1. Subagent A in `../psi-impact-task7` completes Task 7 (tests green) and commits only on `impact/task-7-type`.
2. Subagent B in `../psi-impact-task8` completes Task 8 and commits only on `impact/task-8-add`.
3. Subagent C in `../psi-impact-task9` completes Task 9 and commits only on `impact/task-9-drop`.
4. Main agent, on the primary worktree `main` at `TASK6_SHA`:

```bash
git cherry-pick <task7-commit-sha>
pytest tests/unit/impact/rules/test_type_change_matrix.py -v
git cherry-pick <task8-commit-sha>
pytest tests/unit/impact/rules/test_add_column_matrix.py -v
git cherry-pick <task9-commit-sha>
pytest tests/unit/impact/rules -v
```

5. Only after the merged rules suite is green: **Layer review C**.
6. Remove worktrees:

```bash
git worktree remove ../psi-impact-task7
git worktree remove ../psi-impact-task8
git worktree remove ../psi-impact-task9
```

Do **not** run three `git commit` operations concurrently against one working tree.
---

### Task 0: Baseline and traceability

**Files:** none modified.

**Interfaces:**
- Consumes: Foundation green HEAD; this plan
- Produces: baseline confirmation recorded by implementer before Task 1

- [ ] **Step 1: Verify Foundation imports and absence of impact package**

```bash
python -c "from pginspect.models.result import CommandResult; from pginspect.models.execution_error import ExecutionError; from pathlib import Path; import pginspect; root=Path(pginspect.__file__).resolve().parent; assert not (root/'impact').exists(); print('baseline-ok')"
```

Expected: prints `baseline-ok`.

- [ ] **Step 2: Unit + lint baselines**

```bash
pytest tests/unit -q
ruff check src tests
ruff format --check src tests
mypy src
```

Expected: all exit 0.

- [ ] **Step 3: Confirm workflow files exist**

```bash
python -c "from pathlib import Path; w=Path('.github/workflows'); req={'unit.yml','lint-type.yml','schema.yml','integration.yml','safety.yml','coverage.yml'}; missing=req- {p.name for p in w.glob('*.yml')}; assert not missing, missing; print('workflows-ok')"
```

- [ ] **Step 4: No product commit**

Proceed to Task 1 without a Task 0 commit.

---

### Task 1: Impact contracts (complete)

**Files:**
- Create: `src/pginspect/impact/__init__.py`
- Create: `src/pginspect/impact/models/__init__.py`
- Create: `src/pginspect/impact/models/enums.py`
- Create: `src/pginspect/impact/models/scalars.py`
- Create: `src/pginspect/impact/models/evidence.py`
- Create: `src/pginspect/impact/models/card.py`
- Create: `src/pginspect/impact/models/result.py`
- Test: `tests/unit/impact/models/test_enums.py`
- Test: `tests/unit/impact/models/test_scalars.py`
- Test: `tests/unit/impact/models/test_impact_result_validators.py`
- Test: `tests/unit/impact/models/conftest.py` (exact factories)
- Do **not** modify Foundation `src/pginspect/models/*` or `docs/schemas/**/1.0.schema.json`

**Interfaces:**
- Consumes: `PublicModel`; **exact** `from pginspect.models.execution_error import ExecutionError`
- Produces: enums/models/validators below

**Normative types:**

```python
# scalars.py
JSONScalar = str | int | float | bool | None  # no nested objects; PublicModel allow_inf_nan=False rejects NaN/inf
```

```text
ImpactPreflightCheckStatus: passed | failed | skipped   # distinct enum
PreflightStatus: passed | incomplete | failed
Outcome, Risk, AnalysisStatus, ExecutionPrediction, LockMode, PhysicalTriState,
NoOpReason, ImpactRole, EvidenceKind, ObjectKind, AnalysisStage
# + confidence enums per design §3.4
```

`ImpactCommandResult.error: ExecutionError | None` — Foundation type only.

**Mandatory validators (in addition to design §4.6):**

| Rule | Assertion |
| --- | --- |
| `execution_prediction == no_op` | `no_op_reason is not None` |
| `execution_prediction != no_op` | `no_op_reason is None` |
| `analysis_status` starts with `unsupported_` | `execution_prediction == not_evaluated` and `risk == not_applicable` |
| cards (always) | `input.card_count == len(statements)` |
| controls (always) | `input.source_statement_count >= input.control_statement_count` |
| classification-complete counts | If `preflight.analysis_stage_reached ∈ {resolve, catalog, rules, complete}` **and** `outcome != failed`, then `source_statement_count == card_count + control_statement_count`. Do **not** enforce this equality for early preflight incomplete (`analysis_stage_reached=preflight`, `statements=()`) or for `outcome=failed` results assembled before card assembly. |
| indexes | `statement_index` unique, all `>= 1`, strictly ascending in `statements` |
| evidence | `evidence_id` unique; every card `evidence_refs` exists in `evidence`; every evidence item referenced ≥1 when `statements` non-empty |
| time | `duration_ms >= 0`; `started_at` timezone-aware UTC |
| fingerprint | matches `^sha256:[0-9a-f]{16}$` |
| preview | Unicode code-point length of `sanitized_preview` `<= 240` |

Add explicit unit tests for: (a) preflight-incomplete with `source_statement_count=3`, `card_count=0`, `control_statement_count=0`, `statements=()` — must validate; (b) classification-complete completed result with mismatched counts — must reject; (c) `outcome=failed` before cards with nonzero `source_statement_count` and empty statements — must validate without equality.

- [ ] **Step 1: Write factories + failing validator tests**

Create `tests/unit/impact/models/conftest.py` with exact helpers:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pginspect.impact.models.card import ImpactStatementCard
from pginspect.impact.models.enums import (
    AnalysisStatus,
    ExecutionPrediction,
    LockMode,
    Outcome,
    PhysicalTriState,
    Risk,
)
from pginspect.impact.models.evidence import ImpactEvidence
from pginspect.impact.models.result import (
    ImpactCommandResult,
    ImpactConfidence,
    ImpactInputMeta,
    ImpactPreflight,
    ImpactSummary,
)


AUTH_LIMIT = "Authorization failures are not modeled; analysis assumes sufficient privileges."


@pytest.fixture
def one_evidence() -> ImpactEvidence:
    return ImpactEvidence(
        evidence_id="rule:add.nullable.no_default",
        kind="semantic_rule",
        summary="nullable add without default",
        attributes={"rule_key": "add.nullable.no_default"},
    )


@pytest.fixture
def one_analyzed_card(one_evidence: ImpactEvidence) -> ImpactStatementCard:
    return ImpactStatementCard(
        statement_index=1,
        start_line=1,
        end_line=1,
        statement_fingerprint="sha256:0123456789abcdef",
        sanitized_preview="ALTER TABLE t ADD COLUMN note text",
        analysis_status=AnalysisStatus.ANALYZED,
        execution_prediction=ExecutionPrediction.APPLIES,
        no_op_reason=None,
        risk=Risk.WARNING,
        confidence=ImpactConfidence(
            lock="high",
            rewrite="high",
            execution="high",
            dependencies="high",
            impact_scale="medium",
        ),
        lock=LockMode.ACCESS_EXCLUSIVE_LOCK,
        table_rewrite=PhysicalTriState.NO,
        table_scan=PhysicalTriState.NO,
        index_rebuild=PhysicalTriState.NO,
        affected_objects=(),
        why=("catalog DDL semantics: metadata-only add",),
        safer_rollout={"steps": (), "assumptions": (), "preconditions": ()},
        limitations=(AUTH_LIMIT,),
        evidence_refs=(one_evidence.evidence_id,),
    )


@pytest.fixture
def minimal_completed_kwargs(one_analyzed_card, one_evidence) -> dict:
    return {
        "schema_version": "0.1",
        "command": "impact",
        "outcome": Outcome.COMPLETED,
        "exit_code": 1,
        "started_at": datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC),
        "duration_ms": 10,
        "app_version": "0.0.0",
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=1,
            card_count=1,
            control_statement_count=0,
        ),
        "connection_context": None,
        "preflight": ImpactPreflight(
            status="passed",
            analysis_stage_reached="complete",
            checks=(),
            limitations=(),
        ),
        "snapshot": None,
        "summary": ImpactSummary(
            overall_risk=Risk.WARNING,
            critical_count=0,
            warning_count=1,
            safe_count=0,
            not_applicable_count=0,
            would_fail_count=0,
            may_fail_count=0,
            unsupported_count=0,
            no_op_count=0,
            analyzed_count=1,
            incomplete=False,
        ),
        "statements": (one_analyzed_card,),
        "evidence": (one_evidence,),
        "error": None,
    }
```

Add tests covering every mandatory validator row above, including:

```python
def test_no_op_requires_reason(minimal_completed_kwargs, one_analyzed_card):
    card = one_analyzed_card.model_copy(
        update={
            "execution_prediction": ExecutionPrediction.NO_OP,
            "no_op_reason": None,
            "risk": Risk.SAFE,
        }
    )
    kwargs = {**minimal_completed_kwargs, "statements": (card,)}
    with pytest.raises(ValidationError):
        ImpactCommandResult(**kwargs)


def test_unsupported_forces_not_evaluated(minimal_completed_kwargs, one_analyzed_card, one_evidence):
    card = one_analyzed_card.model_copy(
        update={
            "analysis_status": AnalysisStatus.UNSUPPORTED_PARSER,
            "execution_prediction": ExecutionPrediction.APPLIES,  # illegal
            "risk": Risk.WARNING,
            "evidence_refs": (one_evidence.evidence_id,),
        }
    )
    kwargs = {**minimal_completed_kwargs, "statements": (card,), "outcome": Outcome.INCOMPLETE, "exit_code": 3}
    with pytest.raises(ValidationError):
        ImpactCommandResult(**kwargs)


def test_error_field_is_foundation_execution_error(minimal_completed_kwargs):
    from pginspect.models.enums import ExecutionErrorCategory, ExecutionErrorCode
    from pginspect.models.execution_error import ExecutionError

    err = ExecutionError(
        code=ExecutionErrorCode.INTERNAL,
        category=ExecutionErrorCategory.INTERNAL,
        message="boom",
        retryable=False,
    )
    kwargs = {
        **minimal_completed_kwargs,
        "outcome": Outcome.FAILED,
        "exit_code": 5,
        "statements": (),
        "evidence": (),
        "summary": ImpactSummary(
            overall_risk=Risk.NOT_APPLICABLE,
            critical_count=0,
            warning_count=0,
            safe_count=0,
            not_applicable_count=0,
            would_fail_count=0,
            may_fail_count=0,
            unsupported_count=0,
            no_op_count=0,
            analyzed_count=0,
            incomplete=True,
        ),
        "input": ImpactInputMeta(
            path_basename="m.sql",
            source_statement_count=0,
            card_count=0,
            control_statement_count=0,
        ),
        "error": err,
    }
    result = ImpactCommandResult(**kwargs)
    assert type(result.error) is ExecutionError
```

Adjust enum member access to match implemented `StrEnum` style; keep semantic names identical to design.

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/unit/impact/models -v
```

Expected: `ModuleNotFoundError` or import errors for `pginspect.impact`.

- [ ] **Step 3: Implement models + validators**

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/unit/impact/models -v
```

- [ ] **Step 5: Commit**

```bash
git add src/pginspect/impact/__init__.py src/pginspect/impact/models tests/unit/impact/models
git commit -m "feat(impact): add complete 0.1 contracts reusing Foundation ExecutionError"
```

---

### Task 2: Local input → `LocalParsedScript`

**Files:**
- Create: `src/pginspect/impact/input.py`
- Create: `src/pginspect/impact/parse_local.py`
- Create: `src/pginspect/impact/parser/{__init__,split,tokens,control,ast}.py`
- Test: `tests/unit/impact/parser/test_input_loader.py`
- Test: `tests/unit/impact/parser/test_splitter_limits.py`
- Test: `tests/unit/impact/parser/test_tokenizer_redaction.py`
- Test: `tests/unit/impact/parser/test_control_recognizer.py`
- Test: `tests/unit/impact/parser/test_x2_x3_local.py`
- Create: `tests/fixtures/impact/X2/migration.sql`
- Create: `tests/fixtures/impact/X3/migration.sql`

**Interfaces:**

```python
@dataclass(frozen=True)
class LocalParsedScript:
    path_basename: str
    statements: tuple[LocalStatement, ...]  # non-control + control kept for ordinals
    control_ordinals: tuple[int, ...]       # 1-based statement_index values that are control
    source_statement_count: int             # counts all source statements including control


def parse_migration_path(path: Path) -> LocalParsedScript:
    """Load + split + tokenize + control-tag. Raises LocalPhaseError on all exit-4 conditions."""
```

**Mandatory limit/malformed tests (exact):**

| Case | Expected |
| --- | --- |
| psql backslash command outside comments/strings | `LocalPhaseError` |
| `COPY ... FROM STDIN` with inline payload / `\.` | `LocalPhaseError` |
| 1001 statements | `LocalPhaseError` |
| 10001 tokens in one statement | `LocalPhaseError` |
| block-comment nesting depth 65 | `LocalPhaseError` |
| dollar-tag mismatch | `LocalPhaseError` |
| X2 unclosed string (fixture body below) | `LocalPhaseError` |
| X3 comment-only | `LocalPhaseError` |
| literal canary `CANARY_SECRET_7f03` in SQL | absent from `sanitized_preview` and fingerprint input stream |

**Exact fixture bodies:**

`tests/fixtures/impact/X2/migration.sql`:

```sql
ALTER TABLE impact_x2.t
  ADD COLUMN x text DEFAULT 'unclosed;
```

`tests/fixtures/impact/X3/migration.sql`:

```sql
-- comment only
/* still only a comment */
```

- [ ] **Step 1: Write failing tests for all rows above + `LocalParsedScript` shape**

```python
def test_local_parsed_script_counts_controls(tmp_path: Path):
    p = tmp_path / "m.sql"
    p.write_text("BEGIN;\nALTER TABLE t ADD COLUMN a int;\nCOMMIT;\n", encoding="utf-8")
    script = parse_migration_path(p)
    assert script.source_statement_count == 3
    assert script.control_ordinals == (1, 3)
    assert len([s for s in script.statements if not s.is_control]) == 1
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/unit/impact/parser -v
```

- [ ] **Step 3: Implement loader/FSM/tokenizer/control/`parse_migration_path`**

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/unit/impact/parser -v
```

- [ ] **Step 5: Commit**

```bash
git add src/pginspect/impact/input.py src/pginspect/impact/parse_local.py src/pginspect/impact/parser tests/unit/impact/parser tests/fixtures/impact/X2 tests/fixtures/impact/X3
git commit -m "feat(impact): add LocalParsedScript loader with FSM limits and control ordinals"
```

---

### Task 3: Major-aware grammar (PG 14–18 keyword fixtures)

**Files:**
- Create: `src/pginspect/impact/parser/grammar_alter.py`
- Create: `src/pginspect/impact/parser/classify.py`
- Modify: `src/pginspect/impact/parser/ast.py`
- Create: `tests/fixtures/impact/keywords/pg14.json` … `pg18.json`
- Create: `tests/unit/impact/parser/test_typename.py`
- Create: `tests/unit/impact/parser/test_grammar_families.py`
- Create: `scripts/capture_pg_keywords.py` (dev helper; run once per major under CI DSN to refresh fixtures)

**Interfaces:**

```python
def classify_noncontrol_statement(
    tokens: Sequence[Token],
    keyword_categories: Mapping[str, str],  # word -> catcode from pg_get_keywords()
) -> AlterClassification:  # SupportedAlterType|SupportedAlterAdd|SupportedAlterDrop|UnsupportedParser
```

**Keyword fixtures:** each `pgNN.json` is a JSON object mapping keyword word → catcode string, captured from that major. Grammar tests **must** parametrize:

```python
@pytest.mark.parametrize("major", [14, 15, 16, 17, 18])
def test_alter_type_parses_on_major(major: int) -> None:
    keywords = json.loads(
        Path(f"tests/fixtures/impact/keywords/pg{major}.json").read_text(encoding="utf-8")
    )
    tokens = tokenize("ALTER TABLE s.t ALTER COLUMN c TYPE integer")
    result = classify_noncontrol_statement(tokens, keywords)
    assert result.family == "type"
    assert result.type_name.name.normalized == "integer"
```

**`scripts/capture_pg_keywords.py` normative behavior:**

1. Connect using env `PGINSPECT_TEST_DSN` only (no password/DSN on argv).
2. `SELECT current_setting('server_version_num')::int` and derive `actual_major = server_version_num // 10000`.
3. Fail with nonzero exit if `actual_major != --major`.
4. Only then `SELECT word, catcode FROM pg_catalog.pg_get_keywords() ORDER BY word`.
5. Write canonical JSON object to `--out`.

```bash
python scripts/capture_pg_keywords.py --major 14 --out tests/fixtures/impact/keywords/pg14.json
```

Commit the five JSON files in Task 3 after verified capture against each major.

- [ ] **Step 1: Write failing grammar tests parametrized across majors 14–18** covering TypeName allowlist, TYPE/SET DATA TYPE, ADD, DROP, multi-action `unsupported_parser`, dollar-body `unsupported_parser`, `ONLY`/`*`.

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/unit/impact/parser/test_typename.py tests/unit/impact/parser/test_grammar_families.py -v
```

- [ ] **Step 3: Implement grammar + commit keyword fixtures**

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/unit/impact/parser -v
```

- [ ] **Step 5: Commit**

```bash
git add src/pginspect/impact/parser tests/unit/impact/parser tests/fixtures/impact/keywords scripts/capture_pg_keywords.py
git commit -m "feat(impact): add major-aware ALTER grammar with PG14-18 keyword fixtures"
```

**Layer review A:** parser/local phase complete; no DB I/O.

---

### Task 4: Impact session profile — exact API and timeline

**Files:**
- Modify: `src/pginspect/session.py`
- Create: `src/pginspect/impact/preflight.py` — defines **`ResolutionContext`** (Task 5 imports it from here)
- Create: `src/pginspect/impact/queries.py` (session/preflight query specs only in this task)
- Test: `tests/unit/impact/test_impact_profile_sequence.py`
- Test: `tests/unit/impact/test_preflight_gates.py`
- Test: `tests/unit/test_session_connect_test_fingerprint.py`
- Create: `tests/unit/goldens/session_sql_hashes.json`

**`ResolutionContext` created in Task 4 (`preflight.py`):**

```python
@dataclass(frozen=True)
class ResolutionContext:
    database: str
    role: str
    session_user: str
    current_schema: str | None
    current_schemas_user: tuple[str, ...]
    current_schemas_with_implicit: tuple[str, ...]
    search_path_raw: str
    max_identifier_length_bytes: int
    server_major: int
    server_version_num: int
    keyword_categories: Mapping[str, str]
```

**Normative API:**

```python
@dataclass(frozen=True)
class ImpactSessionState:
    resolution_context: ResolutionContext
    connection_context: ImpactConnectionContext
    catalog_snapshot_at: datetime  # UTC; stamped immediately before first SELECT (impact.set_timeouts)

class DiagnosticSession:
    def establish_impact_profile(self) -> ImpactSessionState:
        """Normative timeline (query_id / command order):
        1. impact.begin_read_only_rr
           BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ
        2. catalog_snapshot_at = datetime.now(UTC)
           stamped immediately before the first SELECT
        3. impact.set_timeouts
           SELECT pg_catalog.set_config(...) x3 with is_local=true  # FIRST SELECT
        4. impact.capture_resolution_context
        5. impact.harden_search_path
           SET LOCAL search_path = pg_catalog
        6. impact.verify_safety
        7. impact.preflight_reads
        """
```

**Timeout rule (normative):** `impact.set_timeouts` is a **SELECT** using package-owned `LiteralString` SQL and three bound string parameters (timeout values such as `"5000ms"`). It must **not** splice dynamic values into SQL text and must **not** use bare `SET` with client-side formatting of dynamic values.

Exact SQL constant:

```python
IMPACT_SET_TIMEOUTS_SQL: LiteralString = """
SELECT
    pg_catalog.set_config('statement_timeout', %s, true),
    pg_catalog.set_config('lock_timeout', %s, true),
    pg_catalog.set_config('idle_in_transaction_session_timeout', %s, true)
"""
```

`param_types = (str, str, str)`. Bound args are built from `SessionSafetyConfig` as `f"{ms}ms"` for each of statement/lock/idle timeouts. SQL text never changes; only bound parameters change.

**Invariants:**

1. `BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ` occurs **before any SELECT**.
2. `catalog_snapshot_at` is set **immediately before** the first SELECT, which is `impact.set_timeouts`.
3. `impact.set_timeouts` is `command_kind=SELECT` and is the first SELECT in the timeline.
4. Pre-hardening context (`impact.capture_resolution_context`) is read **before** `search_path=pg_catalog`.
5. Connect-test `_ESTABLISH_SQL` / `_VERIFY_SQL` remain byte-identical to pre-Task-4 HEAD (golden SHA-256 in `tests/unit/goldens/session_sql_hashes.json`).

- [ ] **Step 1: Capture Foundation SQL hashes then write failing tests**

```bash
python -c "import hashlib; from pginspect import session as s; print(hashlib.sha256(s._ESTABLISH_SQL.encode()).hexdigest()); print(hashlib.sha256(s._VERIFY_SQL.encode()).hexdigest())"
```

Write those two hex digests into `tests/unit/goldens/session_sql_hashes.json` as keys `establish_sql_sha256` and `verify_sql_sha256` **before** modifying `session.py`.

```python
def test_impact_profile_query_id_order(fake_session_recorder):
    state = fake_session_recorder.establish_impact_profile()
    assert fake_session_recorder.query_ids == [
        "impact.begin_read_only_rr",
        "impact.set_timeouts",
        "impact.capture_resolution_context",
        "impact.harden_search_path",
        "impact.verify_safety",
        "impact.preflight_reads",
    ]
    assert fake_session_recorder.command_kinds == [
        "BEGIN",
        "SELECT",
        "SELECT",
        "SET",
        "SELECT",
        "SELECT",
    ]
    assert fake_session_recorder.first_select_query_id == "impact.set_timeouts"
    assert state.catalog_snapshot_at.tzinfo is not None


def test_connect_test_establish_sql_unchanged():
    import hashlib
    import json
    from pathlib import Path
    from pginspect import session as s

    expected = json.loads(Path("tests/unit/goldens/session_sql_hashes.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(s._ESTABLISH_SQL.encode("utf-8")).hexdigest() == expected["establish_sql_sha256"]
    assert hashlib.sha256(s._VERIFY_SQL.encode("utf-8")).hexdigest() == expected["verify_sql_sha256"]
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/unit/impact/test_impact_profile_sequence.py tests/unit/impact/test_preflight_gates.py tests/unit/test_session_connect_test_fingerprint.py -v
```

- [ ] **Step 3: Implement `establish_impact_profile` + preflight gates + `ResolutionContext`**

Preflight incomplete when: major ∉ {14..18}; `standard_conforming_strings != on`; not read-only; isolation ≠ repeatable read; encodings ≠ UTF8.

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/unit/impact/test_impact_profile_sequence.py tests/unit/impact/test_preflight_gates.py tests/unit/test_session_connect_test_fingerprint.py tests/unit/test_session_state_machine.py tests/unit/test_connectivity_orchestration.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/pginspect/session.py src/pginspect/impact/preflight.py src/pginspect/impact/queries.py tests/unit/impact/test_impact_profile_sequence.py tests/unit/impact/test_preflight_gates.py tests/unit/test_session_connect_test_fingerprint.py tests/unit/goldens/session_sql_hashes.json
git commit -m "feat(impact): add establish_impact_profile with set_config timeouts and ResolutionContext"
```

---

### Task 5: Resolution, catalog, complete T1–T3 coercion (no stubs)

**Files:**
- Create: `src/pginspect/impact/analysis_unit.py`
- Create: `src/pginspect/impact/resolve.py`
- Create: `src/pginspect/impact/catalog.py`
- Create: `src/pginspect/impact/query_exec.py` — QuerySpec executor + test recorder callback
- Create: `src/pginspect/impact/models/catalog_types.py`
- Create: `src/pginspect/impact/rules/__init__.py` — exports `lookup_coercion`, `CoercionLookupResult` only
- Create: `src/pginspect/impact/rules/coercion.py`
- Modify: `src/pginspect/impact/queries.py` (full registry including Task 4 session queries + catalog)
- Modify: `src/pginspect/impact/preflight.py` — import/`ResolutionContext` already owned here; catalog uses it
- Test: `tests/unit/impact/test_resolve_ranking.py`
- Test: `tests/unit/impact/test_catalog_snapshots.py`
- Test: `tests/unit/impact/test_coercion_evidence_t1_t3.py`
- Test: `tests/unit/impact/test_dependency_bfs_bounds.py`
- Test: `tests/unit/impact/test_no_pg_is_visible.py`
- Test: `tests/unit/impact/test_query_registry.py`

**QuerySpec:**

```python
@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    sql: LiteralString
    param_types: tuple[type, ...]
    row_model: type | None  # None for BEGIN/SET
    required_evidence_family: str
    command_kind: Literal["SELECT", "SET", "BEGIN"]
```

**Complete package-owned query inventory (normative minimum):**

| query_id | Purpose | Owner constant | Params | Row model | Evidence family | Kind |
| --- | --- | --- | --- | --- | --- | --- |
| `impact.begin_read_only_rr` | Begin RR read-only txn | `queries.py` | `()` | `None` | session | BEGIN |
| `impact.set_timeouts` | Local timeouts via `set_config(..., true)` | `IMPACT_SET_TIMEOUTS_SQL` in `queries.py` | `(str, str, str)` — `f"{ms}ms"` ×3 | `None` (discard row) | session | SELECT |
| `impact.capture_resolution_context` | Pre-harden path/schemas/role/db | `queries.py` | `()` | `ResolutionCaptureRow` | resolution | SELECT |
| `impact.harden_search_path` | SET LOCAL search_path + safety GUCs | `queries.py` | `()` | `None` | session | SET |
| `impact.verify_safety` | Verify RO + path + timeouts | `queries.py` | `()` | `SafetyVerifyRow` | session | SELECT |
| `impact.preflight_reads` | version/GUC/encoding/isolation/keywords | `queries.py` | `()` | `PreflightRow` | preflight | SELECT |
| `impact.resolve_relation_candidates` | Rank relations by schema list | `queries.py` | `(tuple[str,...], str)` nspnames + relname | `RelationCandidateRow` | resolution | SELECT |
| `impact.resolve_type_candidates` | Rank types by schema list | `queries.py` | `(tuple[str,...], str)` | `TypeCandidateRow` | resolution | SELECT |
| `impact.resolve_function_candidates` | Rank functions | `queries.py` | `(tuple[str,...], str, tuple[int,...])` | `FunctionCandidateRow` | resolution | SELECT |
| `impact.fetch_relation` | RelationSnapshot core | `queries.py` | `(int,)` oid | `RelationRow` | catalog_object | SELECT |
| `impact.fetch_columns` | ColumnSnapshot list | `queries.py` | `(int,)` relid | `ColumnRow` | catalog_object | SELECT |
| `impact.fetch_type` | TypeSnapshot / domain | `queries.py` | `(int,)` oid | `TypeRow` | catalog_object | SELECT |
| `impact.fetch_domain_constraints` | DomainConstraintSnapshot | `queries.py` | `(int,)` typid | `DomainConstraintRow` | catalog_object | SELECT |
| `impact.fetch_indexes` | IndexSnapshot for relation | `queries.py` | `(int,)` relid | `IndexRow` | catalog_object | SELECT |
| `impact.fetch_constraints` | ConstraintSnapshot | `queries.py` | `(int,)` relid | `ConstraintRow` | catalog_object | SELECT |
| `impact.fetch_function` | FunctionSnapshot | `queries.py` | `(int,)` oid | `FunctionRow` | catalog_object | SELECT |
| `impact.fetch_dependency_edges` | Bounded BFS batch | `queries.py` | class/obj ids + limit | `DependencyEdgeRow` | dependency_edge | SELECT |
| `impact.fetch_relation_metrics` | sizes + n_live_tup | `queries.py` | `(int,)` relid | `RelationMetricsRow` | metric_observation | SELECT |
| `impact.fetch_pg_cast` | pg_cast rows for oid pair | `queries.py` | `(int, int)` | `PgCastRow` | coercion | SELECT |

All SELECT/SET/BEGIN execution goes through `query_exec.execute_spec`. Recorder callback records `(query_id, sql_text, bound_parameters, command_kind)`.

**T1–T3 coercion (fixed origins; no runtime fallback):**

| Pair | majors | method | origin | evidence_id | On mismatch |
| --- | --- | --- | --- | --- | --- |
| integer → text | 14–18 | `automatic_io` | `server_generic_rule` | `coercion:integer_to_text_assignment` | N/A (checked-in; may consult pg_cast but must not invent rows) |
| text → varchar | 14–18 | `binary` | `pg_cast` | `coercion:text_to_varchar_binary` | if live `pg_cast` row absent or not binary/assignment → `unsupported_evidence` (unit/integration failure vs expected) |
| text → integer, no USING | 14–18 | absence | `checked_in_rule` | rule key `type.no_assignment_cast.no_using` | if unexpected assignment cast appears → `unsupported_evidence` |

- [ ] **Step 1: Write failing coercion + resolve + visibility + registry tests**

```python
import re
from pathlib import Path

_VISIBILITY_RE = re.compile(r"pg_\w*_is_visible")


def test_source_tree_forbids_all_pg_is_visible():
    root = Path("src/pginspect/impact")
    offenders = [p for p in root.rglob("*.py") if _VISIBILITY_RE.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_registry_contains_required_query_ids():
    from pginspect.impact.queries import IMPACT_QUERY_REGISTRY
    required = {
        "impact.begin_read_only_rr",
        "impact.set_timeouts",
        "impact.capture_resolution_context",
        "impact.harden_search_path",
        "impact.verify_safety",
        "impact.preflight_reads",
        "impact.resolve_relation_candidates",
        "impact.resolve_type_candidates",
        "impact.resolve_function_candidates",
        "impact.fetch_relation",
        "impact.fetch_columns",
        "impact.fetch_type",
        "impact.fetch_domain_constraints",
        "impact.fetch_indexes",
        "impact.fetch_constraints",
        "impact.fetch_function",
        "impact.fetch_dependency_edges",
        "impact.fetch_relation_metrics",
        "impact.fetch_pg_cast",
    }
    assert required <= set(IMPACT_QUERY_REGISTRY)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/unit/impact/test_resolve_ranking.py tests/unit/impact/test_catalog_snapshots.py tests/unit/impact/test_coercion_evidence_t1_t3.py tests/unit/impact/test_dependency_bfs_bounds.py tests/unit/impact/test_no_pg_is_visible.py tests/unit/impact/test_query_registry.py -v
```

- [ ] **Step 3: Implement resolve/catalog/coercion/QuerySpec/`query_exec.py`**

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/pginspect/impact/analysis_unit.py src/pginspect/impact/resolve.py src/pginspect/impact/catalog.py src/pginspect/impact/query_exec.py src/pginspect/impact/models/catalog_types.py src/pginspect/impact/rules/__init__.py src/pginspect/impact/rules/coercion.py src/pginspect/impact/queries.py tests/unit/impact/test_resolve_ranking.py tests/unit/impact/test_catalog_snapshots.py tests/unit/impact/test_coercion_evidence_t1_t3.py tests/unit/impact/test_dependency_bfs_bounds.py tests/unit/impact/test_no_pg_is_visible.py tests/unit/impact/test_query_registry.py
git commit -m "feat(impact): add resolution, QuerySpec inventory, query_exec recorder, and T1-T3 coercion"
```

**Layer review B.**

---

### Task 6: Sequence constraints on `AnalysisUnit` + shared severity

**Files:**
- Create: `src/pginspect/impact/sequence.py`
- Create: `src/pginspect/impact/rules/severity.py`
- Create: `src/pginspect/impact/rules/contracts.py`
- Modify: `src/pginspect/impact/rules/__init__.py` — append exports exactly:
  `RuleVerdict`, `apply_physical_invariants`, `aggregate_exit_code` (from severity/contracts). Keep prior coercion exports.
- Test: `tests/unit/impact/test_sequence_analyzer.py`
- Test: `tests/unit/impact/rules/test_severity_invariants.py`

**Normative `AnalysisUnit` (complete minimal type — no ellipsis fields):**

```python
@dataclass(frozen=True)
class SourceSpan:
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class AnalysisUnit:
    statement_index: int
    source_span: SourceSpan
    statement_fingerprint: str
    sanitized_preview: str
    family: Literal["type", "add", "drop", "unsupported_parser"]
    ast: object  # SupportedAlterType | SupportedAlterAdd | SupportedAlterDrop | UnsupportedParserAst
    analysis_status: AnalysisStatus
    table_oid: int | None
    table_schema: str | None
    table_name: str | None
    column_attnum: int | None
    column_normalized_name: str | None
    resolution_payload: object | None
    evidence_ids: tuple[str, ...]
    requires_virtual_schema_state: bool
    limitations: tuple[str, ...]


def apply_sequence_constraints(units: Sequence[AnalysisUnit]) -> tuple[AnalysisUnit, ...]:
    """Mark dependents unsupported_sequence per design §1.6.
    Runs after resolution, before risk scoring / ImpactStatementCard assembly.
    """
```

Tests use real identities:

```python
def test_add_then_alter_same_table_oid_and_column() -> None:
    span = SourceSpan(1, 1, 0, 10)
    u1 = AnalysisUnit(
        statement_index=1,
        source_span=span,
        statement_fingerprint="sha256:aaaaaaaaaaaaaaaa",
        sanitized_preview="ALTER TABLE t ADD COLUMN x int",
        family="add",
        ast=object(),
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=10,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="x",
        resolution_payload=None,
        evidence_ids=(),
        requires_virtual_schema_state=True,
        limitations=(),
    )
    u2 = AnalysisUnit(
        statement_index=2,
        source_span=SourceSpan(2, 2, 11, 20),
        statement_fingerprint="sha256:bbbbbbbbbbbbbbbb",
        sanitized_preview="ALTER TABLE t ALTER COLUMN x TYPE text",
        family="type",
        ast=object(),
        analysis_status=AnalysisStatus.ANALYZED,
        table_oid=10,
        table_schema="public",
        table_name="t",
        column_attnum=None,
        column_normalized_name="x",
        resolution_payload=None,
        evidence_ids=(),
        requires_virtual_schema_state=False,
        limitations=(),
    )
    out = apply_sequence_constraints((u1, u2))
    assert out[0].analysis_status == AnalysisStatus.ANALYZED
    assert out[1].analysis_status == AnalysisStatus.UNSUPPORTED_SEQUENCE
```

`severity.py` / `contracts.py` provide: `RuleVerdict`, physical invariants (`rewrite=yes ⇒ scan=yes`), risk mapping helpers, `aggregate_exit_code`.

- [ ] **Step 1–5:** TDD + commit

```bash
git add src/pginspect/impact/sequence.py src/pginspect/impact/rules/severity.py src/pginspect/impact/rules/contracts.py src/pginspect/impact/rules/__init__.py tests/unit/impact/test_sequence_analyzer.py tests/unit/impact/rules/test_severity_invariants.py
git commit -m "feat(impact): apply sequence constraints on AnalysisUnit and shared rule contracts"
```

---

### Task 7: TYPE rule engine — full normative matrix

**Files:**
- Create: `src/pginspect/impact/rules/type_change.py`
- Test: `tests/unit/impact/rules/test_type_change_matrix.py`
- Test factories: `tests/unit/impact/rules/factories_type.py`

**Owns only the above paths.** Concurrent development uses Variant B isolated worktrees (see Parallelism); do not commit Task 7/8/9 in one shared working tree concurrently.

**Mandatory unit cases** — each row is the **only** allowed outcome (AUTH = authorization limitation string):

| Case | rule_key / evidence | analysis_status | execution | rewrite | scan | index_rebuild | risk | lock | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| same declared type, no USING | `type.same_declared_type.no_using` | analyzed | applies | no | no | no | warning | AE | AUTH |
| unknown assignment, indexes=yes | `type.assignment_cast_unknown.no_using` | analyzed | may_fail | possible | possible | possible | critical | AE | AUTH |
| unknown assignment, indexes=no | `type.assignment_cast_unknown.no_using` | analyzed | may_fail | possible | possible | no | critical | AE | AUTH |
| opaque USING, indexes=yes | `type.opaque_using` | analyzed | may_fail | possible | possible | possible | critical | AE | AUTH |
| opaque USING, indexes=no | `type.opaque_using` | analyzed | may_fail | possible | possible | no | critical | AE | AUTH |
| proven rewrite int→text, indexes=yes (T1) | `type.proven_rewrite` | analyzed | applies | yes | yes | yes | critical | AE | AUTH |
| proven rewrite int→text, indexes=no | `type.proven_rewrite` | analyzed | applies | yes | yes | no | critical | AE | AUTH |
| binary text→varchar, PG14, indexes=yes (T2) | `type.binary.text_to_varchar.same_collation.no_domain.no_using` | analyzed | applies | no | no | yes | critical | AE | AUTH |
| binary text→varchar, PG15–18, indexes=yes | same rule_key | analyzed | applies | no | no | no | warning | AE | AUTH |
| binary text→varchar, any major, indexes=no | same rule_key | analyzed | applies | no | no | no | warning | AE | AUTH |
| no assignment text→int (T3) | `type.no_assignment_cast.no_using` | analyzed | would_fail | not_applicable | not_applicable | not_applicable | critical | AE if table exists | AUTH |
| typmod widen varchar(10)→varchar(20), indexes=yes | `type.typmod_change.conservative_may_fail` | analyzed | may_fail | possible | possible | possible | critical | AE | AUTH; no silent “safe widen” |
| typmod widen, indexes=no | same | analyzed | may_fail | possible | possible | no | critical | AE | AUTH |
| typmod narrow varchar(20)→varchar(10), indexes=yes | `type.typmod_change.conservative_may_fail` | analyzed | may_fail | possible | possible | possible | critical | AE | AUTH |
| typmod narrow, indexes=no | same | analyzed | may_fail | possible | possible | no | critical | AE | AUTH |
| collation change only, indexes=yes | `type.collation_change.conservative_may_fail` | analyzed | may_fail | possible | possible | possible | critical | AE | AUTH |
| collation change only, indexes=no | same | analyzed | may_fail | possible | possible | no | critical | AE | AUTH |
| domain source type → base, indexes=yes | `type.domain_boundary.conservative_may_fail` | analyzed | may_fail | possible | possible | possible | critical | AE | AUTH |
| domain source, indexes=no | same | analyzed | may_fail | possible | possible | no | critical | AE | AUTH |
| base → domain target, indexes=yes | `type.domain_boundary.conservative_may_fail` | analyzed | may_fail | possible | possible | possible | critical | AE | AUTH |
| base → domain target, indexes=no | same | analyzed | may_fail | possible | possible | no | critical | AE | AUTH |

Confidence: lock/rewrite/execution/dependencies = `high` when status=analyzed and evidence complete; `impact_scale` = `medium` unless metrics absent (`low`). `unsupported_evidence` is **not** used for these typmod/collation/domain cases — reserved for missing required catalog evidence only.

- [ ] **Step 1:** Write full matrix failing tests using factories in `factories_type.py` (exact builders; no ellipsis in executable code).
- [ ] **Step 2:** `pytest tests/unit/impact/rules/test_type_change_matrix.py -v` → FAIL
- [ ] **Step 3:** Implement `type_change.py`
- [ ] **Step 4:** PASS
- [ ] **Step 5:** Commit

```bash
git add src/pginspect/impact/rules/type_change.py tests/unit/impact/rules/test_type_change_matrix.py tests/unit/impact/rules/factories_type.py
git commit -m "feat(impact): implement full TYPE rule matrix"
```

---

### Task 8: ADD COLUMN rule engine — full normative matrix

**Files:**
- Create: `src/pginspect/impact/rules/add_column.py`
- Test: `tests/unit/impact/rules/test_add_column_matrix.py`
- Test factories: `tests/unit/impact/rules/factories_add.py`

**Mandatory unit cases:**

| Case | rule_key | execution | rewrite | scan | index_rebuild | risk |
| --- | --- | --- | --- | --- | --- | --- |
| coercion invalid | `add.coercion_invalid` | would_fail | not_applicable | not_applicable | not_applicable | critical |
| nullable, effective_default NULL (A1) | `add.nullable.no_default` | applies | no | no | no | warning |
| nullable, const DEFAULT false (A2) | `add.nullable.const_or_nonvolatile_valid` | applies | no | no | no | warning |
| effective domain default, classifiable nonvolatile | `add.nullable.const_or_nonvolatile_valid` | applies | no | no | no | warning |
| unknown domain default, indexes=yes | `add.effective_default_unknown` | may_fail | possible | possible | possible | critical |
| unknown domain default, indexes=no | `add.effective_default_unknown` | may_fail | possible | possible | no | critical |
| constrained domain, indexes=yes | `add.domain_with_constraints` | applies | yes | yes | yes | critical |
| constrained domain, indexes=no | `add.domain_with_constraints` | applies | yes | yes | no | critical |
| `pg_catalog.now()` on timestamptz, resolved `provolatile=s` (stable) | `add.nullable.const_or_nonvolatile_valid` | applies | no | no | no | warning |
| `pg_catalog.clock_timestamp()`, indexes=yes (A3) | `add.volatile_valid` | applies | yes | yes | yes | critical |
| `pg_catalog.clock_timestamp()`, indexes=no | `add.volatile_valid` | applies | yes | yes | no | critical |
| explicit DEFAULT NULL, nullable | `add.nullable.no_default` | applies | no | no | no | warning |
| NOT NULL + proven non-null nonvolatile default | `add.not_null.nonvolatile_valid.proven_nonnull` | applies | no | no | no | warning |
| NOT NULL + null/unknown default (A4) | `add.not_null.no_default` | may_fail | no | possible | no | critical |
| A5 semantic projection equals A4 (n_live_tup=0 must not change) | `add.not_null.no_default` | may_fail | no | possible | no | critical |

**`now()` vs `clock_timestamp()` (normative):**

```text
pg_catalog.now()
  → FunctionSnapshot.provolatile == "s" (stable)
  → default_volatility = proven_nonvolatile
  → rewrite=no, scan=no
  → risk=warning (AccessExclusiveLock only)

pg_catalog.clock_timestamp()
  → FunctionSnapshot.provolatile == "v" (volatile)
  → default_volatility = proven_volatile
  → rewrite=yes, scan=yes
  → risk=critical
```

A4/A5 must include limitations: emptiness string + AUTH. Compare A4 vs A5 on semantic projection only: `execution_prediction`, `risk`, `lock`, rewrite/scan/index_rebuild, rule evidence ids, required limitations — **not** full card byte identity.

- [ ] Steps 1–5 TDD + commit:

```bash
git add src/pginspect/impact/rules/add_column.py tests/unit/impact/rules/test_add_column_matrix.py tests/unit/impact/rules/factories_add.py
git commit -m "feat(impact): implement full ADD COLUMN rule matrix"
```

---

### Task 9: DROP COLUMN rule engine — full normative matrix

**Files:**
- Create: `src/pginspect/impact/rules/drop_column.py`
- Test: `tests/unit/impact/rules/test_drop_column_matrix.py`
- Test factories: `tests/unit/impact/rules/factories_drop.py`

**Mandatory unit cases:**

```text
no dependents
internal-only (D1)
automatic dependents
external blocker + RESTRICT/default (D2)
CASCADE + external/cascade (D3)
truncated graph → unsupported_evidence
required evidence missing → unsupported_evidence
```

Physical always: rewrite=no, scan=no, index_rebuild=no; lock=AccessExclusiveLock when target exists.

- [ ] Steps 1–5 TDD + commit:

```bash
git add src/pginspect/impact/rules/drop_column.py tests/unit/impact/rules/test_drop_column_matrix.py tests/unit/impact/rules/factories_drop.py
git commit -m "feat(impact): implement full DROP COLUMN rule matrix"
```

**Layer review C — only after Variant B cherry-picks of Tasks 7, 8, and 9 are on main and `pytest tests/unit/impact/rules -v` is green.**

---

### Task 10: Orchestration (`run_impact`) — output-agnostic

**Files:**
- Create: `src/pginspect/impact/run.py`
- Test: `tests/unit/impact/test_run_impact_orchestration.py`
- Test: `tests/unit/impact/test_exit_aggregation.py`

**Normative signature:**

```python
def run_impact(
    path: Path,
    connection_config: ConnectionConfig,
    session_safety: SessionSafetyConfig,
) -> ImpactCommandResult:
    """Raise LocalPhaseError for exit-4 local failures; otherwise always return ImpactCommandResult."""
```

- Raises `LocalPhaseError` for local/malformed/input failures (CLI maps to process exit 4; **no** result).
- Returns `ImpactCommandResult` with `outcome=failed`, `exit_code=3` for expected DB/runtime analysis failures.
- Returns `ImpactCommandResult` with `outcome=failed`, `exit_code=5` for internal modeled failures.
- Does **not** take `OutputConfig`. Does **not** define a `NoResult` sentinel.

**Mandatory orchestration tests:**

```text
exact stage order (local → connect → profile → classify → resolve → catalog → sequence → rules → assemble)
malformed input opens no connection
preflight incomplete → statements=(), exit=3, incomplete=true
qualified missing + IF EXISTS → no_op card
qualified missing without IF EXISTS → would_fail card
unsupported_sequence preserved into cards
evidence registry: no missing refs, no unused ids when statements non-empty
rollback on every DB path (success and failure)
```

- [ ] Steps 1–5 TDD + commit:

```bash
git add src/pginspect/impact/run.py tests/unit/impact/test_run_impact_orchestration.py tests/unit/impact/test_exit_aggregation.py
git commit -m "feat(impact): wire output-agnostic run_impact orchestration"
```

---

### Task 11: Renderers and CLI

**Files:**
- Create: `src/pginspect/impact/cli.py`
- Create: `src/pginspect/impact/renderers/{__init__,text,json}.py`
- Modify: `src/pginspect/cli.py` (register command only; no Path.open, no exists/readable checks)
- Modify: `tests/unit/test_package_boundaries.py` (impact boundaries)
- Test: `tests/unit/impact/test_renderers.py`
- Test: `tests/unit/impact/test_cli_impact.py`

**Rules:** Typer receives `Path` and passes it to `run_impact` / `parse_migration_path`. **Only** `impact/input.py` opens/stat/reads the file.

**Mandatory tests:**

```text
full filesystem path absent from stdout, stderr, and serialized result fields
raw migration SQL absent from text, json, and debug
JSON mode: stderr always empty
JSON mode: exactly one object + one trailing newline
text --debug: diagnostics only on stderr
serialization failure → process exit 5, no result object on stdout
installed entrypoint: python -c "from pginspect.cli import main; raise SystemExit(main(['impact','--help']))" exits 0 and mentions impact
LocalPhaseError → exit 4, empty stdout
```

- [ ] Steps 1–5 TDD + commit:

```bash
git add src/pginspect/cli.py src/pginspect/impact/cli.py src/pginspect/impact/renderers tests/unit/impact/test_renderers.py tests/unit/impact/test_cli_impact.py tests/unit/test_package_boundaries.py
git commit -m "feat(impact): add renderers and thin impact CLI without path I/O"
```

**Layer review D.**

---

### Task 12: Live integration — Demo fixtures + design §2

**Files:** create the exact fixture tree below; plus:

- `tests/integration/impact/conftest.py`
- `tests/integration/impact/test_fixture_matrix.py`
- `tests/integration/impact/test_resolution_preflight_live.py`
- `tests/integration/impact/test_rollback_live.py`

**Isolation:** each fixture uses schema `impact_<id_lower>`; setup begins with `DROP SCHEMA IF EXISTS impact_t1 CASCADE;` (and the matching schema name for other fixtures) then create, so CI re-runs are idempotent. Cleanup in fixture finalizer drops that schema via admin `DROP SCHEMA IF EXISTS <schema> CASCADE`.

#### Exact Demo fixtures

**T1** — `tests/fixtures/impact/T1/setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_t1 CASCADE;
CREATE SCHEMA impact_t1;
CREATE TABLE impact_t1.t (
  id int PRIMARY KEY,
  payload integer NOT NULL
);
CREATE INDEX impact_t1_payload_idx ON impact_t1.t (payload);
```

`migration.sql`:

```sql
ALTER TABLE impact_t1.t ALTER COLUMN payload TYPE text;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 2,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "applies",
      "table_rewrite": "yes",
      "table_scan": "yes",
      "index_rebuild": "yes",
      "lock": "AccessExclusiveLock",
      "risk": "critical",
      "evidence_ids": [
        "rule:type.proven_rewrite",
        "coercion:integer_to_text_assignment",
        "index:impact_t1_payload_idx"
      ],
      "limitations_contains": [
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

**T2** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_t2 CASCADE;
CREATE SCHEMA impact_t2;
CREATE TABLE impact_t2.t (
  id int PRIMARY KEY,
  label text NOT NULL
);
CREATE INDEX impact_t2_label_idx ON impact_t2.t (label);
```

`migration.sql`:

```sql
ALTER TABLE impact_t2.t ALTER COLUMN label TYPE varchar;
```

`expected/common.json` (PG15–18 base; comparator merges `pg14.json` overlay when major==14):

```json
{
  "outcome": "completed",
  "exit_code": 1,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "applies",
      "table_rewrite": "no",
      "table_scan": "no",
      "index_rebuild": "no",
      "lock": "AccessExclusiveLock",
      "risk": "warning",
      "evidence_ids": [
        "rule:type.binary.text_to_varchar.same_collation.no_domain.no_using",
        "coercion:text_to_varchar_binary",
        "index:impact_t2_label_idx"
      ]
    }
  ]
}
```

`expected/pg14.json` overlay:

```json
{
  "exit_code": 2,
  "cards": [
    {
      "index_rebuild": "yes",
      "risk": "critical"
    }
  ]
}
```

Comparator rule: load `common.json`, deep-merge `pg{major}.json` when present (card fields merge by index).

**T3** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_t3 CASCADE;
CREATE SCHEMA impact_t3;
CREATE TABLE impact_t3.t (
  id int PRIMARY KEY,
  payload text NOT NULL
);
```

`migration.sql`:

```sql
ALTER TABLE impact_t3.t ALTER COLUMN payload TYPE integer;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 2,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "would_fail",
      "table_rewrite": "not_applicable",
      "table_scan": "not_applicable",
      "index_rebuild": "not_applicable",
      "risk": "critical",
      "evidence_ids": ["rule:type.no_assignment_cast.no_using"]
    }
  ]
}
```

**A1** — `tests/fixtures/impact/A1/setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_a1 CASCADE;
CREATE SCHEMA impact_a1;
CREATE TABLE impact_a1.t (id int PRIMARY KEY);
```

`migration.sql`:

```sql
ALTER TABLE impact_a1.t ADD COLUMN note text;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 1,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "applies",
      "table_rewrite": "no",
      "table_scan": "no",
      "index_rebuild": "no",
      "lock": "AccessExclusiveLock",
      "risk": "warning",
      "evidence_ids": ["rule:add.nullable.no_default"],
      "limitations_contains": [
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

**A2** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_a2 CASCADE;
CREATE SCHEMA impact_a2;
CREATE TABLE impact_a2.t (id int PRIMARY KEY);
```

`migration.sql`:

```sql
ALTER TABLE impact_a2.t ADD COLUMN flag boolean DEFAULT false;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 1,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "applies",
      "table_rewrite": "no",
      "table_scan": "no",
      "index_rebuild": "no",
      "lock": "AccessExclusiveLock",
      "risk": "warning",
      "evidence_ids": ["rule:add.nullable.const_or_nonvolatile_valid"],
      "limitations_contains": [
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

**A3** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_a3 CASCADE;
CREATE SCHEMA impact_a3;
CREATE TABLE impact_a3.t (id int PRIMARY KEY);
CREATE INDEX impact_a3_id_idx ON impact_a3.t (id);
```

`migration.sql`:

```sql
ALTER TABLE impact_a3.t
  ADD COLUMN seen_at timestamptz DEFAULT pg_catalog.clock_timestamp();
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 2,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "applies",
      "table_rewrite": "yes",
      "table_scan": "yes",
      "index_rebuild": "yes",
      "lock": "AccessExclusiveLock",
      "risk": "critical",
      "evidence_ids": [
        "rule:add.volatile_valid",
        "function:pg_catalog.clock_timestamp()",
        "index:impact_a3_id_idx"
      ],
      "limitations_contains": [
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

**A4** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_a4 CASCADE;
CREATE SCHEMA impact_a4;
CREATE TABLE impact_a4.t (id int PRIMARY KEY);
```

`migration.sql`:

```sql
ALTER TABLE impact_a4.t ADD COLUMN required_col text NOT NULL;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 2,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "may_fail",
      "table_rewrite": "no",
      "table_scan": "possible",
      "index_rebuild": "no",
      "lock": "AccessExclusiveLock",
      "risk": "critical",
      "evidence_ids": ["rule:add.not_null.no_default"],
      "limitations_contains": [
        "Table emptiness is not proven from catalog evidence (n_live_tup is an estimate).",
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

**A5** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_a5 CASCADE;
CREATE SCHEMA impact_a5;
CREATE TABLE impact_a5.t (id int PRIMARY KEY);
ANALYZE impact_a5.t;
```

`migration.sql`:

```sql
ALTER TABLE impact_a5.t ADD COLUMN required_col text NOT NULL;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 2,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "may_fail",
      "table_rewrite": "no",
      "table_scan": "possible",
      "index_rebuild": "no",
      "lock": "AccessExclusiveLock",
      "risk": "critical",
      "evidence_ids": ["rule:add.not_null.no_default"],
      "limitations_contains": [
        "Table emptiness is not proven from catalog evidence (n_live_tup is an estimate).",
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

Comparator vs A4: assert equal semantic projection keys only (`outcome`, `exit_code`, and the card keys listed above). Do not require equal fingerprints, schema names, or affected_objects.

**D1** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_d1 CASCADE;
CREATE SCHEMA impact_d1;
CREATE TABLE impact_d1.t (
  id int PRIMARY KEY,
  obsolete text
);
CREATE INDEX impact_d1_obsolete_idx ON impact_d1.t (obsolete);
```

`migration.sql`:

```sql
ALTER TABLE impact_d1.t DROP COLUMN obsolete;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 1,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "applies",
      "table_rewrite": "no",
      "table_scan": "no",
      "index_rebuild": "no",
      "lock": "AccessExclusiveLock",
      "risk": "warning",
      "evidence_ids": ["rule:drop.internal_only"],
      "limitations_contains": [
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

**D2** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_d2 CASCADE;
CREATE SCHEMA impact_d2;
CREATE TABLE impact_d2.t (
  id int PRIMARY KEY,
  secret text
);
CREATE VIEW impact_d2.v AS SELECT id, secret FROM impact_d2.t;
```

`migration.sql`:

```sql
ALTER TABLE impact_d2.t DROP COLUMN secret RESTRICT;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 2,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "would_fail",
      "table_rewrite": "no",
      "table_scan": "no",
      "index_rebuild": "no",
      "lock": "AccessExclusiveLock",
      "risk": "critical",
      "evidence_ids": [
        "rule:drop.external_blocker_restrict",
        "dep:view:impact_d2.v"
      ],
      "limitations_contains": [
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

**D3** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_d3 CASCADE;
CREATE SCHEMA impact_d3;
CREATE TABLE impact_d3.t (
  id int PRIMARY KEY,
  secret text
);
CREATE VIEW impact_d3.v AS SELECT id, secret FROM impact_d3.t;
```

`migration.sql`:

```sql
ALTER TABLE impact_d3.t DROP COLUMN secret CASCADE;
```

`expected/common.json`:

```json
{
  "outcome": "completed",
  "exit_code": 2,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "applies",
      "table_rewrite": "no",
      "table_scan": "no",
      "index_rebuild": "no",
      "lock": "AccessExclusiveLock",
      "risk": "critical",
      "evidence_ids": [
        "rule:drop.cascade_external",
        "dep:view:impact_d3.v"
      ],
      "limitations_contains": [
        "Authorization failures are not modeled; analysis assumes sufficient privileges."
      ]
    }
  ]
}
```

**X1** — `setup.sql`:

```sql
DROP SCHEMA IF EXISTS impact_x1 CASCADE;
CREATE SCHEMA impact_x1;
CREATE TABLE impact_x1.t (id int PRIMARY KEY);
```

`migration.sql`:

```sql
ALTER TABLE impact_x1.t ADD COLUMN note text;
CREATE TABLE impact_x1.other (id int);
```

`expected/common.json`:

```json
{
  "outcome": "incomplete",
  "exit_code": 3,
  "cards": [
    {
      "analysis_status": "analyzed",
      "execution_prediction": "applies",
      "risk": "warning",
      "evidence_ids": ["rule:add.nullable.no_default"]
    },
    {
      "analysis_status": "unsupported_parser",
      "execution_prediction": "not_evaluated",
      "risk": "not_applicable"
    }
  ]
}
```

X2/X3 remain local-only (Task 2).

**Isolation:** each fixture schema starts with `DROP SCHEMA IF EXISTS` then `CASCADE`. Finalizer drops the same schema via admin connection.

#### Live §2 fixtures (exact paths)

| Test id | Paths | Normative setup | migration | Exact assertions |
| --- | --- | --- | --- | --- |
| `S2_shadow` | `tests/fixtures/impact/S2_shadow/` | see setup.sql; subject `search_path=impact_s2_a, impact_s2_b` | `ALTER TABLE t ADD COLUMN note text;` | `outcome=completed`; card `analysis_status=analyzed`; resolved table schema `impact_s2_a`; `impact_s2_b.t` is not the target; exit 1; evidence includes `rule:add.nullable.no_default` |
| `S2_partition` | `tests/fixtures/impact/S2_partition/` | partitioned parent | `ALTER TABLE impact_s2_p.t ADD COLUMN note text;` | `outcome=incomplete`; `exit_code=3`; card `analysis_status=unsupported_scope`; `execution_prediction=not_evaluated`; `risk=not_applicable` |
| `S2_inherit` | `tests/fixtures/impact/S2_inherit/` | inheritance parent | `ALTER TABLE impact_s2_i.parent ADD COLUMN note text;` | `outcome=incomplete`; `exit_code=3`; card `analysis_status=unsupported_scope`; `execution_prediction=not_evaluated`; `risk=not_applicable` |
| `S2_missing_if_exists` | `tests/fixtures/impact/S2_missing_if_exists/` | empty schema only | `ALTER TABLE IF EXISTS impact_s2_m.missing ADD COLUMN note text;` | `outcome=completed`; `exit_code=0`; `execution_prediction=no_op`; `no_op_reason=target_missing_if_exists`; `risk=safe` |
| `S2_scs_off` | `tests/fixtures/impact/S2_scs_off/` | minimal table; subject started with `PGOPTIONS=-c standard_conforming_strings=off` | `ALTER TABLE impact_s2_scs.t ADD COLUMN note text;` | `outcome=incomplete`; `exit_code=3`; `preflight.status=incomplete`; `statements=()`; preflight check records `standard_conforming_strings` observed `off` |
| `S2_rollback` | reuses T1 paths | apply T1 setup; run impact; compare admin catalog checksum before/after | T1 migration | relation/index definitions unchanged; `SELECT txid_current_if_assigned()` / no leftover open txn on subject after `run_impact` returns |

**Exact `S2_partition/setup.sql`:**

```sql
DROP SCHEMA IF EXISTS impact_s2_p CASCADE;
CREATE SCHEMA impact_s2_p;
CREATE TABLE impact_s2_p.t (id int NOT NULL, payload int) PARTITION BY RANGE (id);
CREATE TABLE impact_s2_p.t_p1 PARTITION OF impact_s2_p.t FOR VALUES FROM (0) TO (1000);
```

**Exact `S2_inherit/setup.sql`:**

```sql
DROP SCHEMA IF EXISTS impact_s2_i CASCADE;
CREATE SCHEMA impact_s2_i;
CREATE TABLE impact_s2_i.parent (id int PRIMARY KEY, payload int);
CREATE TABLE impact_s2_i.child () INHERITS (impact_s2_i.parent);
```

**Exact `S2_missing_if_exists/setup.sql`:**

```sql
DROP SCHEMA IF EXISTS impact_s2_m CASCADE;
CREATE SCHEMA impact_s2_m;
```

**Exact `S2_scs_off/setup.sql`:**

```sql
DROP SCHEMA IF EXISTS impact_s2_scs CASCADE;
CREATE SCHEMA impact_s2_scs;
CREATE TABLE impact_s2_scs.t (id int PRIMARY KEY);
```

**Exact `S2_shadow/setup.sql`:**

```sql
DROP SCHEMA IF EXISTS impact_s2_a CASCADE;
DROP SCHEMA IF EXISTS impact_s2_b CASCADE;
CREATE SCHEMA impact_s2_a;
CREATE SCHEMA impact_s2_b;
CREATE TABLE impact_s2_a.t (id int PRIMARY KEY);
CREATE TABLE impact_s2_b.t (id int PRIMARY KEY);
```

Subject connection for `S2_shadow` must use startup/`ConnectionConfig` search_path `impact_s2_a, impact_s2_b` so captured `current_schemas(true)` ranks `impact_s2_a` before `impact_s2_b`. Unqualified `t` resolves to `impact_s2_a.t` (first match). Presence of `impact_s2_b.t` must **not** yield `unsupported_resolution`.

**`S2_scs_off` subject startup (normative):**

```python
import os
from contextlib import contextmanager


@contextmanager
def subject_env_scs_off():
    previous = os.environ.get("PGOPTIONS")
    os.environ["PGOPTIONS"] = "-c standard_conforming_strings=off"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = previous
```

Test body:

1. `apply_setup_sql(admin_dsn, S2_scs_off/setup.sql)`
2. enter `subject_env_scs_off()`
3. call `run_impact` so libpq opens a **new** subject connection inheriting `PGOPTIONS`
4. assert preflight incomplete / empty statements as in the table above
5. in `finally`: restore env (context manager) and `drop_schema(admin_dsn, "impact_s2_scs")`
6. Do **not** alter role/database defaults for the shared CI user.

Create helper `tests/integration/impact/_fixture_admin.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

import psycopg

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Only schemas belonging to committed impact fixtures may be dropped by helpers.
FIXTURE_SCHEMA_REGISTRY: frozenset[str] = frozenset(
    {
        "impact_t1",
        "impact_t2",
        "impact_t3",
        "impact_a1",
        "impact_a2",
        "impact_a3",
        "impact_a4",
        "impact_a5",
        "impact_d1",
        "impact_d2",
        "impact_d3",
        "impact_x1",
        "impact_s2_a",
        "impact_s2_b",
        "impact_s2_p",
        "impact_s2_i",
        "impact_s2_m",
        "impact_s2_scs",
    }
)


def apply_setup_sql(admin_dsn: str, setup_path: Path) -> None:
    sql = setup_path.read_text(encoding="utf-8")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql)


def drop_schema(admin_dsn: str, schema: str) -> None:
    if schema not in FIXTURE_SCHEMA_REGISTRY or _SCHEMA_RE.fullmatch(schema) is None:
        raise ValueError(f"refusing to drop non-registry schema: {schema!r}")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(psycopg.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(psycopg.sql.Identifier(schema)))
```

Also assert live: RR+RO; capture before harden; effective search_path `{pg_catalog}` after harden; unqualified first-match order (`S2_shadow`); `pg_catalog.clock_timestamp()` FunctionSnapshot on A3.

- [ ] Steps 1–5: create fixtures + failing tests then implement harness

```bash
pytest tests/integration/impact -v
```

(requires `PGINSPECT_TEST_DSN`, `PGINSPECT_EXPECT_PG_MAJOR`)

```bash
git add tests/fixtures/impact tests/integration/impact
git commit -m "test(impact): add live Demo fixtures and design section 2 integration tests"
```

---

### Task 13: Safety gates — tests only

**Decision:** Task 5 already created `query_exec.py` and the recorder callback. **Task 13 must not modify production source.**

**Files (exhaustive):**
- Create: `tests/safety/impact/test_migration_never_executed.py`
- Create: `tests/safety/impact/test_query_allowlist.py`
- Create: `tests/safety/impact/test_schema_unchanged.py`
- Create: `tests/safety/impact/test_force_rollback.py`
- Create: `tests/safety/impact/_helpers.py`
- Modify: `tests/unit/test_package_boundaries.py`

**Wire test distinctions:**

```text
recorded event fields:
  query_id: str
  sql_text: str          # exact LiteralString from registry
  bound_parameters: tuple # may contain object names from migration
assert canary migration statement text not in sql_text
assert canary may appear only inside bound_parameters values if at all
```

**Allowlist test:**

```text
every executed query_id ∈ IMPACT_QUERY_REGISTRY
registry[query_id].sql is the exact LiteralString executed
mutating registry entry in test cannot change production mapping (frozen/mapping proxy)
```

- [ ] Steps 1–5 TDD + commit:

```bash
git add tests/safety/impact tests/unit/test_package_boundaries.py
git commit -m "test(impact): enforce allowlisted QuerySpec execution and non-execution of migration SQL"
```

**Layer review E.**

---

### Task 14: Schema export, CI, documentation

**Files:**
- Modify: `scripts/export_schemas.py` — export impact 0.1 with exact `$id` URNs; leave Foundation 1.0 generation unchanged
- Create: `scripts/compare_schemas_export.py` — export into a temp directory; fail if committed files differ **or** if generated paths are missing/untracked relative to expectation list
- Create: `docs/schemas/impact-command-result/0.1.schema.json`
- Create: `docs/schemas/impact-statement-card/0.1.schema.json`
- Create: `tests/unit/impact/test_schema_drift.py`
- Create goldens under `tests/schemas/goldens/impact_*.json`
- Modify: `.github/workflows/schema.yml` to run `python scripts/compare_schemas_export.py`
- Modify: `.github/workflows/integration.yml` — keep a single recursive collection command:
  `pytest tests/integration`
  (do **not** also pass `tests/integration/impact`; that double-collects)
- Modify: `.github/workflows/safety.yml` — keep:
  `pytest tests/safety`
  (do **not** also pass `tests/safety/impact`)
- Modify: `.github/workflows/coverage.yml` to include impact suites via the same recursive roots
- Modify: `.github/workflows/unit.yml` — confirm `tests/unit` recursion collects impact unit nodes once
- Modify: `README.md` — document `pginspect impact` as **prototype / private repository feature**, not a shipped reliable release
- Modify: `CHANGELOG.md` — under Unreleased/prototype note only

**compare script requirements:**

```text
temp export of finding/1.0, command-result/1.0, impact-command-result/0.1, impact-statement-card/0.1
byte-compare Foundation 1.0 to committed files (must be identical)
byte-compare impact 0.1 to committed files
fail if expected committed path missing (detects forgotten add of generated files)
fail if temp produced unexpected extra schema paths
```

**Acceptance — collection uniqueness:**

```bash
pytest --collect-only -q tests/unit tests/integration tests/safety > collect.txt
python -c "from collections import Counter; import pathlib; lines=[l.strip() for l in pathlib.Path('collect.txt').read_text(encoding='utf-8').splitlines() if '::' in l]; c=Counter(lines); dups=[(k,v) for k,v in c.items() if v>1]; assert not dups, dups; impact=[l for l in lines if '/impact/' in l.replace('\\\\','/') or 'impact' in l]; assert impact, 'no impact tests collected'; print('collect-ok', len(lines), 'impact', len(impact))"
```

**Explicit test commands for this task:**

```bash
pytest tests/unit/impact -q
pytest tests/unit/test_schema_drift.py tests/unit/impact/test_schema_drift.py -q
python scripts/compare_schemas_export.py
```

Live suites remain CI-gated with DSN via `pytest tests/integration` / `pytest tests/safety`.

- [ ] Commit:

```bash
git add scripts/export_schemas.py scripts/compare_schemas_export.py docs/schemas/impact-command-result docs/schemas/impact-statement-card tests/unit/impact/test_schema_drift.py tests/schemas/goldens .github/workflows README.md CHANGELOG.md
git commit -m "feat(impact): export 0.1 schemas with compare gate and CI suite wiring"
```

---

### Task 15: Demo-proof recordings + final CI re-gate

**Files:**
- Create: `scripts/record_impact_demo.py`
- Create: `docs/superpowers/demos/2026-07-29-impact-demo-proof.md`
- Create: `docs/superpowers/demos/recordings/T1.txt`
- Create: `docs/superpowers/demos/recordings/A4.txt`
- Create: `docs/superpowers/demos/recordings/D2.txt`
- Create: `docs/superpowers/demos/recordings/MANIFEST.json`

**`scripts/record_impact_demo.py` normative CLI:**

```text
python scripts/record_impact_demo.py --fixture T1 --out docs/superpowers/demos/recordings/T1.txt
python scripts/record_impact_demo.py --fixture A4 --out docs/superpowers/demos/recordings/A4.txt
python scripts/record_impact_demo.py --fixture D2 --out docs/superpowers/demos/recordings/D2.txt
```

Behavior (failure-safe):

```text
EXPECTED_EXIT = {"T1": 2, "A4": 2, "D2": 2}
SCHEMA = {"T1": "impact_t1", "A4": "impact_a4", "D2": "impact_d2"}
```

```python
def record_fixture(fixture: str, out_path: Path) -> int:
    admin_dsn = os.environ["PGINSPECT_TEST_DSN"]
    setup_path = Path(f"tests/fixtures/impact/{fixture}/setup.sql")
    migration_path = Path(f"tests/fixtures/impact/{fixture}/migration.sql")
    tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
    diag_path = out_path.with_suffix(out_path.suffix + ".stderr.txt")
    apply_setup_sql(admin_dsn, setup_path)
    try:
        proc = subprocess.run(
            ["pginspect", "impact", str(migration_path), "--format", "text"],
            check=False,
            capture_output=True,
            text=True,
        )
        diag_path.write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != EXPECTED_EXIT[fixture]:
            if tmp_out.exists():
                tmp_out.unlink()
            raise SystemExit(f"unexpected exit {proc.returncode} for {fixture}")
        tmp_out.write_text(proc.stdout, encoding="utf-8")
        for forbidden in ("password=", "PGPASSWORD", ":5432/", "/home/", "C:\\"):
            if forbidden in tmp_out.read_text(encoding="utf-8"):
                tmp_out.unlink()
                raise SystemExit(f"redaction failed for {fixture}: {forbidden}")
        os.replace(tmp_out, out_path)
        print(
            f"fixture={fixture} major={os.environ['PGINSPECT_RECORDING_MAJOR']}",
            file=sys.stderr,
        )
        return 0
    finally:
        drop_schema(admin_dsn, SCHEMA[fixture])
        if tmp_out.exists():
            tmp_out.unlink()
```

Rules:

1. Read admin `PGINSPECT_TEST_DSN` and subject libpq env only from environment (never argv).
2. Verify live major == `PGINSPECT_RECORDING_MAJOR` before setup.
3. Never write a partial report to `--out` on process failure; only `os.replace` after successful exit + redaction.
4. Keep `stderr` only in the diagnostic `*.stderr.txt` sidecar (not committed unless useful for debugging; default: gitignore or delete after success).
5. Metadata never enters the report file.

**MANIFEST.json (no self SHA):**

```json
{
  "recorded_against_commit": "<Task-14 HEAD SHA>",
  "recording_postgresql_major": 16,
  "recordings": [
    {
      "fixture_id": "T1",
      "command": ["python", "scripts/record_impact_demo.py", "--fixture", "T1", "--out", "docs/superpowers/demos/recordings/T1.txt"],
      "path": "docs/superpowers/demos/recordings/T1.txt"
    },
    {
      "fixture_id": "A4",
      "command": ["python", "scripts/record_impact_demo.py", "--fixture", "A4", "--out", "docs/superpowers/demos/recordings/A4.txt"],
      "path": "docs/superpowers/demos/recordings/A4.txt"
    },
    {
      "fixture_id": "D2",
      "command": ["python", "scripts/record_impact_demo.py", "--fixture", "D2", "--out", "docs/superpowers/demos/recordings/D2.txt"],
      "path": "docs/superpowers/demos/recordings/D2.txt"
    }
  ],
  "redaction_verification": {
    "forbidden_substrings_absent": ["password=", "PGPASSWORD", ":5432/", "/home/", "C:\\"]
  }
}
```

Replace `<Task-14 HEAD SHA>` with the actual Task-14 commit hash at recording time. Task-15 commit SHA is recorded only in final CI evidence, not inside MANIFEST.

**Exact recording commands:**

```bash
python scripts/record_impact_demo.py --fixture T1 --out docs/superpowers/demos/recordings/T1.txt
python scripts/record_impact_demo.py --fixture A4 --out docs/superpowers/demos/recordings/A4.txt
python scripts/record_impact_demo.py --fixture D2 --out docs/superpowers/demos/recordings/D2.txt
```

**Protocol doc** states design §5.7 human criteria; do not automate human study.

- [ ] Commit Task 15:

```bash
git add scripts/record_impact_demo.py docs/superpowers/demos
git commit -m "docs(impact): add Demo-proof protocol and redacted T1/A4/D2 recordings"
```

- [ ] **Final private push + CI re-gate (mandatory):**

```bash
git push origin HEAD:main
python -c "import subprocess; print(subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip())"
```

Then wait for all required workflow runs on that exact SHA (`unit`, `lint-type`, `schema`, `integration`, `safety`, `coverage`). Collect run IDs/URLs. Do not change visibility or publish. Green CI from Task 14 on an older SHA does **not** complete implementation.

---

## Deferred items

- DROP INDEX family
- pglast / libpg_query
- Authorization modeling (policy A)
- Partition/inheritance risk scoring beyond `unsupported_scope`
- Offline/HypoPG/EXPLAIN-engine/doctor
- Foundation 1.0 schema mutation
- Publication / PyPI / public visibility / `PUBLICATION_APPROVED`
- Legacy archive (Foundation A-08/A-10 track)
- Executing the human Demo-proof study

## Commit sequence

| Task | Commit |
| --- | --- |
| 0 | none |
| 1 | `feat(impact): add complete 0.1 contracts reusing Foundation ExecutionError` |
| 2 | `feat(impact): add LocalParsedScript loader with FSM limits and control ordinals` |
| 3 | `feat(impact): add major-aware ALTER grammar with PG14-18 keyword fixtures` |
| 4 | `feat(impact): add establish_impact_profile with normative RR timeline` |
| 5 | `feat(impact): add resolution, catalog QuerySpecs, and T1-T3 coercion evidence` |
| 6 | `feat(impact): apply sequence constraints on AnalysisUnit and shared rule contracts` |
| 7 | `feat(impact): implement full TYPE rule matrix` |
| 8 | `feat(impact): implement full ADD COLUMN rule matrix` |
| 9 | `feat(impact): implement full DROP COLUMN rule matrix` |
| 10 | `feat(impact): wire output-agnostic run_impact orchestration` |
| 11 | `feat(impact): add renderers and thin impact CLI without path I/O` |
| 12 | `test(impact): add live Demo fixtures and design section 2 integration tests` |
| 13 | `test(impact): enforce allowlisted QuerySpec execution and non-execution of migration SQL` |
| 14 | `feat(impact): export 0.1 schemas with compare gate and CI suite wiring` |
| 15 | `docs(impact): add Demo-proof protocol and redacted T1/A4/D2 recordings` |

## Implementation risks

1. Session timeline vs Foundation establish order
2. CoercionEvidence correctness (no invented `pg_cast`)
3. T2 PG14 vs 15–18 split
4. `pg_*_is_visible` regressions
5. Migration text leaking into SQL strings
6. Foundation 1.0 schema mutation / untracked 0.1 files
7. Lexer limit edge cases
8. Parallel 7–9 regressions if shared files touched

## Self-review (this revision)

- Task 4 timeouts use `SELECT pg_catalog.set_config(..., true)` as the first SELECT; `catalog_snapshot_at` precedes that SELECT.
- `S2_shadow` asserts first-match resolution to `impact_s2_a`, not `unsupported_resolution`.
- `S2_scs_off` uses `PGOPTIONS=-c standard_conforming_strings=off` for a new subject connection.
- Task 12 helpers are concrete (`apply_setup_sql` / `drop_schema` + registry); A5 has full `expected/common.json`.
- Tasks 7–9 use Variant B isolated worktrees + ordered cherry-pick before Layer review C.
- Task 15 recorder uses setup/try/finally, expected exit codes, temp file + atomic replace, stderr sidecar.
- No implementation authorized by this document.

---

**Authorization boundary:** writing-plans revision only. Do not implement, commit, or push until a separate owner command authorizes implementation.
