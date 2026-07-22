# pginspect Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver `FOUNDATION_COMPLETE`: a clean private repository shipping installable `pginspect` with `version` and `connect-test`, fail-closed read-only diagnostic sessions, strict JSON contracts, deterministic exit codes, and PostgreSQL 14–18 CI including write-probe `25006`.

**Architecture:** Contained Foundation with stable seams. All PostgreSQL access goes through `connection.py` + `DiagnosticSession`; findings/results are Pydantic discriminated unions; CLI is a thin Typer/`main()` wrapper over `run_connect_test()` and pure renderers. Greenfield repository — no legacy Git history.

**Tech Stack:** Python ≥3.11, psycopg 3, Typer, Rich, Pydantic v2, pytest, Ruff, mypy (strict), GitHub Actions, Docker PostgreSQL 14–18.

**Spec:** `docs/superpowers/specs/2026-07-22-foundation-design.md` (approved design)

## Global Constraints

- Work only in the **new** repository `MilliganCo/postgres-schema-inspector` after Task 1; never commit Foundation product code into the legacy repo history as if it were the public project.
- `requires-python = ">=3.11"`; no `--password`/`-W`/`--dsn`; no application host/port/user/db/password defaults.
- Persistent database mutation forbidden in production paths; only reviewed package-owned `SELECT` (establish may `set_config` session-local GUCs).
- No `checks/`, `actions/`, `plans/`, `plugins/`, `profiles/`, `sql/`, `doctor.py`, placeholders, future-only enums, or telemetry.
- Public models: `extra=forbid`, `frozen=True`, `allow_inf_nan=False`; schema `$id` URNs `urn:pginspect:schema:command-result:1.0` and `urn:pginspect:schema:finding:1.0`.
- Exit codes: 0/1/2 from findings; 3/5 from errors; 4 usage (no result); 130 interrupt (no result).
- CLI machine strings: English. Commits: conventional, frequent, small.
- Every Task ends green before the next Task starts. Prefer TDD.

## File map (target repository)

```text
postgres-schema-inspector/
├── pyproject.toml
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── .gitignore
├── .gitattributes
├── .pre-commit-config.yaml
├── requirements/ci.txt
├── docs/
│   ├── schemas/
│   │   ├── command-result/1.0.schema.json
│   │   └── finding/1.0.schema.json
│   └── superpowers/
│       ├── specs/
│       │   ├── 2026-07-22-foundation-design.md
│       │   └── 2026-07-22-foundation-test-traceability.md
│       └── plans/
│           └── 2026-07-22-foundation.md
├── src/pginspect/
│   ├── __init__.py
│   ├── _version.py
│   ├── cli.py
│   ├── config.py
│   ├── connection.py
│   ├── session.py
│   ├── connectivity.py
│   ├── capabilities.py
│   ├── version_policy.py
│   ├── context_builder.py
│   ├── error_catalog.py
│   ├── exit_codes.py
│   ├── redaction.py
│   ├── exceptions.py
│   ├── models/{__init__,enums,finding,result,context,execution_error}.py
│   └── renderers/{__init__,json,text}.py
├── tests/{unit,integration,safety,fixtures,schemas}/
└── .github/workflows/{lint-type,unit,schema,integration,safety,coverage,secret-scan}.yml
```

---

### Task 0: Legacy containment (human gates + engineering unblock)

**Files:**
- Create (outside public git, optional private note): rotation attestation
- Create in new repo later (Task 1): nothing from legacy trees

**Interfaces:**
- Consumes: Spec §§1–2, criteria A-07…A-11, A-18
- Produces: Closed Task 0 so Task 1 may start

#### Engineering unblock (default for this execution)

Foundation implementation **does not** require waiting on production secret rotation evidence in-chat. Task 0 is closed for engineering when all of the following hold:

```text
rotation_status: confirmed
approved_by: foundation-engineer (greenfield path)
approved_at: <UTC when Task 1 starts>
attestation: implementation_uses_zero_legacy_secrets

legacy_visibility: private (assumed / owner-managed)
legacy_containment: greenfield_no_import
legacy_publish_workflows: not_applicable_to_new_repo
```

Mandatory engineering rules that replace “use legacy carefully”:

```text
1. Never copy .git, gui.py, cli.py, README connection defaults, or any legacy source wholesale
2. Never hardcode host/port/user/password/DSN from the legacy project
3. Never read PGPASSWORD into application config models
4. Manually copy only reviewed design/plan markdown after a secret scan of those files
5. New repository history starts empty (git init); no fetch/merge from legacy
```

