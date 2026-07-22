# pginspect Foundation Design

**Date:** 2026-07-22  
**Status:** approved design (pre-implementation)  
**Scope:** Foundation / Week 1 only  
**Product:** `pginspect` (`postgres-schema-inspector`)  
**Outcome states:** `FOUNDATION_COMPLETE` (private) → later `PUBLICATION_APPROVED` (public)

This document defines architecture and contracts for Foundation. It contains no implementation code. Deferred features are documented only as non-goals.

---

## 1. Repository and legacy isolation

```yaml
repository_strategy: greenfield
legacy_repository: MilliganCo/database-count-and-truncate
legacy_role: private_read_only_archive
new_repository: MilliganCo/postgres-schema-inspector
history_migration: forbidden
automated_source_import: forbidden
source_transfer: manual_reviewed_reimplementation
initial_visibility: private
target_visibility: public
```

### Target layout

```text
MilliganCo/database-count-and-truncate  # private legacy archive
MilliganCo/postgres-schema-inspector    # new clean history (private first)
```

### Forbidden

- fork of legacy; orphan branch inside legacy; `git filter-repo` as public basis
- cherry-pick; copying `.git`; GitHub import; transferring changelog as product history
- bulk copy of the working tree
- Git bundle, patch series, release archive, GitHub Actions artifact, generated source archive, or repository export produced from the legacy repository

### Allowed

- new MIT LICENSE, SECURITY.md, .gitignore, .gitattributes, pyproject.toml
- package scaffold, tests, CI
- manually reviewed reimplementation of safe ideas from legacy `cli.py` under the new architecture
- `truncate` / GUI / password CLI are not transferred into Foundation

### History invariant

> Public repository history must originate from a new Git repository. No commit, tree, tag, branch, reflog, artifact, or automated import from the legacy repository may be included. Legacy source may only be used as a private reference for manually reviewed reimplementation.

Release-reachable history must contain exactly one root commit; all other release-reachable commits are its descendants. No imported branches, tags, bundles, grafts, or replace refs. Machine checks:

```bash
test "$(git rev-list --max-parents=0 --all | wc -l)" -eq 1
test -z "$(git replace -l)"
```

Independent history provenance also requires a human attestation gate (Git cannot prove absence of manual copy/paste).

### Legacy retention

```yaml
legacy_retention:
  visibility: private
  deletion_required: false
  archival_status: archived_or_named_owner_exception
  new_development: forbidden
```

Rename to `*-legacy` is optional. Archive on GitHub is preferred; if not yet possible, a named owner exception plus a tracked archive follow-up task is required for `FOUNDATION_COMPLETE`.

### Creation order (summary)

1. Confirm credential rotation.  
2. Optionally rename/describe legacy as archive.  
3. `mkdir postgres-schema-inspector && git init`.  
4. Create empty GitHub repo `MilliganCo/postgres-schema-inspector` (private).  
5. First commit: safe foundation files only.  
6. Gitleaks + TruffleHog before first push.  
7. Push private. Remain private until `PUBLICATION_APPROVED`.

---

## 2. Security invariants and publication gates

### Invariants

```yaml
security_invariants:
  clean_history: required
  application_connection_defaults: forbidden   # no app host/port/user/db/password defaults
  cli_password_value: forbidden
  diagnostic_session_read_only: required
  persistent_database_mutation: forbidden
  ci_write_enforcement_sqlstate: "25006"
  redaction_always_enabled: true
  destructive_foundation_commands: forbidden
  repository_secrets: forbidden
  no_telemetry_or_unexpected_egress: required
```

Session-local establishment of safety GUCs through the reviewed `set_config` statement is the only intentional runtime state change. Persistent database objects and data are never modified.

### Diagnostic session (establish vs verify)

Each diagnostic session **establishes and verifies** required safety characteristics:

```yaml
diagnostic_session:
  establishes:
    default_transaction_read_only: on
    statement_timeout: nonzero
    lock_timeout: nonzero
    idle_in_transaction_session_timeout: nonzero
    search_path: pg_catalog
  verifies:
    default_transaction_read_only: on
    transaction_read_only: on
    statement_timeout: expected (ms)
    lock_timeout: expected (ms)
    idle_in_transaction_session_timeout: expected (ms)
    search_path: expected
  observes_not_gated:
    application_name: kind only for safety decisions
```

`application_name` is set at connect via `fallback_application_name=pginspect/<version>` (libpq). User `PGAPPNAME` / service override is preserved. Empty/custom names are not safety failures.

### `connect-test` mutation policy

`connect-test` executes only reviewed package-owned `SELECT` statements. The establish statement intentionally changes session-local GUCs; all remaining statements are non-mutating catalog or settings reads. No DML, DDL, maintenance, procedure calls, or write probe.

```yaml
write_probe: not_run
verification_level: settings
```

CLI wording: “Read-only configuration verified. No write probe was executed.”  
Never: “Database user cannot write.”

### Credential sources

```yaml
credential_sources:
  pgpass: allowed
  pgpassfile: allowed
  pgservice: allowed
  environment: allowed          # including PGPASSWORD for isolated CI; not recommended UX
  cli_password_value: forbidden
  interactive_password_prompt: deferred
```

pginspect defines **no** application-level defaults for host, port, user, database, or password; connection defaults are delegated to libpq.

### Debug vs redaction

Debug may expose stack structure and additional diagnostic context, but must **never** disable credential, DSN, connection-option, or sensitive-value redaction. Raw driver text is never retained, even under `--debug`.

### CI write enforcement

Throwaway Postgres; subject role has real write grants on a persistent probe table. Each probe uses a fresh connection + `DiagnosticSession`. Expected SQLSTATE `25006`. Observer/admin connection verifies unchanged state. Repeat after reconnect. Covers INSERT/UPDATE/DELETE/TRUNCATE/CREATE TABLE.

### Gates

```yaml
pre_push_gate:
  legacy_credentials_rotated: required   # human
  staged_content_reviewed: required      # human
  gitleaks_scan: required
  trufflehog_scan: required

pre_publication_gate:
  foundation_complete: required
  full_git_history_scan: required        # both scanners, fetch-depth 0, no baselines
  working_tree_scan: required
  ci_artifact_review: required
  dependency_and_license_review: required
  security_checklist_approved: required  # human
```