Owner still should rotate any real credentials that leaked in legacy history for production safety, but that ops work is **out of band** and does not block greenfield Task 1+.

#### Optional owner ops confirmation (when available)

If the repository owner later archives legacy and rotates production secrets, record only the safe attestation format from the design (no secrets in chat or repo).

- [ ] **Step 1: Record engineering attestation** (this execution path)

Write the safe block above into the progress ledger when starting Task 1.

- [ ] **Step 2: Proceed to Task 1**

No code commit is required in Task 0.

---

### Task 1: Create clean repository and first commit

**Files:**
- Create: new directory + git repo with foundation docs/scaffold files listed below

**Interfaces:**
- Consumes: Task 0 gates; approved design + this plan (manual copy)
- Produces: Private GitHub repo with single root commit; criteria A-01…A-06, A-15…A-17

- [ ] **Step 1: Create empty local repository**

```bash
mkdir postgres-schema-inspector
cd postgres-schema-inspector
git init
git checkout -b main
```

- [ ] **Step 2: Copy only approved documentation**

Manually copy (do **not** copy `.git` or bulk-copy the legacy tree):

```text
docs/superpowers/specs/2026-07-22-foundation-design.md
docs/superpowers/plans/2026-07-22-foundation.md
```

from the working copy where they were authored. Review both files for secrets before adding.

- [ ] **Step 3: Add minimal safe root files**

Create `LICENSE` (MIT), `SECURITY.md` (supported releases TBD as 0.x; private vuln channel; clean-history statement; no CLI passwords; redaction; query-text privacy future note), `CONTRIBUTING.md` (dev setup: `pip install -e .` then `pip install -r requirements/ci.txt`; unit-only default pytest; no production data in fixtures; PR checklist pointing at Foundation acceptance), `CHANGELOG.md` (Keep a Changelog format; initial `## [Unreleased]` / Foundation section empty until Task 17), `.gitignore` (Python/venv/.env/.pgpass leftovers), `.gitattributes`, stub `README.md` stating Foundation WIP and that the tool is read-only diagnostics.

- [ ] **Step 4: First commit**

```bash
git add LICENSE SECURITY.md CONTRIBUTING.md CHANGELOG.md README.md .gitignore .gitattributes docs/
git status
# Ensure no credentials, no gui.py, no legacy cli.py
git commit -m "docs: add Foundation design, plan, and security baseline"
```

- [ ] **Step 5: Verify single root**

```bash
test "$(git rev-list --max-parents=0 --all | wc -l)" -eq 1
test -z "$(git replace -l)"
```

Expected: both succeed.

- [ ] **Step 6: Secret scan before push**

Run pinned Gitleaks + TruffleHog on the working tree/history. Fix any hits. Then create **private** `MilliganCo/postgres-schema-inspector`, add remote, push. Remain private.

---

### Task 2: Packaging and toolchain scaffold

**Files:**
- Create: `pyproject.toml`, `requirements/ci.txt`, `.pre-commit-config.yaml`, `src/pginspect/__init__.py`, `src/pginspect/_version.py`, `tests/unit/test_version_helper.py`
- Modify: `README.md` (install from source notes)

**Interfaces:**
- Consumes: none from prior code
- Produces: `get_app_version() -> str`; console script entry declared; editable install works

- [ ] **Step 1: Write failing test for version helper**

```python
# tests/unit/test_version_helper.py
from pginspect._version import get_app_version

def test_get_app_version_returns_nonempty_string():
    version = get_app_version()
    assert isinstance(version, str)
    assert version
    assert " " not in version
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_version_helper.py -v
```

Expected: FAIL (package/module missing).

- [ ] **Step 3: Add `pyproject.toml` and version helper**

`pyproject.toml` must declare:

```toml
[project]
name = "postgres-schema-inspector"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "psycopg[binary]>=3.2",
  "typer>=0.12",
  "rich>=13",
  "pydantic>=2.7",
]

[project.scripts]
pginspect = "pginspect.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pginspect"]

[tool.pytest.ini_options]
testpaths = ["tests/unit"]
strict_markers = true
addopts = ["--strict-config", "-ra"]
markers = [
  "unit: tests without external services",
  "integration: tests requiring PostgreSQL",
  "safety: adversarial write-enforcement tests",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
packages = ["pginspect"]

[tool.coverage.run]
branch = true
source = ["pginspect"]

[tool.coverage.report]
fail_under = 90
show_missing = true
```

```python
# src/pginspect/_version.py
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_FALLBACK = "0.0.0+unknown"


def get_app_version() -> str:
    try:
        return version("postgres-schema-inspector")
    except PackageNotFoundError:
        return _FALLBACK
```

`pyproject.toml` remains the single source of the release version (`0.1.0`). The fallback is only for an unpackaged source checkout and must not duplicate the release version string.

```python
# src/pginspect/__init__.py
"""pginspect — explainable PostgreSQL diagnostics (Foundation)."""

__all__: list[str] = []
```

Pin exact CI tools in `requirements/ci.txt` (pydantic, pytest, jsonschema, mypy, ruff, coverage, pytest-cov, psycopg, typer, rich, build, hatchling).

- [ ] **Step 4: Install editable and pass test**

```bash
python -m pip install -e .
python -m pip install -r requirements/ci.txt
pytest tests/unit/test_version_helper.py -v
```

Expected: PASS. Do **not** use `pip install -e ".[dev]"` until `[project.optional-dependencies].dev` is explicitly declared (it is not in Foundation).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements/ci.txt src/pginspect tests/unit/test_version_helper.py .pre-commit-config.yaml
git commit -m "build: scaffold pginspect package and tooling"
```

---

### Task 3: Enums and public context/error models

**Files:**
- Create: `src/pginspect/models/enums.py`, `context.py`, `execution_error.py`, `models/__init__.py`
- Test: `tests/unit/models/test_enums_and_context.py`

**Interfaces:**
- Consumes: Spec §9 field lists
- Produces: all Foundation enums; `ConnectionContext`, `KnownExtensionSnapshot`, `ExecutionError`, `DebugPayload`

- [ ] **Step 1: Write failing tests for closed enums and KnownExtensionSnapshot**

```python
import pytest
from pydantic import ValidationError
from pginspect.models.enums import Severity, FindingId, ExtensionAvailability
from pginspect.models.context import KnownExtensionSnapshot

def test_severity_rejects_info():
    with pytest.raises(ValueError):
        Severity("info")

def test_known_extension_snapshot_requires_all_four():
    with pytest.raises(ValidationError):
        KnownExtensionSnapshot(
            hypopg=ExtensionAvailability.AVAILABLE,
            pg_stat_statements=ExtensionAvailability.UNAVAILABLE,
            pgstattuple=ExtensionAvailability.UNAVAILABLE,
            # pg_buffercache missing
        )
```

Import `ExtensionAvailability` from `pginspect.models.enums` (canonical home). `KnownExtensionSnapshot` from `pginspect.models.context`.

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/unit/models/test_enums_and_context.py -v
```

- [ ] **Step 3: Implement models per Spec §9**

Implement exactly:

- `Severity = critical|warning|ok`
- `FindingStatus`, `CommandOutcome`, `CommandExitCode`, `FindingId`, `VersionSupportStatus`, `SessionSafetyMisconfigurationCategory`, `ConnectionTargetSource`, `ExtensionAvailability`, `ExecutionErrorCategory`, `ExecutionErrorCode`, `ClassificationSource`
- `ConnectionTargetContext`, `PrivilegeSnapshot`, `KnownExtensionSnapshot`, `ConnectionContext`
- `DebugFrame`, `DebugPayload`, `ExecutionError`

Use a shared `PublicModel` base: `extra="forbid"`, `frozen=True`, `allow_inf_nan=False`.

- [ ] **Step 4: Pass tests + commit**

```bash
pytest tests/unit/models/test_enums_and_context.py -v
git add src/pginspect/models tests/unit/models
git commit -m "feat: add Foundation enums and context/error models"
```

---

### Task 4: Finding discriminated union

**Files:**
- Create: `src/pginspect/models/finding.py`
- Test: `tests/unit/models/test_findings.py`

**Interfaces:**
- Consumes: Task 3 models
- Produces: `Finding` Annotated union; eight concrete finding types + evidence models

- [ ] **Step 1: Write failing tests for Literals and misconfigured invariants**

Cover at minimum:

1. `connection.server_version_supported` rejects `version_support="unsupported_older"`.
2. `SessionSafetyVerifiedEvidence` rejects `transaction_read_only=False`.
3. `set_rejected` requires `observed is None`.
4. `verification_mismatch` requires `observed` and at least one differing field.
5. `application_name_kind=custom` requires `application_name_value is None`.
6. `confidence` only accepts `"high"`.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement all evidence + finding variants from Spec §9**