Full-history scans must already pass while the repo is private (`FOUNDATION_COMPLETE`). Publication repeats scans on the exact release commit.

Credential rotation evidence stores only safe facts (`rotation_status`, approver, UTC time) outside the public tree — never secret values.

`SECURITY.md` is required in the first commit.

---

## 3. Package boundaries

### Approach

**Contained Foundation with stable seams:** implement only Foundation modules; do not create empty future packages.

### Layout

```text
src/pginspect/
  __init__.py
  _version.py
  cli.py
  config.py
  connection.py
  session.py
  connectivity.py          # run_connect_test orchestration
  capabilities.py
  version_policy.py
  context_builder.py
  error_catalog.py
  exit_codes.py
  redaction.py
  exceptions.py
  models/
    __init__.py
    enums.py
    finding.py
    result.py
    context.py
    execution_error.py
  renderers/
    __init__.py
    json.py
    text.py
```

### Foundation Python API

```text
Supported:
  CLI entry point (pginspect.cli:main)
  internal/test imports of run_connect_test and public models

Not promised:
  stable third-party Python API
```

### Responsibilities

| Module | Owns | Must not |
|---|---|---|
| `cli.py` | Typer app, `main()`, argv→configs, render I/O, return exit ints | SQL, psycopg, Finding construction |
| `config.py` | typed connection/session intent, CLI validation, precedence of **explicit CLI** fields | opening connections; reading/copying PG\* into kwargs; `.pgpass` parsing |
| `connection.py` | `build_connect_kwargs`, `psycopg.connect(autocommit=True)`, map connect errors, close | session GUCs, findings, capability SQL |
| `session.py` | `DiagnosticSession` establish/verify, force_rollback txn, fail-closed state machine | CLI, rendering |
| `connectivity.py` | `run_connect_test` → stage builders → `ConnectTestCommandResult` | Typer, streams |
| `capabilities.py` | one atomic discovery SELECT → private `DiscoveredCapabilities` | support policy decisions; public context |
| `version_policy.py` | supported / experimental / untested / unsupported classification | SQL |
| `context_builder.py` | public `ConnectionContext` / target fingerprint | redaction primitives ownership |
| `error_catalog.py` | catalogued public messages, retryability table | model construction beyond messages |
| `redaction.py` | fingerprint, sanitize_untrusted_text, safe debug frames | business models |
| `exceptions.py` | domain exception types | serializable `ExecutionError` |
| `models/` | public Pydantic contracts | I/O |
| `renderers/` | pure string renderers from `CommandResult` | psycopg, Typer, connecting, redaction |

### DB access rule

- Only `connection.py` creates/closes raw `psycopg.Connection`.
- Only `DiagnosticSession` owns SQL execution surface (package-private `_fetch_*`).
- `capabilities.py` and future checks receive `DiagnosticSession`, never raw connection/cursor.
- Psycopg types must not appear in models or renderers.

### Absent directories / modules

No `checks/`, `actions/`, `plans/`, `plugins/`, `profiles/`, `sql/`, `doctor.py`. No check base classes, plugin protocols, or generic SQL loader.

### Runtime stack

```yaml
python: ">=3.11"
db_driver: psycopg3
cli: typer
terminal: rich
models: pydantic-v2
packaging: src-layout + pyproject.toml
```

### Entry point

```toml
[project.scripts]
pginspect = "pginspect.cli:main"
```

### JSON Schema source of truth

Schemas under `docs/schemas/` are generated from Pydantic (`TypeAdapter(...).json_schema(mode="serialization")`). CI fails on drift.

---

## 4. Configuration resolution

### Split configs

```text
ConnectionConfig      # service, host, port, dbname, user, sslmode, connect_timeout_s
SessionSafetyConfig   # statement/lock/idle timeouts
OutputConfig          # format only
ExecutionOptions      # include_debug
ConnectTestConfig     # connection + session
```

`ConnectionConfig`, `SessionSafetyConfig`, `ConnectTestConfig`, `OutputConfig`, and `ExecutionOptions` live in `config.py`.

`run_connect_test(config, *, include_debug=False)` receives `ConnectTestConfig` + debug flag. `OutputConfig` stays in CLI only.

### Sources

```yaml
configuration_sources:
  cli_options: true
  libpq_environment: true          # left in process env for libpq
  environment_parsed_by_pginspect: false
  service_files_parsed_by_pginspect: false
  project_toml: false
  stored_credentials: false
  cli_password_value: false
```

### Precedence (libpq-compatible)

```text
1. Explicit CLI fields as direct connection parameters
2. Service selected by --service (overrides PGSERVICE)
3. Parameters from selected service
4. Remaining PG* environment defaults
5. Libpq built-in defaults
```

pginspect must **not** copy `PGHOST` etc. into kwargs (that would incorrectly override service).

### Timeouts

```yaml
connect_timeout_s: {default: 10, min: 2, max: 60, zero_forbidden: true}
statement_timeout_ms: {default: 15000, min: 1, max: 300000}
lock_timeout_ms: {default: 2000, min: 1, max: 60000}
idle_in_transaction_session_timeout_ms: {default: 15000, min: 1, max: 300000}
```

`lock_timeout_ms` must be **strictly less than** `statement_timeout_ms` (configuration error → exit 4).

`connect_timeout` is always passed as a direct parameter (overrides env/service).

### SslMode

`disable | allow | prefer | require | verify-ca | verify-full`

### `build_connect_kwargs`

Returns kwargs for `psycopg.connect`, never a DSN string; never includes password; always includes:

```text
connect_timeout
fallback_application_name = "pginspect/<version>"
```

plus non-None: `service`, `host`, `port`, `dbname`, `user`, `sslmode`.

### CLI usage exit 4

Typer/Click usage errors are remapped by `main()` to exit **4** (Click default 2 is not used as process exit). Help → 0.

---

## 5. Connection lifecycle

```text
ConnectionConfig
  → build_connect_kwargs()
  → psycopg.connect(autocommit=True, **kwargs)
  → map expected Psycopg errors with structured signals
  → sanitized domain exception (no raw cause/context)
  → yield raw connection in custom context manager
  → DiagnosticSession owns SQL/txn
  → unconditional close
```

`autocommit` is a Psycopg argument, not a libpq kwarg.

Do **not** use `with psycopg.connect() as conn` (native CM commits on success).

### Domain exceptions

```text
PginspectError
├── PginspectConfigurationError
├── PginspectConnectError
│   ├── ConnectAuthenticationError
│   ├── ConnectNetworkError
│   ├── ConnectTimeoutError
│   ├── ConnectTlsError
│   ├── ConnectDatabaseMissingError
│   └── ConnectFailedError
├── SessionSafetyError
└── PginspectInternalError
```

Avoid shadowing builtins (`ConnectionError`, `TimeoutError`, `InternalError`).

### Classification order

1. `psycopg.errors.ConnectionTimeout` → timeout  
2. sqlstate `3D000` → database_missing  
3. sqlstate prefix `28` → authentication_failed  
4. `pgconn.needs_password` (transient read only) → authentication_failed  
5. sqlstate prefix `08` → network  
6. audited TLS-specific signal only → tls  
7. else → other  

Ambiguous text → `other`. Evidence may include `classification_source` and `sqlstate`.

Non-Psycopg unexpected exceptions during connect → internal (exit 5), **not** `connection.failed`.

### KeyboardInterrupt

No Finding / CommandResult; wrapper → 130. Does not map to `connection.failed`.

### Transport metadata

`DiagnosticSession.transport_metadata()` → `tls_used: true|false|null`. Never read password/DSN/`get_parameters()`/repr surfaces.

---

## 6. Diagnostic session setup and verification

### State machine

```text
NEW → ESTABLISHING → READY → CLOSED
                 ↘ FAILED → CLOSED
```

Reject: double enter; query before READY; query after FAILED/CLOSED; nested sessions; reuse.

After any `psycopg.Error`: fail-closed (`FAILED`); no further SQL in that session.

### Establish

One parameterized autocommit statement via `pg_catalog.set_config(..., false)` for:

- `default_transaction_read_only=on`
- `statement_timeout` / `lock_timeout` / `idle_in_transaction_session_timeout`
- `search_path=pg_catalog`

All names schema-qualified; no user interpolation into SQL text.

### Transaction

```python
conn.transaction(force_rollback=True)
```

Normal exit never commits. No manual `commit`/`rollback` inside the active Psycopg transaction context.

### Verify

One structured SELECT using `current_setting` / `pg_settings` (ms units) and `current_schemas(false)`. Do not compare formatted `SHOW` timeout strings.

Pass criteria: both read-only flags true; timeouts equal configured ms with unit `ms`; `search_path_raw=pg_catalog`; effective path exactly `['pg_catalog']`.

`application_name` classified as `pginspect_owned | custom | empty` — not a safety gate. Custom values are not placed in evidence.

### SQL surface

Package-private `_fetch_one` / `_fetch_all` with `LiteralString` queries only. No public `execute`, no `show(name)`, no arbitrary user SQL.

Guarantees = package-owned reviewed SQL + read-only transaction + fixed search_path + force rollback + no public query API. Read-only is **not** a general SQL sandbox.

### Failure mapping (session setup)

| Situation | Exit |
|---|---:|
| Required GUC rejected / mismatch / bad search_path | 2 (`session_safety_misconfigured`) |
| Broken connection / class `08` / statement timeout / `57014` | 3 |
| Verification SQL programming bug / invariant | 5 |
| KeyboardInterrupt | 130 |

### Evidence (verified)

Includes GUC booleans/ms, search_path list, application_name kind/value rules, `write_probe=not_run`, `verification_level=settings`, `read_only_scope=postgresql_transaction`, `read_only_is_sandbox=false`, plus limitations about no write probe and CI enforcement.

---

## 7. Capability discovery

Runs only when `session.state == READY`. One atomic package-owned SELECT (identity + privileges + known extensions). No partial results; no SAVEPOINT recovery in Foundation.

Uses `CURRENT_USER` / `SESSION_USER` (not `pg_catalog.current_user`). Version from `current_setting('server_version')` and `server_version_num` — never `version()`.

### Private vs public

`DiscoveredCapabilities` (private, non-serialized) → redaction/context_builder → public `ConnectionContext`.

### Version policy (`version_policy.py`)

```text
14–18              supported → ok / exit 0
19beta/rc          experimental → warning / exit 1
> max tested stable untested_newer → warning / exit 1
10–13              unsupported_older → critical / exit 2
<pre-10            unsupported_legacy → critical / exit 2
```

This is **pginspect release policy**, not live upstream fetch.

### Privileges

`can_use_pg_monitor` / `can_use_pg_read_all_stats` / `can_use_pg_read_all_settings` / `is_superuser` (NULL is invariant failure).

### Extensions allowlist

`hypopg`, `pg_stat_statements`, `pgstattuple`, `pg_buffercache` → every key present as `available|unavailable`. Absence is not a finding. HypoPG is not installed or exercised in Foundation CI.

### Target context

```text
--host → explicit_host_fingerprint + source=explicit_cli_host
else   → fingerprint null + source=libpq_resolved_unknown
```

### Finding order (full success)

1. `connection.established`  
2. `connection.session_safety_verified`  
3. exactly one version finding  

No findings for missing extensions, non-superuser, or standby.

---

## 8. Redaction and error normalization

### Identifier display (Foundation)

```yaml
database: literal
role: literal
session_user: literal   # always present; never omitted when equal to role
explicit_host: fingerprint only
resolved_libpq_host: unavailable
```

Host fingerprint:

```text
NFC + strip → sha256 → "sha256:" + first 16 hex chars
```

Documented as pseudonymous, not cryptographic anonymity. Exact `--host` string; no DNS, no lowercasing, no multi-host split.

### Module split

- `redaction.py` — primitives only  
- `error_catalog.py` — public messages / retryability  
- `context_builder.py` — public context assembly  

### ExecutionError

Typed `code` + `category` enums. Categories in Foundation: `connection | session | operational | internal`. No usage/configuration/interrupted in the result model.

No raw driver text in default or debug. Debug payload: exception type names, causal-chain type names, bounded frames (`module`, `function`, `line`) — no absolute paths, locals, or source lines.

### Domain exception hygiene

No stored raw exception, traceback, pgconn, args; `__cause__`/`__context__` must not reference driver exceptions after mapping.

### CLI usage messages

Catalogued; do not echo user values.

### Output escaping (renderers)