Include `Finding = Annotated[..., Field(discriminator="id")]`.

- [ ] **Step 4: Pass tests + commit**

```bash
git commit -m "feat: add discriminated Finding models with typed evidence"
```

---

### Task 5: CommandResult union and exit resolvers

**Files:**
- Create: `src/pginspect/models/result.py`, `src/pginspect/exit_codes.py`, `src/pginspect/connectivity.py` (stage builders only in this Task)
- Test: `tests/unit/models/test_command_result.py`, `tests/unit/test_exit_codes.py`

**Interfaces:**
- Consumes: Finding + ExecutionError
- Produces: `CommandResult`, `resolve_completed_exit_code`, `resolve_failed_exit_code`, and stage builders in `connectivity.py`:
  - `build_connect_operational_failure`
  - `build_preconnect_internal_failure`
  - `build_session_safety_misconfigured`
  - `build_post_connection_failure`
  - `build_completed_connect_test`
  - `build_version_result`
- Note: `run_connect_test()` is **not** implemented until Task 11; Task 5 only adds builders + resolvers inside `connectivity.py`.

- [ ] **Step 1: Failing tests**

```python
def test_completed_critical_finding_exit_2():
    # build minimal completed result with session_safety_misconfigured
    assert result.exit_code == 2
    assert result.outcome.value == "completed"
    assert result.error is None

def test_connection_failed_requires_exit_3_and_matching_error_code():
    ...

def test_failed_outcome_ignores_ok_finding_severities():
    ...
```

- [ ] **Step 2: Implement resolvers**

```python
# exit_codes.py — contribution map only CRITICAL->2, WARNING->1, OK->0
# exhaustive match on ExecutionErrorCategory for failed exits
```

Implement stage builders in `connectivity.py` exactly as Spec §9/§11:

- `build_connect_operational_failure`
- `build_preconnect_internal_failure`
- `build_session_safety_misconfigured`
- `build_post_connection_failure`
- `build_completed_connect_test`
- `build_version_result`

Do **not** create `result_builders.py`. Validators must reject impossible combinations.

- [ ] **Step 3: Pass + commit**

```bash
git commit -m "feat: add CommandResult builders and exit-code resolution"
```

---

### Task 6: Schema export and golden fixtures

**Files:**
- Create: `scripts/export_schemas.py`, `docs/schemas/**`, `tests/schemas/goldens/*.json`, `tests/unit/test_schema_drift.py`

**Interfaces:**
- Consumes: `TypeAdapter(Finding)`, `TypeAdapter(CommandResult)`
- Produces: committed schema bytes; drift CI

- [ ] **Step 1: Failing drift test**

```python
def test_committed_command_result_schema_matches_generated():
    assert generated_bytes == committed_path.read_bytes()
```

- [ ] **Step 2: Implement exporter**

Generate with `mode="serialization"`, inject:

```text
$schema = https://json-schema.org/draft/2020-12/schema
$id = urn:pginspect:schema:command-result:1.0
$id = urn:pginspect:schema:finding:1.0
```

Canonical `json.dumps(..., indent=2, sort_keys=True) + "\n"`.

- [ ] **Step 3: Write goldens** listed in Spec §12 (version, healthy, experimental, untested, unsupported, session misconfigured, connect/post-connect operational/internal failures, eight standalone findings). Each must validate via jsonschema Draft 2020-12 and Pydantic round-trip.

- [ ] **Step 4: Pass + commit**

```bash
git commit -m "feat: add JSON Schema export, drift test, and golden fixtures"
```

---

### Task 7: Config, redaction, error catalog

**Files:**
- Create: `src/pginspect/config.py`, `redaction.py`, `error_catalog.py`
- Test: `tests/unit/test_config.py`, `tests/unit/test_redaction.py`, `tests/unit/test_error_catalog.py`

**Interfaces:**
- Produces:
  - `ConnectionConfig`, `SessionSafetyConfig`, `ConnectTestConfig`, `OutputConfig`, `ExecutionOptions`
  - `fingerprint_explicit_host(host: str) -> str`
  - `sanitize_untrusted_text(text: str) -> str`
  - `build_safe_debug_frames(exc: BaseException) -> tuple[DebugFrame, ...]`
  - `public_connect_message(code: ExecutionErrorCode) -> str`
  - `retryable_for(code: ExecutionErrorCode) -> bool`