Escape C0/C1, DEL, ESC, CR/LF/TAB, U+2028/U+2029, bidi controls. Rich: `markup=False`, no highlight/emoji; user values never as markup.

### Canary leakage tests

End-to-end JSON/text must not leak passwords, DSN, host literals, passfile/cert paths, absolute source paths, or injectable ANSI.

---

## 9. Finding and CommandResult contracts

### Schema evolution

Exact versions (`1.0`); additive optional fields / new enums / new finding variants → **minor** bump with new immutable schema file; remove/rename/type/requiredness → **major**. Old files remain.

Paths and `$id`:

```text
docs/schemas/command-result/1.0.schema.json
  $id: urn:pginspect:schema:command-result:1.0

docs/schemas/finding/1.0.schema.json
  $id: urn:pginspect:schema:finding:1.0
```

`$schema`: `https://json-schema.org/draft/2020-12/schema`.  
Generated with serialization mode; canonical bytes compared in CI. URNs need not resolve on the network; schemas are never fetched via `$id` at runtime.

### Shared model config

All public models: `extra=forbid`, `frozen=True` (faux-immutability acknowledged), `allow_inf_nan=False`.

### Enums

```text
Severity: critical | warning | ok
# Confidence is not a separate enum in schema 1.0; see FindingBase.confidence

FindingStatus: triggered | passed
CommandOutcome: completed | failed

CommandExitCode:
  OK = 0
  WARNING = 1
  CRITICAL = 2
  OPERATIONAL_FAILURE = 3
  INTERNAL_FAILURE = 5

FindingId:
  connection.established
  connection.failed
  connection.server_version_supported
  connection.server_version_experimental
  connection.server_version_untested
  connection.server_version_unsupported
  connection.session_safety_verified
  connection.session_safety_misconfigured

VersionSupportStatus:
  supported | experimental | untested_newer | unsupported_older | unsupported_legacy

SessionSafetyMisconfigurationCategory:
  set_rejected | verification_mismatch

ConnectionTargetSource:
  explicit_cli_host | libpq_resolved_unknown

ExtensionAvailability:
  available | unavailable

ExecutionErrorCategory:
  connection | session | operational | internal

ExecutionErrorCode:
  authentication_failed
  network_unreachable
  connect_timeout
  tls_failed
  database_missing
  connection_failed
  operational_failure
  internal_failure

ClassificationSource:
  connection_timeout_type
  sqlstate
  needs_password
  audited_tls_signal
  fallback_other
  internal
```

Process-only exits `4` and `130` are **not** members of `CommandExitCode`.

`Severity.info`, `Confidence.medium`, and `Confidence.low` are absent from schema 1.0; they may appear only with a later minor bump when a real consumer needs them.

### Context models

```text
ConnectionTargetContext
  explicit_host_fingerprint: str | null   # "sha256:" + 16 hex, or null
  source: ConnectionTargetSource          # required

PrivilegeSnapshot
  is_superuser: bool                      # required, non-null
  can_use_pg_monitor: bool
  can_use_pg_read_all_stats: bool
  can_use_pg_read_all_settings: bool

KnownExtensionSnapshot
  hypopg: ExtensionAvailability
  pg_stat_statements: ExtensionAvailability
  pgstattuple: ExtensionAvailability
  pg_buffercache: ExtensionAvailability

ConnectionContext
  database: str                           # required literal
  role: str                               # required literal
  session_user: str                       # required literal (never omitted)
  server_version: str
  server_version_num: int
  server_major: int | null
  server_major_label: str
  version_support: VersionSupportStatus
  in_recovery: bool
  target: ConnectionTargetContext
  privileges: PrivilegeSnapshot
  extensions: KnownExtensionSnapshot
```

### Errors and debug

```text
DebugFrame
  module: str
  function: str
  line: int

DebugPayload
  exception_type: str
  causal_chain_types: tuple[str, ...]     # max 8
  frames: tuple[DebugFrame, ...]          # max 20

ExecutionError
  code: ExecutionErrorCode                # required
  category: ExecutionErrorCategory        # required; compatible with code
  message: str                            # catalogued, redacted
  retryable: bool                         # from central table
  sqlstate: str | null
  classification_source: ClassificationSource | null
  debug: DebugPayload | null              # only when include_debug=true
```

### Finding shared fields

```text
FindingBase
  schema_version: "1.0"
  id: FindingId
  severity: Severity                      # fixed per variant
  confidence: Literal["high"]             # only value in schema 1.0
  status: FindingStatus                   # fixed per variant
  title: str
  summary: str | null
  scope: ConnectionFindingScope           # required
  limitations: tuple[str, ...]
  remediation: Remediation | null

ConnectionFindingScope
  target: ConnectionTargetContext         # required

Remediation
  summary: str                            # required; no automatic/command fields
```

### Evidence models (required fields + schema literals)

```text
ConnectionEstablishedEvidence
  tls_used: bool | null

ConnectionFailedEvidence
  category: authentication_failed | network_unreachable | connect_timeout
            | tls_failed | database_missing | connection_failed
  classification_source: ClassificationSource
  sqlstate: str | null

# Per-variant ServerVersionEvidence — version_support is a Literal matching FindingId:
ServerVersionSupportedEvidence
  server_version: str
  server_version_num: int
  server_major: int | null
  server_major_label: str
  version_support: Literal["supported"]
  supported_majors: tuple[int, ...]
  max_tested_stable_major: int
  tested_prerelease_majors: tuple[int, ...]

ServerVersionExperimentalEvidence
  ...same fields...
  version_support: Literal["experimental"]

ServerVersionUntestedEvidence
  ...same fields...
  version_support: Literal["untested_newer"]

ServerVersionUnsupportedEvidence
  ...same fields...
  version_support: Literal["unsupported_older" | "unsupported_legacy"]

SessionSafetyVerifiedEvidence
  default_transaction_read_only: Literal[true]
  transaction_read_only: Literal[true]
  statement_timeout_ms: int
  lock_timeout_ms: int
  idle_in_transaction_session_timeout_ms: int
  search_path: tuple[Literal["pg_catalog"]]
  application_name_kind: pginspect_owned | custom | empty
  application_name_value: str | null
  write_probe: Literal["not_run"]
  verification_level: Literal["settings"]
  read_only_scope: Literal["postgresql_transaction"]
  read_only_is_sandbox: Literal[false]

  validators:
    application_name_kind=pginspect_owned → application_name_value required (non-null, non-empty)
    application_name_kind=custom|empty → application_name_value must be null

SessionSafetyExpectedState
  default_transaction_read_only: Literal[true]
  transaction_read_only: Literal[true]
  statement_timeout_ms: int
  lock_timeout_ms: int
  idle_in_transaction_session_timeout_ms: int
  search_path: tuple[Literal["pg_catalog"]]

SessionSafetyObservedState
  default_transaction_read_only: bool
  transaction_read_only: bool
  statement_timeout_ms: int
  lock_timeout_ms: int
  idle_in_transaction_session_timeout_ms: int
  search_path: tuple[str, ...]

SessionSafetyMisconfiguredEvidence
  category: SessionSafetyMisconfigurationCategory
  expected: SessionSafetyExpectedState
  observed: SessionSafetyObservedState | null
  sqlstate: str | null

  invariants:
    set_rejected → observed = null
    verification_mismatch → observed required AND at least one field differs from expected
    verification query failure does NOT create this finding
      → classified as operational exit 3 or internal exit 5 per §6
```

### Finding variants (severity/status/evidence fixed)

| ID | Severity | Status | Evidence type |
|---|---|---|---|
| `connection.established` | ok | passed | ConnectionEstablishedEvidence |
| `connection.failed` | critical | triggered | ConnectionFailedEvidence |
| `connection.server_version_supported` | ok | passed | ServerVersionSupportedEvidence |
| `connection.server_version_experimental` | warning | triggered | ServerVersionExperimentalEvidence |
| `connection.server_version_untested` | warning | triggered | ServerVersionUntestedEvidence |
| `connection.server_version_unsupported` | critical | triggered | ServerVersionUnsupportedEvidence |
| `connection.session_safety_verified` | ok | passed | SessionSafetyVerifiedEvidence |
| `connection.session_safety_misconfigured` | critical | triggered | SessionSafetyMisconfiguredEvidence |

`Finding` = discriminated union on `id`. No `skipped`/`unknown`; no `partial` outcome.

### Cross-field result validators (additional)

```text
connection.failed present
  → evidence.category aligns with error.code
  → error.category == connection
  → outcome == failed
  → exit_code == 3

version finding present
  → evidence.version_support Literal matches FindingId as above
  → ConnectionContext.version_support equals evidence.version_support
```

### CommandResult envelope

Every result includes:

```text
schema_version: "1.0"
command: "version" | "connect-test"
outcome: CommandOutcome
exit_code: CommandExitCode
started_at: datetime (UTC, serialized as ...Z)
duration_ms: int (>= 0)
app_version: str
context: ConnectionContext | null
findings: tuple[Finding, ...]
error: ExecutionError | null
```

Discriminated by `command`:

```text
VersionCommandResult
  command = "version"
  outcome = completed
  exit_code = 0
  context = null
  findings = ()
  error = null

ConnectTestCommandResult
  command = "connect-test"
  context / findings / error per stage builders and validators
```

```text
outcome completed → assessment finished; exit 0|1|2; error null
outcome failed    → assessment incomplete; exit 3|5; error required
```

### Stage builders (only construction path)

```text
build_connect_operational_failure
build_preconnect_internal_failure
build_session_safety_misconfigured
build_post_connection_failure
build_completed_connect_test
```

### Timing

UTC-aware `started_at` with `Z` suffix; `duration_ms` from `perf_counter_ns`.

---

## 10. CLI and renderer contracts

### `main()`

Manual Click context via `get_command(app).make_context` / `invoke`. Maps usage → 4; `KeyboardInterrupt` → 130; fatal wrapper → 5 catalogued stderr; returns command int otherwise.

Typer: no completion, no suggestions, no pretty exceptions, `rich_markup_mode=None`, empty argv is usage error 4 (not auto-help). `-h` free for `--host` on `connect-test`. Root help uses `--help` only (not `-h`).

### Commands

```text
pginspect version [--format text|json]
pginspect connect-test [options]
```

### `connect-test` options

| Option | Maps to | Notes |
|---|---|---|
| `--service NAME` | `ConnectionConfig.service` | overrides `PGSERVICE` |
| `-h` / `--host HOST` | `ConnectionConfig.host` | no default; fingerprint source |
| `-p` / `--port PORT` | `ConnectionConfig.port` | int; invalid → exit 4 |
| `-d` / `--dbname NAME` | `ConnectionConfig.dbname` | |
| `-U` / `--user USER` | `ConnectionConfig.user` | |
| `--sslmode MODE` | `ConnectionConfig.sslmode` | disable\|allow\|prefer\|require\|verify-ca\|verify-full |
| `--connect-timeout SECONDS` | `connect_timeout_s` | default 10; range 2–60; 0 forbidden |
| `--statement-timeout MS` | session | default 15000; 1–300000 |
| `--lock-timeout MS` | session | default 2000; 1–60000; must be < statement-timeout |
| `--idle-in-transaction-timeout MS` | session | default 15000; 1–300000 |
| `--format text\|json` | `OutputConfig.format` | command-local; default text |
| `--debug` | `ExecutionOptions.include_debug` | structured debug only |

### Absent options / behaviors

```text
--password
-W
--dsn
interactive password prompt
root-level --format
shell completion options
```

`--format` is command-local. `pginspect --format json version` → exit 4.

### Usage-error catalog (`CliErrorCode`)

| Code | Message (exact English) |
|---|---|
| `invalid_option_value` | `Invalid value for --<name>.` (name known; never echo value) |
| `missing_option_value` | `Missing value for --<name>.` |
| `unknown_option` | `Unknown option.` |
| `unknown_command` | `Unknown command.` |
| `unexpected_argument` | `Unexpected argument.` |
| `command_required` | `A command is required.` |
| `configuration_invalid` | catalogued config message, e.g. `lock_timeout must be less than statement_timeout.` |

Unknown/unclassified usage cases → `Invalid command line.`  
Messages never include raw argv tokens, option values, or Pydantic repr.

### Streams

| Mode | stdout | stderr |
|---|---|---|
| text, no debug | report | empty |
| text + debug | report | debug section |
| JSON (any debug) | one JSON object + final newline | empty |
| usage/config | empty | one catalogued line |
| fatal pre-write | empty | `pginspect failed due to an internal error.` |