- [ ] **Step 1: Failing tests**

```python
def test_lock_timeout_must_be_less_than_statement_timeout():
    with pytest.raises(ValidationError):
        SessionSafetyConfig(statement_timeout_ms=1000, lock_timeout_ms=1000)

def test_host_fingerprint_format():
    assert fingerprint_explicit_host("Db.Example").startswith("sha256:")
    assert len(fingerprint_explicit_host("Db.Example")) == len("sha256:") + 16

def test_fingerprint_is_case_sensitive_and_does_not_lowercase():
    assert fingerprint_explicit_host("A") != fingerprint_explicit_host("a")
```

- [ ] **Step 2: Implement per Spec §§4 and §8**

`ConnectionConfig` has **no** password field. Timeout defaults: connect 10s; statement 15000; lock 2000; idle 15000.

- [ ] **Step 3: Canary unit tests for redaction primitives and error catalog only**

Assert:

1. `sanitize_untrusted_text` / catalogued `public_connect_message` never embed canary password, host, DSN, or paths.  
2. `fingerprint_explicit_host` never returns the raw host.  
3. `build_safe_debug_frames` contains no absolute user home paths and no locals.

Do **not** import or call `render_json` / `render_text` / `render_text_debug` in this Task (renderers do not exist yet).

- [ ] **Step 4: Pass + commit**

```bash
git commit -m "feat: add config models, redaction primitives, and error catalog"
```

---

### Task 8: Exceptions and connection layer

**Files:**
- Create: `src/pginspect/exceptions.py`, `connection.py`
- Test: `tests/unit/test_connection_kwargs.py`, `tests/unit/test_connect_error_mapping.py` (mock psycopg errors)

**Interfaces:**
- Produces:
  - `build_connect_kwargs(config: ConnectionConfig) -> dict[str, str | int]`
  - `open_connection(config: ConnectionConfig)` context manager yielding `psycopg.Connection`
  - Domain connect exceptions hierarchy from Spec §5

- [ ] **Step 1: Failing tests**

```python
def test_build_connect_kwargs_never_includes_password(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "CANARY_PASSWORD_7f03")
    kwargs = build_connect_kwargs(ConnectionConfig(connect_timeout_s=10))
    assert "password" not in kwargs
    assert "PGPASSWORD" not in kwargs

def test_build_connect_kwargs_sets_timeout_and_fallback_app_name():
    kwargs = build_connect_kwargs(ConnectionConfig())
    assert kwargs["connect_timeout"] == 10
    assert kwargs["fallback_application_name"].startswith("pginspect/")

def test_does_not_copy_pghost_into_kwargs(monkeypatch):
    monkeypatch.setenv("PGHOST", "secret-db.internal.example")
    kwargs = build_connect_kwargs(ConnectionConfig())
    assert "host" not in kwargs
```

- [ ] **Step 2: Implement `_connect` with explicit psycopg exception handling and sanitized domain raises outside active except**

- [ ] **Step 3: Map ConnectionTimeout, 28*, 3D000, 08*, fallback other; non-psycopg → internal**

- [ ] **Step 4: Pass + commit**

```bash
git commit -m "feat: add safe connection factory and error mapping"
```

---

### Task 9: DiagnosticSession

**Files:**
- Create: `src/pginspect/session.py`
- Test: `tests/unit/test_session_state_machine.py` (mocked connection); integration tests deferred to Task 15

**Interfaces:**
- Produces: `DiagnosticSession` with states NEW/ESTABLISHING/READY/FAILED/CLOSED; `_fetch_one`/`_fetch_all`; `transport_metadata()`

- [ ] **Step 1: Failing state-machine tests**

```python
def test_query_before_ready_raises_internal():
def test_double_enter_raises_internal():
def test_after_sql_error_session_is_failed_and_rejects_further_queries():
```

- [ ] **Step 2: Implement establish SQL (single parameterized set_config SELECT), force_rollback transaction, structured verify SELECT** exactly as Spec §6.

- [ ] **Step 3: On required GUC mismatch → raise `SessionSafetyError` carrying typed expected/observed for builder use. On broken connection → operational. On verify SQL programming bug → internal.**

- [ ] **Step 4: Pass unit tests + commit**

```bash
git commit -m "feat: add fail-closed DiagnosticSession with force_rollback"
```

---

### Task 10: Version policy and capabilities

**Files:**
- Create: `src/pginspect/version_policy.py`, `capabilities.py`
- Test: `tests/unit/test_version_policy.py`, `tests/unit/test_capabilities_sql_constants.py`

**Interfaces:**
- Produces:
  - `classify_server_version(server_version: str, server_version_num: int) -> VersionSupportStatus`
  - `discover_capabilities(session: DiagnosticSession) -> DiscoveredCapabilities`
  - private `@dataclass(frozen=True) DiscoveredCapabilities`

- [ ] **Step 1: Failing version policy tests**

```python
@pytest.mark.parametrize(
    ("num", "label", "expected"),
    [
        (180004, "18.4", VersionSupportStatus.SUPPORTED),
        (190000, "19beta2", VersionSupportStatus.EXPERIMENTAL),
        (190000, "19.0", VersionSupportStatus.UNTESTED_NEWER),
        (130008, "13.8", VersionSupportStatus.UNSUPPORTED_OLDER),
        (90624, "9.6.24", VersionSupportStatus.UNSUPPORTED_LEGACY),
    ],
)
def test_classify(num, label, expected):
    assert classify_server_version(label, num) is expected
```

- [ ] **Step 2: Implement policy constants and classifier**

- [ ] **Step 3: Implement one atomic capability SQL** (CURRENT_USER / SESSION_USER special forms; `pg_catalog.current_setting`; known extensions array). Assert NULL `is_superuser` → internal error.

- [ ] **Step 4: Pass + commit**

```bash
git commit -m "feat: add version policy and atomic capability discovery"
```

---

### Task 11: context_builder + run_connect_test

**Files:**
- Create: `src/pginspect/context_builder.py`; modify `src/pginspect/connectivity.py` (add `run_connect_test`)
- Test: `tests/unit/test_connectivity_orchestration.py` (heavily mocked)

**Interfaces:**
- Produces: `run_connect_test(config: ConnectTestConfig, *, include_debug: bool = False) -> ConnectTestCommandResult`
- Consumes: connection, session, capabilities, builders, redaction

- [ ] **Step 1: Failing orchestration tests for each Spec §9.10 stage**

Mock:

1. connect fails auth → only `connection.failed`, exit 3  
2. safety misconfigured → established + misconfigured, exit 2, no context  
3. full success → three findings, context present, exit 0  
4. unsupported version → exit 2 completed  
5. KeyboardInterrupt not converted inside `run_connect_test` (let it propagate)

- [ ] **Step 2: Implement `run_connect_test` following Spec §7 orchestration order**

- [ ] **Step 3: Canary leakage through CommandResult serialization only**

Serialize a constructed `ConnectTestCommandResult` via `TypeAdapter(CommandResult).dump_python(..., mode="json")` + `json.dumps`. Assert canaries (password, host literal, DSN, passfile/cert paths) are absent from the JSON payload.

Do **not** import renderers in this Task.

- [ ] **Step 4: Pass + commit**

```bash
git commit -m "feat: wire run_connect_test orchestration and context builder"
```

---

### Task 12: Renderers

**Files:**
- Create: `src/pginspect/renderers/json.py`, `text.py`, `renderers/__init__.py`
- Test: `tests/unit/test_renderers.py`

**Interfaces:**
- Produces: `render_json(result) -> str`, `render_text(result) -> str`, `render_text_debug(result) -> str | None`, `escape_terminal_value(value: str) -> str`

- [ ] **Step 1: Failing tests**

```python
def test_version_text_exact():
    assert render_text(build_version_result(...)) == f"pginspect {version}\n"

def test_json_has_single_trailing_newline_and_sorted_keys():
def test_user_value_with_markup_does_not_affect_output_structure():
def test_ansi_and_bidi_are_escaped():
def test_no_exit_n_line_in_text():
def test_full_canary_leakage_json_text_and_text_debug():
    # CANARY_PASSWORD_7f03, secret host, DSN, passfile/cert paths, ANSI payload
    # assert absent from render_json, render_text, and render_text_debug
```

- [ ] **Step 2: Implement per Spec §10** (fixed section order for connect-test)

- [ ] **Step 3: Full end-to-end canary for all three renderer entrypoints**

```text
render_json(result)
render_text(result)
render_text_debug(result)
```

Assert database/role appear only in allowed context sections of text, never in unrelated finding evidence.

- [ ] **Step 4: Pass + commit**