Renderers return strings; CLI writes via `click.echo`. No `Exit: N` in text. JSON: `indent=2`, `sort_keys=True`, `allow_nan=False`, single trailing newline.

### Text renderer contract

**`version`:** exactly `pginspect <version>\n`

**`connect-test`:** line-oriented; fixed order; no panels; no adaptive tables; no terminal-width-dependent layout.

Required section order (labels English):

```text
Connection: ...
Database: ...
Role: ...
Session user: ...          # "same as current role" when equal; else escaped literal
Server: <version> (<support status>)
In recovery: yes|no
Session safety: verified|MISCONFIGURED|...
Timeouts: statement=<ms>ms lock=<ms>ms idle_xact=<ms>ms
Write probe: not run
Extensions:
  hypopg: available|unavailable
  pg_stat_statements: ...
  pgstattuple: ...
  pg_buffercache: ...
```

Then finding/error detail lines as needed for non-healthy outcomes (misconfigured expected/observed, connection failed message). User values escaped; never Rich markup.

Failed connect (no context): omit Database/Role/… sections that require context; show Connection failed + catalogued error.

### Version helper

Single `get_app_version()` via `importlib.metadata` (+ controlled source checkout fallback). Used by `version`, `app_version`, and `fallback_application_name`.

### Encoding

Internal Unicode; JSON `ensure_ascii=False`; CI `PYTHONUTF8=1`; no global stream reconfiguration.

### Tests layers

Unit (render/classify/config) → wrapper `main([...])` → installed entrypoint subprocess.

---

## 11. Exit-code resolution

### Result-level (`exit_codes.py`)

- completed findings → `resolve_completed_exit_code` → 0/1/2 via severity contribution table (triggered only)  
- failed error → `resolve_failed_exit_code` → 3/5 exhaustive on category  

Failed outcomes **ignore** finding severities. Exactly one primary `ExecutionError`. Cleanup failures must not replace an active operational/KeyboardInterrupt; orphan cleanup failure → internal 5.

### Process-level (`cli.py`)

```text
KeyboardInterrupt → 130 (no result)
usage/configuration → 4 (no result)
fatal envelope/output → 5 (no result if unsafe to build)
else → CommandResult.exit_code
```

`connection.failed` only for expected Psycopg/libpq connect failures (exit 3). Internal pre-connect → findings empty, exit 5.

`57014` / query cancel → operational 3, not 130.

Invalid config never enters `run_connect_test` through normal construction (CLI → 4). Invalid object reaching the function → internal 5.

No `--fail-on` in Foundation.

---

## 12. Unit, integration, and CI safety tests

### Discovery

Default `pytest` → `tests/unit` only; `strict_markers`; no `matrix_pg` marker. Integration/safety invoked by explicit paths.

### Constraints lock

```text
requirements/ci.txt
```

Pins exact versions of pydantic, pytest, jsonschema, mypy, ruff, coverage, pytest-cov, psycopg, typer, rich (and related). Schema generation and committed-byte drift run only in this environment.

### Matrices

```text
unit-python: 3.11–3.14
integration/safety postgres: 14–18 on Python 3.11
latest-stack: Python 3.14 + PostgreSQL 18
coverage: unit+integration+safety on PG18/Py3.11; branch fail_under=90
```

### CI security / runner contract

```text
permissions: contents: read
actions pinned to full commit SHA
fixed Linux runner label
PostgreSQL service image pinned to digest
health check via pg_isready
assert server_version_num matches job major after startup
no pull_request_target for untrusted code
no repository write token
minimal explicit permissions only
```

### Golden schema examples (required)

```text
version completed
healthy connect-test
experimental version
untested-newer version
unsupported version
session safety misconfigured
connect operational failure
post-connect operational failure
pre-connect internal failure
post-connect internal failure
standalone finding: each of the eight Finding variants
```

Each golden: validates against committed JSON Schema; validates as Pydantic union; round-trips to canonical-equivalent JSON.

### Safety probes

Each adversarial statement in a **fresh** DiagnosticSession; expect `25006`; observer verifies. Probe SQL only under `tests/safety/` (not shipped in wheel). Subject role must have real grants (not `42501`).

### Deterministic network fixtures

Closed local port → refused; loopback stall server → connect timeout. No blackhole/public IPs.

### Libpq precedence

Temporary service/passfile fixtures; assert **actual** connected database, not only fingerprint.

### SIGINT

Real installed-entrypoint subprocess receives SIGINT → 130.

### Architecture boundary tests (required list)

```text
only connection.py and session.py import psycopg
cli.py contains no SQL and no psycopg imports
renderers import public models, but not connection/session/connectivity
models import no I/O, Typer, Rich, or psycopg
no src module calls sys.exit()
no production module exposes arbitrary public execute(query)
no production module reads PGPASSWORD or PGPASSFILE
no SQL constants exist in cli.py or renderers/
```

### Traceability

`docs/superpowers/specs/2026-07-22-foundation-test-traceability.md` maps every atomic §13 criterion ID to automated test or named human gate. Required jobs: no silent skip, no `continue-on-error`, no automatic flaky retries.

---

## 13. Acceptance criteria

### States

```text
FOUNDATION_COMPLETE = all atomic criteria A–G satisfied; repo remains private
PUBLICATION_APPROVED = FOUNDATION_COMPLETE + pre_publication_gate + human sign-off
```

Checklist preparation is Foundation; signing and visibility change are not.

Each criterion has one ID. Traceability maps `Criterion ID → verification → CI job / human gate`. No criterion may remain without automated or named human verification.

### A. Repository & security

| ID | Criterion | Type |
|---|---|---|
| A-01 | New repository created with independent `git init` history | human+machine |
| A-02 | Release-reachable history has exactly one root commit | machine |
| A-03 | No git replace refs | machine |
| A-04 | No imported branches/tags/bundles/grafts from legacy | human+machine |
| A-05 | Legacy Git directory/objects/refs were not copied | human |
| A-06 | Independent-history provenance attested by owner | human |
| A-07 | Legacy repository remains private | human |
| A-08 | Legacy archived on GitHub **or** named owner exception + tracked follow-up | human |
| A-09 | Legacy description states superseded / no new development | human |
| A-10 | Legacy credentials rotation confirmed (safe attestation only) | human |
| A-11 | Staged content reviewed before first push | human |
| A-12 | Gitleaks full-history scan passed (pinned, fetch-depth 0, no baselines) | machine |
| A-13 | TruffleHog full-history scan passed (same constraints) | machine |
| A-14 | Canary test strings are scanner-safe (no suppressions for test DSN) | machine |
| A-15 | `SECURITY.md` present | machine |
| A-16 | `LICENSE` (MIT) present | machine |
| A-17 | README has no hardcoded hosts/users/passwords | machine |
| A-18 | Repository visibility remains private at `FOUNDATION_COMPLETE` | human |
| A-19 | Publication checklist prepared (unsigned) | human |

### B. Package & toolchain

| ID | Criterion | Type |
|---|---|---|
| B-01 | `pyproject.toml` src-layout package `pginspect` | machine |
| B-02 | `requires-python >= 3.11` | machine |
| B-03 | Console script `pginspect = pginspect.cli:main` | machine |
| B-04 | Runtime stack: psycopg3, Typer, Rich, Pydantic v2 | machine |
| B-05 | `python -m build` produces sdist and wheel from clean checkout | machine |
| B-06 | Wheel installs into clean venv; `pip check` passes | machine |
| B-07 | Installed `pginspect version` works | machine |
| B-08 | Installed `pginspect connect-test --help` works | machine |
| B-09 | Wheel excludes tests, credentials, legacy files, local artifacts | machine |
| B-10 | Unit import smoke uses installed wheel on Python 3.11 and 3.14 | machine |
| B-11 | Ruff check green | machine |
| B-12 | Ruff format --check green | machine |
| B-13 | mypy strict green on package | machine |
| B-14 | Architecture boundary tests (§12 list) green | machine |
| B-15 | CI uses `requirements/ci.txt` pins for schema/lint jobs | machine |
| B-16 | CI permissions `contents: read`; actions SHA-pinned; PG digest-pinned | machine |
| B-17 | Fixed Linux runner; no `pull_request_target`; no write token | machine |

### C. CLI contract

| ID | Criterion | Type |
|---|---|---|
| C-01 | Only product commands are `version` and `connect-test` | machine |
| C-02 | `--password` / `-W` absent | machine |
| C-03 | `--dsn` absent | machine |
| C-04 | Interactive password prompt absent | machine |
| C-05 | No application defaults for host/port/user/dbname/password | machine |
| C-06 | `--service` and libpq env/passfile work without app PG\* copying | machine |
| C-07 | `--connect-timeout` always applied (default 10) | machine |
| C-08 | `fallback_application_name` is `pginspect/<version>` from single helper | machine |
| C-09 | Full option set per §10 table is implemented | machine |
| C-10 | `--format` is command-local; root `--format` → exit 4 | machine |
| C-11 | Usage/config errors → exit 4 with catalogued stderr; no echoed values | machine |
| C-12 | Empty argv → exit 4 | machine |
| C-13 | No shell completion options; `-h` is `--host` on connect-test | machine |
| C-14 | KeyboardInterrupt/SIGINT → exit 130; no CommandResult | machine |
| C-15 | Fatal envelope/output failure → exit 5; catalogued stderr; stdout empty if pre-write | machine |
| C-16 | No `sys.exit()` in `src/pginspect` | machine |
| C-17 | Command callbacks return `int`; only `main()` is process wrapper | machine |
| C-18 | Stream contracts per §10 table | machine |
| C-19 | Text output never includes `Exit: N` | machine |
| C-20 | `version` text is exactly `pginspect <version>\n` | machine |

### D. Session & connect-test

| ID | Criterion | Type |
|---|---|---|
| D-01 | One parameterized establish `set_config` SELECT | machine |
| D-02 | One structured verification SELECT (ms units, not SHOW strings) | machine |
| D-03 | One atomic capability discovery SELECT | machine |
| D-04 | No generic `show(name)` or public `execute(query)` | machine |
| D-05 | After any psycopg SQL error, session is FAILED and runs no further SQL | machine |
| D-06 | Capabilities run only when `state=READY` | machine |
| D-07 | `force_rollback=True`; normal exit never commits | machine |
| D-08 | Persistent DB objects/data never modified by production paths | machine |
| D-09 | `write_probe=not_run`; verification_level=settings | machine |
| D-10 | CLI states read-only configuration verified; does not claim role cannot write | machine |
| D-11 | Custom `application_name` preserved; not a safety gate; custom value not in evidence | machine |
| D-12 | Version policy via `version_policy.py` only | machine |
| D-13 | Missing known extensions → unavailable, no findings | machine |

### E. Models & output

| ID | Criterion | Type |
|---|---|---|
| E-01 | Finding is closed discriminated union of eight variants | machine |
| E-02 | Each variant has typed evidence fields per §9 | machine |
| E-03 | Severity/status fixed per variant table | machine |
| E-04 | CommandResult discriminated by command; full envelope fields present | machine |
| E-05 | Public models: `extra=forbid`, `allow_inf_nan=False` | machine |
| E-06 | Semantic validators reject impossible result combinations | machine |
| E-07 | Finding order deterministic per lifecycle stage | machine |
| E-08 | Schema `$id` URNs as specified; Draft 2020-12 | machine |
| E-09 | Schema drift: generated bytes == committed | machine |
| E-10 | All golden examples validate + Pydantic round-trip | machine |
| E-11 | JSON: sort_keys, indent=2, final newline, serialization-mode schema | machine |
| E-12 | Text renderer escapes controls/bidi; no markup for user values | machine |
| E-13 | Database/role/session_user always present literals in context | machine |
| E-14 | Host exposed only as fingerprint when `--host` supplied | machine |
| E-15 | Domain exceptions retain no raw driver cause/context | machine |
| E-16 | Debug payload has no raw driver text / absolute paths / locals | machine |
| E-17 | End-to-end canary leakage tests pass for JSON and text | machine |

### F. Tests & matrix