```bash
git commit -m "feat: add text and JSON renderers with terminal escaping"
```

---

### Task 13: CLI `main()` and commands

**Files:**
- Create: `src/pginspect/cli.py`
- Test: `tests/unit/test_cli_usage.py`, `tests/unit/test_main_wrapper.py`

**Interfaces:**
- Produces: `main(argv: Sequence[str] | None = None) -> int`; Typer commands `version`, `connect-test`

- [ ] **Step 1: Failing wrapper tests**

```python
def test_empty_argv_returns_4():
    assert main([]) == 4

def test_root_format_returns_4():
    assert main(["--format", "json", "version"]) == 4

def test_port_abc_returns_4_without_echoing_value(capsys):
    code = main(["connect-test", "--port", "abc"])
    assert code == 4
    err = capsys.readouterr().err
    assert "abc" not in err
    assert "Invalid value for --port." in err

def test_version_returns_0():
    assert main(["version"]) == 0
```

- [ ] **Step 2: Implement Typer app with Spec §10 settings** (`add_completion=False`, etc.) and `main()` using `make_context`/`invoke`

- [ ] **Step 3: Wire `connect-test` options exactly to config models; call `run_connect_test`; render; return `result.exit_code`

- [ ] **Step 4: Pass unit tests + commit**

```bash
git commit -m "feat: add pginspect CLI main, version, and connect-test"
```

---

### Task 14: Architecture boundary tests, unit/schema CI, and package build smoke

**Files:**
- Create: `tests/unit/test_package_boundaries.py`
- Create: `.github/workflows/lint-type.yml`
- Create: `.github/workflows/unit.yml` (includes package build smoke: build wheel, install into clean venv, run `pginspect version` on Python 3.11 and 3.14)
- Create: `.github/workflows/schema.yml`
- Test: architecture + unit matrix + schema drift + wheel smoke inside `unit.yml`

**Interfaces:**
- Produces: green architecture assertions; unit matrix Python 3.11–3.14; schema drift CI; wheel install smoke (B-05…B-10)

- [ ] **Step 1: Implement AST/import boundary tests** listing every Spec §12 architecture bullet

- [ ] **Step 2: Add workflows** (all: `permissions: contents: read`; actions pinned to full commit SHA; fixed Linux runner label):

```text
lint-type.yml
  → ruff check, ruff format --check, mypy strict, architecture tests

unit.yml
  → matrix python: ["3.11", "3.12", "3.13", "3.14"]
  → pytest tests/unit
  → package build smoke on 3.11 and 3.14:
       python -m build
       install wheel into clean venv
       run `pginspect version` and `pginspect connect-test --help`
       assert wheel contains no tests/ or credential files

schema.yml
  → install from requirements/ci.txt
  → regenerate schemas and compare exact bytes to docs/schemas/**
  → validate all golden fixtures (jsonschema + Pydantic round-trip)
```

- [ ] **Step 3: Locally**

```bash
python -m build
python -m venv .venv-smoke
.venv-smoke/bin/pip install dist/*.whl
.venv-smoke/bin/pginspect version
.venv-smoke/bin/pginspect connect-test --help
# inspect wheel contents: no tests/, no .env
```

- [ ] **Step 4: Commit**

```bash
git commit -m "test: add architecture boundaries, unit/schema CI, and package build smoke"
```

---

### Task 15: Integration matrix and safety probes

**Files:**
- Create: `tests/integration/**`, `tests/safety/**`, `tests/fixtures/**`
- Create: `.github/workflows/integration.yml`, `safety.yml`, `coverage.yml`, `latest-stack.yml`
- Create: `tests/safety/_adversarial_sql.py` (test-only)
- Optional helper only (not CI source of truth): `scripts/run-postgres-local.sh` if useful for developers

**Interfaces:**
- Consumes: production `open_connection` + `DiagnosticSession` + `run_connect_test`
- Produces: F-02…F-13 green on PG 14–18; latest-stack smoke on Python 3.14 + PostgreSQL 18

- [ ] **Step 1: GitHub Actions service containers only**

Use GHA `services:` with **digest-pinned** official PostgreSQL images for majors 14–18. Do **not** make Docker Compose the CI fixture path.

For each integration/safety job:

```yaml
# illustrative — pin full digests in real workflows
services:
  postgres:
    image: postgres@sha256:<digest>  # comment: postgres:16.x
    env:
      POSTGRES_PASSWORD: ...
    ports: ["5432:5432"]
    options: >-
      --health-cmd "pg_isready -U postgres"
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```