| ID | Criterion | Type |
|---|---|---|
| F-01 | Default pytest runs `tests/unit` only | machine |
| F-02 | Integration green on PostgreSQL 14–18 (Python 3.11) | machine |
| F-03 | Safety write probes green on PostgreSQL 14–18 | machine |
| F-04 | Unit package matrix green on Python 3.11–3.14 | machine |
| F-05 | Latest-stack smoke: Python 3.14 + PostgreSQL 18 | machine |
| F-06 | Each write probe uses fresh DiagnosticSession; SQLSTATE 25006 | machine |
| F-07 | Observer confirms probe table unchanged after each probe | machine |
| F-08 | Subject role has real write grants (not insufficient_privilege) | machine |
| F-09 | Connection refused fixture uses local closed port | machine |
| F-10 | Connect timeout fixture uses loopback stall server | machine |
| F-11 | Real SIGINT on installed entrypoint → 130 | machine |
| F-12 | Libpq precedence asserts actual selected database | machine |
| F-13 | Session establishment atomicity verified on real PostgreSQL | machine |
| F-14 | Branch coverage ≥ 90% on combined suites (PG18/Py3.11) | machine |
| F-15 | Traceability matrix covers every §13 ID | machine |
| F-16 | Required CI jobs forbid silent skip / continue-on-error / auto flaky retry | machine |

### G. Explicit non-presence

| ID | Criterion | Type |
|---|---|---|
| G-01 | No `doctor` / inventory / activity / vacuum / index / HypoPG / EXPLAIN commands | machine |
| G-02 | No GUI | machine |
| G-03 | No production write path for ANALYZE/VACUUM/CREATE INDEX/TRUNCATE/other write SQL | machine |
| G-04 | Adversarial write SQL exists only under `tests/safety/` and is not packaged | machine |
| G-05 | No `checks/` `actions/` `plans/` `plugins/` `profiles/` `sql/` or `doctor.py` | machine |
| G-06 | No plugin protocols, check base classes, or generic SQL loader | machine |
| G-07 | No deferred placeholders, feature flags, or TODO implementation stubs | machine |
| G-08 | No telemetry/analytics/crash reporting/update check/remote schema fetch/SaaS | machine |
| G-09 | No outbound network other than requested PostgreSQL connection | machine |
| G-10 | JSON Schema not loaded over the network via `$id` at runtime | machine |

### Definition of done

> `FOUNDATION_COMPLETE` means an independent private repository with verified clean history, an installable `pginspect` package, `version` and `connect-test`, a fail-closed read-only diagnostic session, strict JSON models, deterministic exit codes, and a PostgreSQL 14–18 safety matrix. Production code contains no doctor checks or write execution paths. Public release requires separate `PUBLICATION_APPROVED`.

---

## 14. Explicitly deferred scope

### Meaning of “absent”

Deferred items must not exist as commands, public APIs, feature flags, placeholder modules/dirs, unused enum/schema fields, finding IDs, future-only dependencies, future-only CI jobs, or TODO stubs. Documentation mentions only, clearly marked deferred/non-goal.

### Deferred product

User-facing inventory/activity/vacuum/index/query/replication/storage/security/snapshot/doctor commands; all EXPLAIN/EXPLAIN ANALYZE; HypoPG usage beyond presence detection; any production write execution abstraction (no reserved writable `DiagnosticSession` mode); apply/plan manifests; GUI/SaaS/daemon/HTML/SARIF; plugins; `pginspect.toml`; `--dsn`; interactive password prompt; `--fail-on`; compact JSON; hashed-identifier mode; root `--format`; shell completion; Russian CLI strings (machine contract remains English).

### Foundation exceptions (not deferred)

Fixed atomic capability snapshot and `pg_is_in_recovery()` boolean required by connect-test; wheel build/install smoke; full-history secret scans; private CI; publication checklist **preparation**.

### Deferred release actions

Visibility→public; `PUBLICATION_APPROVED` sign-off; GitHub/TestPyPI/PyPI release; signing; SBOM publication; announcements. Changing accepted coverage threshold or supported matrix as **policy** is deferred; maintenance pin updates that preserve gates are not.

### Legacy archive

Governance gate, not product code. Required for `FOUNDATION_COMPLETE` as archived **or** documented owner exception with follow-up. Remains private; no new development.

### Permanent provenance invariant

Legacy commits/objects/refs/tags are never imported; no merge/cherry-pick/bundle/graft/replace/copied `.git`; no later stage may override this. Ideas may be independently reimplemented after review; wholesale legacy file copy to “avoid history” is forbidden.

### Permanent product non-goals (unless explicit pivot)

No autonomous production auto-tuning; no AI-generated SQL execution; no backup/restore product; no pgAdmin replacement. A future **explicit, reviewed, plan-based apply** workflow may be designed separately; autonomous mutation remains forbidden.

### Network non-presence

No telemetry, analytics, crash reporting, update checks, remote schema fetch, SaaS API, or outbound network other than the requested PostgreSQL connection.

### Handoff rule

Foundation implementation may only implement §§1–13 and required tests/docs/security infrastructure. Tickets needing deferred behavior are rejected or moved to a post-Foundation design stage.

---

## Implementation plan prelude

After this consolidated file receives final approval (`Status: approved design`), the next artifact is a separate implementation plan phased approximately as:

```text
Phase 0 — Legacy containment
Phase 1 — Create clean repository
Phase 2 — Security and tooling baseline
Phase 3 — Package scaffold
Phase 4 — Safe connection layer
Phase 5 — Diagnostic session
Phase 6 — Capability discovery + version policy
Phase 7 — Finding/CommandResult + renderers
Phase 8 — CLI main + exit codes
Phase 9 — PostgreSQL 14–18 CI + safety probes
Phase 10 — FOUNDATION_COMPLETE checklist
```

Inventory, activity, doctor, and any write actions begin only after this.

---

## Document control

| Item | Value |
|---|---|
| Spec path | `docs/superpowers/specs/2026-07-22-foundation-design.md` |
| Traceability matrix | `docs/superpowers/specs/2026-07-22-foundation-test-traceability.md` (required Foundation deliverable; every §13 criterion ID mapped) |
| Source product plan | `POSTGRES_SCHEMA_INSPECTOR_PRODUCT_PLAN.md` (reference only; Foundation is a subset) |
| Language of CLI/machine contract | English |
| Section-by-section design review | completed |
| Consolidated file approval | approved |
| Spec self-review (post four local fixes) | SessionSafetyMisconfiguredEvidence typed; evidence Literals; KnownExtensionSnapshot; Severity/confidence trimmed; connect-test mutation wording |