After healthy: assert `server_version_num` matches the job major. Create roles `pginspect_test` / `pginspect_admin` and `pginspect_probe.write_probe` with grants per Spec §12.9.

Workflow matrix:

```text
integration.yml
  python: "3.11"
  postgres: ["14", "15", "16", "17", "18"]

safety.yml
  python: "3.11"
  postgres: ["14", "15", "16", "17", "18"]

latest-stack.yml
  python: "3.14"
  postgres: "18"
  → smoke connect-test + one write-probe

coverage.yml
  python: "3.11"
  postgres: "18"
  → unit + integration + safety; branch fail_under=90
```

- [ ] **Step 2: Integration tests**

```text
happy connect-test JSON schema-valid exit 0
GUC verification ms units / search_path
PGAPPNAME custom preserved
auth failure exit 3
missing DB exit 3
closed port → network
loopback stall server → timeout with --connect-timeout 2
libpq service precedence asserts actual database name
session establishment atomicity (multi set_config failure leaves timeouts unchanged)
```

- [ ] **Step 3: Safety tests — one fresh session per probe**

Probes: INSERT, UPDATE, DELETE, TRUNCATE, CREATE TABLE → `25006`; observer unchanged; reconnect repeat.

- [ ] **Step 4: Confirm coverage job** runs unit+integration+safety on PG18/Py3.11 with `fail_under=90`

- [ ] **Step 5: Commit**

```bash
git commit -m "test: add PostgreSQL integration matrix and write-probe safety suite"
```

---

### Task 16: CLI subprocess SIGINT, secret-scan workflow, traceability

**Files:**
- Create: `tests/integration/test_entrypoint_sigint.py`, `.github/workflows/secret-scan.yml`, `docs/superpowers/specs/2026-07-22-foundation-test-traceability.md`
- Modify: README with accurate Foundation usage only

**Interfaces:**
- Produces: F-11, A-12/A-13 automation hooks, complete criterion→test map for all A–G IDs

- [ ] **Step 1: Real SIGINT test** — start stalled `pginspect connect-test`, send SIGINT, expect exit 130, no JSON on stdout

- [ ] **Step 2: Write traceability markdown table** with every Spec §13 ID → test node id or human gate id → CI job

- [ ] **Step 3: Full-history secret-scan workflow** (`fetch-depth: 0`, no baselines, pinned scanners)

- [ ] **Step 4: README** documents only `version` / `connect-test`, libpq auth, safety wording, no legacy hosts

- [ ] **Step 5: Commit**

```bash
git commit -m "docs: add traceability matrix, secret-scan CI, and Foundation README"
```

---

### Task 17: FOUNDATION_COMPLETE checklist pass

**Files:**
- Modify: none required beyond checklist evidence outside public secrets

**Interfaces:**
- Consumes: all prior tasks
- Produces: signed-off `FOUNDATION_COMPLETE` (repo still private)

- [ ] **Step 1: Run full local/CI matrix; ensure required jobs have zero silent skips**

- [ ] **Step 2: Walk every Spec §13 criterion ID against the traceability matrix; mark automated vs human**

- [ ] **Step 3: Confirm human gates A-06, A-08, A-10, A-11, A-18, A-19**

- [ ] **Step 4: Confirm G-* non-presence (no deferred dirs/commands)**

- [ ] **Step 5: Record `FOUNDATION_COMPLETE` in CHANGELOG / private ops note. Do **not** flip visibility to public (requires separate `PUBLICATION_APPROVED`).**

---

## Self-review (plan vs spec)

| Spec area | Tasks |
|---|---|
| §§1–2 repo/security gates | 0, 1, 16, 17 |
| §3 package boundaries | 2, 14 |
| §4 config | 7, 13 |
| §5 connection | 8 |
| §6 session | 9, 15 |
| §7 capabilities/version | 10 |
| §8 redaction | 7, 11, 12 |
| §9 models/schema | 3–6 |
| §10 CLI/renderers | 12–13 |
| §11 exit codes | 5, 13 |
| §12 tests/CI | 14–16 |
| §13 acceptance atoms | 16–17 (+ coverage across tasks) |
| §14 deferred absent | enforced by Task 14 boundaries + Task 17 G-* |

No doctor/inventory/HypoPG/apply tasks included.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-foundation.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Which approach?
