# pginspect Change Impact — Design Spec

**Date:** 2026-07-23  
**Status:** approved design  
**Depends on:** `docs/superpowers/specs/2026-07-22-change-impact-product-thesis.md` (approved)  
**Does not authorize:** implementation plan, product implementation, Foundation schema `1.0` mutation, `PUBLICATION_APPROVED`

---

## 0. Scope

Hero command:

```text
pginspect impact MIGRATION.sql [connection options] [--format text|json] [--debug]
```

Prototype: PostgreSQL **14–18**, three DDL families:

```text
ALTER COLUMN TYPE / SET DATA TYPE
ADD COLUMN (+ DEFAULT / nullability)
DROP COLUMN
```

Live read-only catalog only. Migration file is never executed.

`DROP INDEX` is **not selected** for this design: no normative grammar, no module, no rule table. Stretch may be designed later as a separate amendment after Demo-proof.

---

## 0.1 Unified analysis pipeline

Single normative order (resolves prior §1/§2 contradiction):

```text
LOCAL PHASE (no PostgreSQL)
  open once binary → fstat → regular file → max 4 MiB
  → strict UTF-8 decode → strip BOM
  → lexical split + tokenize
  → malformed validation under fixed assumption:
       standard_conforming_strings = on
  → local exact control recognizer (§1.5) for:
       control-only rejection + source ordinal bookkeeping
       (case-insensitive; does NOT use pg_get_keywords();
        does NOT classify arbitrary SQL)
  → reject empty / comment-only / only-`;` / only-control / over limits
  → on any malformed → exit 4, no session, no result

DB PHASE
  open connection
  → BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ
       (before any SELECT; establishes RR for the whole session)
  → set transaction-local timeouts (Foundation)
  → capture pre-hardening resolution context:
       search_path
       current_schema()
       current_schemas(false)
       current_schemas(true)
  → establish hardened GUCs + search_path = pg_catalog
  → verify safety
  → preflight (version/GUC/encoding/isolation)
       on gate fail → incomplete exit 3, analysis_stage=preflight,
                      statements=(), no risk rules
  → major-aware keyword map via pg_get_keywords()
  → major-aware grammar classification / AST-lite for all
       non-control statements (uses keyword map)
  → resolve names using captured path (§2.4) — never pg_*_is_visible after harden
  → CatalogSnapshot + MetricObservation
  → sequence analyzer
  → risk rules
  → build ImpactCommandResult
  → ROLLBACK (force_rollback)
```

`catalog_snapshot_at` is the wall-clock timestamp of the **first SELECT** in the impact transaction. In `REPEATABLE READ` that first query fixes the MVCC snapshot used by subsequent catalog reads.

---

## 1. Parser boundary (local + grammar)

### 1.1 Input loader — `impact/input.py`

```text
open once (binary)
→ fstat / regular-file check
→ max size 4 MiB
→ strict UTF-8 decode
→ strip BOM
→ lexical split/tokenize/malformed validation
```

| Condition | Result |
|---|---|
| `-` (stdin) | exit 4, no result |
| directory / device / pipe | exit 4 |
| unreadable | exit 4 |
| empty / comment-only / only `;` | exit 4 |
| only control statements | exit 4: `No analyzable DDL statements.` |
| unclosed string / identifier / dollar / comment | exit 4 |
| over resource limits (§1.8) | exit 4 |
| file changed after open | ignore; analyze already-read bytes |

CLI never opens the migration path. `run_impact()` completes LOCAL PHASE before any PostgreSQL session.

Public metadata: `path_basename` only (never full path in errors/debug/result).

**Format:** SQL script, not psql. Reject as exit 4:

```text
\i \set \copy and other backslash meta-commands
COPY ... FROM STDIN with inline data / \.
```

Local lexical validation assumes `standard_conforming_strings=on`. Live confirmation is a DB preflight gate; mismatch → incomplete exit 3 (not exit 4).

### 1.2 Lexical splitter (FSM)

States:

```text
normal
single-quoted string
E'...' escape string
double-quoted identifier
dollar-quoted string
line comment
nested block comment
```

Terminator: `;` or EOF. `;` inside strings / quoted identifiers / dollar quotes does not terminate.

Dollar quotes: matching `$$` / `$tag$` (case-sensitive); `$1` is not a dollar quote. Body skipped whole. Statement containing dollar-quoted body → `unsupported_parser` after DB classification (lexically valid, not MVP-supported).

### 1.3 Tokenization

```text
keyword_candidate | unquoted_identifier | quoted_identifier
string/numeric/bit/hex literal | punctuation | source_span
```

Lexer always emits ordinary word tokens; reserved vs unreserved distinction uses live `pg_get_keywords()` during DB-phase grammar classification.

Matchers are token-aware AST-lite. Regex only inside the lexer.

### 1.4 Classification classes

| Class | When | Card? |
|---|---|---|
| `supported` | AST-lite for a supported family | yes |
| `control` | exact control grammar (§1.5) | **no** |
| `unsupported` → `unsupported_parser` | valid SQL not matched / multi-action / dollar body / … | yes |
| `malformed` | UTF-8 / unclosed / illegal file format | **no result**, exit 4 |

Empty separators (`;;`, whitespace/comments) ignored; **no** `statement_index`.

### 1.5 Control grammar (exact)

Recognized forms (case-insensitive; no extra clauses):

```text
BEGIN | BEGIN WORK | BEGIN TRANSACTION
START TRANSACTION
COMMIT | COMMIT WORK | COMMIT TRANSACTION
END | END WORK | END TRANSACTION
```

**Two-phase use:**

```text
LOCAL PHASE:
  fixed exact recognizer for the forms above
  used only for:
    - control-only file rejection (exit 4)
    - assigning source ordinals / skipping card creation
  does NOT call pg_get_keywords()
  does NOT classify arbitrary SQL as supported/unsupported

DB PHASE:
  major-aware classification validates all non-control statements
```

Still unsupported (DB-phase `unsupported_parser` if not caught as other classes):

```text
ROLLBACK, SAVEPOINT, RELEASE SAVEPOINT, SET, RESET, LOCK TABLE,
COMMIT AND CHAIN, transaction mode clauses
```

### 1.6 Sequence analyzer (not parser)

Parser does not track virtual schema. After resolution, `sequence.py` marks dependents:

```text
requires_virtual_schema_state → analysis_status = unsupported_sequence
```

Normative matrix (dependent statement gets `unsupported_sequence`; earlier independently analyzable cards are kept):

| Prior statement | Later statement |
|---|---|
| `ADD COLUMN x …` | later `ALTER`/`DROP` of `x` on same table |
| `DROP COLUMN x …` | later reference to `x` on same table |
| `ALTER … TYPE` on `x` | later op whose resolution depends on the **new** type of `x` |

Outcome: incomplete, exit 3. Independent prior cards remain.

### 1.7 Preview, fingerprint, limits

`sanitized_preview`: comments removed; whitespace collapsed; literals → typed placeholders; max **240** Unicode code points; never raw SQL fallback.

`statement_fingerprint`: SHA-256 of canonical redacted token stream → `sha256:` + first 16 hex.

```yaml
max_file_size: 4 MiB
max_statements: 1000
max_tokens_per_statement: 10000
max_nested_block_comment_depth: 64
max_preview_codepoints: 240
```

`statement_index` 1-based source ordinal; `start_line`/`end_line` 1-based inclusive. Card indexes may skip due to control statements.

### 1.8 Deferred parser tech

`pglast` / libpg_query — candidate after accuracy-first gate.

---

## 1b. Supported grammar (syntax only)

Name resolution is §2.

### Identifier

```text
Identifier:
  raw_token_private
  value: str
  quoted: bool
  normalized_value   # unquoted → lowercase; quoted → exact, "" → "
  source_span
```

Do not hardcode 63; use server `max_identifier_length` (bytes) in §2. Over-long → `unsupported_resolution` (server truncates; do not invent `would_fail`).

### `ALTER TABLE` prefix

```text
ALTER TABLE [IF EXISTS] <table_name> <single_action>
```

Unsupported: `ONLY`, trailing `*`, top-level multi-action commas (depth 0 only).

### `type_name` grammar (required for catalog resolution)

Opaque `type_name_span` alone is insufficient. Supported AST-lite:

```text
TypeName:
  name: QualifiedName          # schema.optional + ident, or multiword built-in
  typmod: tuple[TypmodArg, ...] | null
  array_bounds: tuple[ArrayBound, ...]   # [] / [n], may be empty

TypmodArg: integer literal | identifier (limited; unknown → unsupported_parser)
ArrayBound: unbound | integer_literal
```

**Multiword built-ins (exact token sequences, case-insensitive unquoted):**

```text
double precision
character varying
bit varying
character
char
varchar
national character varying
national character
national char
time with time zone
time without time zone
timestamp with time zone
timestamp without time zone
interval   # optional typmod supported; fields syntax beyond typmod → unsupported_parser
```

Anything else that is not a simple qualified/unqualified type name (+ optional typmod + array suffix) → `unsupported_parser`.

### Family 1 — column type

```text
ALTER [COLUMN] <col> TYPE <TypeName> [COLLATE <qual>] [USING <expr>]
ALTER [COLUMN] <col> SET DATA TYPE <TypeName> [COLLATE <qual>] [USING <expr>]
```

AST-lite: `table`, `column`, `type_name: TypeName`, `collation`, `using_expression_span`.  
`USING` last, non-empty, depth-balanced. Extra top-level tokens → `unsupported_parser`.

### Family 2 — add column

```text
ADD [COLUMN] [IF NOT EXISTS] <col> <TypeName>
  [COLLATE <qual>]
  [DEFAULT <expr>] [NULL | NOT NULL]     # either order vs DEFAULT
```

AST-lite: `type_name: TypeName`, spans, `nullability: unspecified|null|not_null`, `if_not_exists`.  
**No** `default_is_literal_like` in parser.

At most one each of DEFAULT / nullability / COLLATE.  
Unsupported: `CONSTRAINT`, `CHECK`, `REFERENCES`, `UNIQUE`, `PRIMARY KEY`, `GENERATED`, `IDENTITY`.

### Family 3 — drop column

```text
DROP [COLUMN] [IF EXISTS] <col> [RESTRICT | CASCADE]
```

```text
drop_behavior_written: default | restrict | cascade
effective_behavior: restrict | cascade    # default → restrict
```

### Not in this design

`DROP INDEX` — deferred (§6). No `grammar_drop_index.py`.

---

## 2. Preflight, resolution, catalog

### 2.1 Impact session profile

Explicit profile in `session.py` (not a generic mode). `connect-test` unchanged.

Order per §0.1. After hardening, all package SQL is schema-qualified; `search_path=pg_catalog`.

### 2.2 Preflight reads

```text
server_version, server_version_num
current_database, current_user, session_user
captured: current_schema, current_schemas(false/true), search_path
standard_conforming_strings, max_identifier_length
server_encoding, client_encoding
transaction_isolation, transaction_read_only
pg_is_in_recovery()
pg_get_keywords() → word, catcode, barelabel
```

Early incomplete (`outcome=incomplete`, exit 3, `analysis_stage_reached=preflight`, empty statements, no rules) when:

```text
server_major ∉ {14,15,16,17,18}
standard_conforming_strings ≠ on
transaction_read_only ≠ on
transaction_isolation ≠ repeatable read
server_encoding ≠ UTF8 OR client_encoding ≠ UTF8
```

### 2.3 Resolution context (pre-hardening)

```text
ResolutionContext:
  database: str
  role: str
  session_user: str
  current_schema: str | null
  current_schemas_user: tuple[str, ...]      # current_schemas(false)
  current_schemas_with_implicit: tuple[str, ...]  # current_schemas(true)
  search_path_raw: str
  max_identifier_length_bytes: int
  server_major: int
  server_version_num: int
  keyword_categories: map[str, catcode]
```

### 2.4 Name resolution (no `pg_*_is_visible` after hardening)

After hardening, visibility helpers reflect `search_path=pg_catalog` and **must not** be used.

```text
resolver uses captured current_schemas(true) ordering
→ explicit catalog ranking by that path
→ first matching candidate wins (same semantics as ordinary lookup)
→ applies equally to relations, indexes, types, collations, functions
```

Rules:

```text
qualified name
  → exact schema + object lookup in that schema only

unqualified relation / index
  → candidate only if present in captured current_schema()
  → and that candidate is the first match under captured current_schemas(true)
  → else unsupported_resolution (NOT deterministic missing)

current_schema() IS NULL
  → unsupported_resolution for unqualified targets

unqualified type / collation / function
  → rank by captured current_schemas(true); first match
  → if none → see §2.5 outcomes
```

Deterministic missing (IF EXISTS / IF NOT EXISTS no-op paths) only for **fully qualified** relation names (and qualified column checks on an already-resolved table).

Identifier byte length > `max_identifier_length` → `unsupported_resolution` + truncation limitation.

### 2.5 Deterministic resolution outcomes

| Situation | analysis_status | execution_prediction | risk |
|---|---|---|---|
| qualified table missing + `IF EXISTS` | analyzed | no_op (`target_missing_if_exists`) | safe |
| qualified table missing without `IF EXISTS` | analyzed | would_fail | critical |
| existing table + missing DROP/TYPE column without `IF EXISTS` | analyzed | would_fail | critical |
| existing table + missing DROP/TYPE column with `IF EXISTS` | analyzed | no_op (`column_missing_if_exists`) | warning (AE lock) |
| existing table + existing ADD column without `IF NOT EXISTS` | analyzed | would_fail | critical |
| existing table + existing ADD column with `IF NOT EXISTS` | analyzed | no_op (`column_already_exists_if_not_exists`) | warning (AE lock) |
| qualified type or collation missing | analyzed | would_fail | critical |
| unqualified target unresolved under MVP policy | unsupported_resolution | not_evaluated | not_applicable → incomplete |

### 2.6 Privilege semantics (policy B)

```text
execution_prediction models DDL semantics only.
Authorization / ownership / GRANT / type USAGE failures are explicitly not modeled.
```

Cards may still say `applies` when catalog DDL semantics would succeed for a privileged role. Mandatory limitation on every analyzed card:

```text
Authorization failures are not modeled; analysis assumes sufficient privileges.
```

### 2.7 Relation eligibility (Demo-proof)

Risk scoring only if:

```text
relkind = 'r'
relispartition = false
no pg_inherits parent
no pg_inherits descendants
```

Otherwise: resolve into snapshot, `unsupported_scope`, incomplete, exit 3.

### 2.8 Catalog structures

```text
CatalogSnapshot:
  catalog_snapshot_at: datetime   # time of first SELECT (§0.1)
  server_version_num: int
  relations: map[oid, RelationSnapshot]
  types: map[oid, TypeSnapshot]
  functions: map[oid, FunctionSnapshot]
  coercions: tuple[CoercionEvidence, ...]
  dependency_edges: tuple[DependencyEdge, ...]
  dependency_graph_complete: bool
  truncated_at_limit: bool

MetricObservation:
  metrics_observed_at: datetime | null
  metrics_consistency: "best_effort"
  relation_metrics: map[oid, RelationMetrics]
```

```text
RelationSnapshot:
  oid, nspname, relname, relkind
  relpersistence
  relispartition: bool
  inherits_parents: tuple[oid, ...]
  inherits_children: tuple[oid, ...]
  columns: tuple[ColumnSnapshot, ...]
  indexes: tuple[IndexSnapshot, ...]
  constraints: tuple[ConstraintSnapshot, ...]

ColumnSnapshot:
  attnum, attname
  type_oid, typmod
  attndims: int
  attnotnull: bool
  attisdropped: bool
  identity: "" | "a" | "d"           # attidentity
  generated: "" | "s" | "v"          # attgenerated; "v" = virtual (PG18+)
  default_bin: str | null            # pg_attrdef.adbin as pg_node_tree text
  collation_oid: oid | null

TypeSnapshot:
  oid, nspname, typname
  typtype, typcategory
  typbasetype: oid | 0
  typelem: oid | 0                   # element type for arrays; else 0
  typarray: oid | 0                  # array type that contains this type; else 0
  typndims: int
  typtypmod: int
  typlen, typbyval, typalign
  typcollation: oid | 0
  typdefaultbin: str | null          # domain default nodeToString form
  typdefault: str | null             # domain default display form
  domain_not_null: bool
  domain_constraints: tuple[DomainConstraintSnapshot, ...]

DomainConstraintSnapshot:
  oid, conname, contype, conbin_present: bool

IndexSnapshot:
  oid, nspname, relname
  indrelid, indisunique, indisprimary, indisexclusion
  indkey_attnums: tuple[int, ...]
  indisvalid: bool
  predicate_present: bool          # opaque; not parsed
  is_constraint_backed: bool

ConstraintSnapshot:
  oid, conname, contype
  conrelid, confrelid
  conkey_attnums: tuple[int, ...]
  confkey_attnums: tuple[int, ...]
  confupdtype, confdeltype

FunctionSnapshot:
  oid, nspname, proname
  proargtypes: tuple[oid, ...]
  prorettype: oid
  provolatile: "i" | "s" | "v"
  prokind: str

CoercionEvidence:
  source_oid: oid
  target_oid: oid
  context: implicit | assignment | explicit
  method:
    catalog_function
    | binary
    | catalog_inout
    | automatic_io
    | domain
    | array
    | checked_rule
  origin:
    pg_cast
    | server_generic_rule
    | checked_in_rule
  evidence_id: str

DependencyEdge:
  classid, objid, objsubid
  refclassid, refobjid, refobjsubid
  deptype: str
  class_kind, ref_class_kind       # mapped object kinds
  bucket: internal | automatic | external_blocking | cascade
```

**Coercion policy:** `pg_cast` is necessary but not sufficient. Paths may also come from server generic rules (e.g. automatic I/O to string types, generic domain conversions) or from checked-in rule tables. A TYPE/ADD decision that needs assignment coercibility must cite a concrete `CoercionEvidence` (or a checked-in absence rule such as `type.no_assignment_cast.no_using`). Inventing a `pg_cast` row that does not exist is forbidden.

Dependency traversal: bounded BFS from column/table object address; max edges normative default **10_000**. If truncated → `dependency_graph_complete=false`, `truncated_at_limit=true`.

```text
RelationMetrics:
  pg_relation_size, pg_total_relation_size, indexes_size
  n_live_tup: int | null
  stats_freshness: unknown | estimated
```

### 2.9 Required vs optional evidence by family

| Family | Required (missing → `unsupported_evidence`) | Optional |
|---|---|---|
| TYPE | RelationSnapshot, ColumnSnapshot, source+target TypeSnapshot (incl. array/domain fields), CoercionEvidence or proven absence of assignment path, IndexSnapshot list for table | RelationMetrics, collation details beyond oid |
| ADD | RelationSnapshot, column-name conflict scan, target TypeSnapshot (incl. domain default fields when typtype=d), effective_default classification inputs; if effective_default is a function call → FunctionSnapshot for qualified allowlist forms; domain_constraints when typtype=d | RelationMetrics, indexes list (required when scoring index_rebuild) |
| DROP | RelationSnapshot, ColumnSnapshot, DependencyEdge set with `dependency_graph_complete=true` for “no external blockers” claims | RelationMetrics |

Optional missing → analyze with reduced `impact_scale` / limitations, not automatic incomplete — except when a physical field cannot be decided without it (then `unsupported_evidence`).

### 2.10 DB-access boundary

`impact/*` must not import psycopg, hold raw connection/cursor, or expose public `execute()`.  
`catalog.py` uses `DiagnosticSession` + package-owned `LiteralString` queries only.  
**Invariant:** neither raw migration text, nor preview, nor token span is ever sent as SQL.  
Catalog lookups use parameterized OID/name values only.  
Architecture/safety tests record package query IDs and prove migration fragments never reach the execution surface.

---

## 3. Risk rules (normative)

### 3.1 Axes

```text
analysis_status:
  analyzed
  unsupported_parser
  unsupported_resolution
  unsupported_scope
  unsupported_evidence
  unsupported_sequence

execution_prediction:
  applies
  no_op
  would_fail
  may_fail
  not_evaluated
```

### 3.2 Physical fields & invariants

```text
table_rewrite | table_scan | index_rebuild:
  yes | no | possible | unknown | not_applicable

INVARIANTS:
  table_rewrite = yes → table_scan = yes
  ALTER COLUMN TYPE + table_rewrite=yes + affected_indexes_exist
      → index_rebuild = yes
  ADD COLUMN + volatile DEFAULT + indexes_exist
      → index_rebuild = yes
  DROP COLUMN → index_rebuild = no
```

### 3.3 Severity (deterministic; no alternatives)

```text
would_fail → critical
confirmed table_rewrite=yes → critical
possible table_rewrite → critical
confirmed index_rebuild=yes → critical
possible index_rebuild → critical
confirmed or possible table_scan under AccessExclusiveLock → critical
may_fail → critical
CASCADE with external/cascade dependents → critical
AccessExclusiveLock with rewrite=no, scan=no, index_rebuild=no → warning
deterministic target_missing_if_exists → safe
required evidence unavailable → unsupported_evidence, risk=not_applicable, exit 3
```

### 3.4 Confidence

```text
ImpactConfidence:
  lock: high | medium | low | not_applicable
  rewrite: high | medium | low | not_applicable
  execution: high | medium | low | not_applicable
  dependencies: high | medium | low | not_applicable
  impact_scale: high | medium | low | unknown | not_applicable
```

Size / `n_live_tup` amplify explanation and `impact_scale` only; never flip semantic rewrite/lock verdict.

### 3.5 `no_op` + lock

```text
NoOpReason:
  target_missing_if_exists
  column_missing_if_exists
  column_already_exists_if_not_exists
```

| Reason | lock | risk |
|---|---|---|
| `target_missing_if_exists` | not_applicable | safe |
| `column_already_exists_if_not_exists` | AccessExclusiveLock | warning |
| `column_missing_if_exists` | AccessExclusiveLock | warning |

### 3.6 TYPE rule table

Decision key:

```text
server_major
source_base_type, source_typmod, source_collation_oid, source_domain_constraints?
target_base_type, target_typmod, target_collation_oid, target_domain_constraints?
using_present, using_identity_proven
affected_indexes_exist: bool
```

| Rule key | analysis | execution | rewrite | scan | index_rebuild | risk |
|---|---|---|---|---|---|---|
| `type.no_assignment_cast.no_using` | analyzed | would_fail | not_applicable | not_applicable | not_applicable | critical |
| `type.assignment_cast_unknown.no_using` + indexes | analyzed | may_fail | possible | possible | possible | critical |
| `type.assignment_cast_unknown.no_using` + no indexes | analyzed | may_fail | possible | possible | no | critical |
| `type.opaque_using` + indexes | analyzed | may_fail | possible | possible | possible | critical |
| `type.opaque_using` + no indexes | analyzed | may_fail | possible | possible | no | critical |
| `type.proven_rewrite` + indexes | analyzed | applies | yes | yes | yes | critical |
| `type.proven_rewrite` + no indexes | analyzed | applies | yes | yes | no | critical |
| `type.same_declared_type.no_using` | analyzed | applies | no | no | no | warning |
| T2 binary text→varchar — see per-major subtable | analyzed | applies | no | no | (subtable) | (subtable) |

**T2 normative pair:** `text → varchar` (no typmod change beyond unconstrained varchar), no `USING`, same collation, no domains.

| Major | indexes on column? | index_rebuild | risk |
|---|---|---|---|
| 14 | yes | yes | critical |
| 14 | no | no | warning |
| 15–18 | yes | no | warning |
| 15–18 | no | no | warning |

Evidence ids: `rule:type.binary.text_to_varchar…` plus `CoercionEvidence` with `method=binary` / `origin` as recorded. Unknown type pairs (not in checked-in table) → `type.assignment_cast_unknown.no_using` (not silent binary-coercible).

Lock when target table exists: always `AccessExclusiveLock`.

### 3.7 ADD COLUMN / DEFAULT axes

PostgreSQL applies a domain default when no column-level `DEFAULT` is written. Normative effective default:

```text
effective_default:
  explicit column DEFAULT expression, if present
  else domain DEFAULT (TypeSnapshot.typdefaultbin / typdefault), if typtype=d and present
  else NULL
```

All three axes classify **effective_default**, not merely the written column DEFAULT span:

```text
default_volatility: proven_nonvolatile | proven_volatile | unknown
default_coercion: proven_valid | proven_invalid | unknown
default_nullability: proven_nonnull | proven_null | unknown
```

High-confidence function allowlist only for:

```text
grammar-defined values: CURRENT_TIMESTAMP, CURRENT_DATE, CURRENT_TIME, LOCALTIMESTAMP, LOCALTIME, NULL, TRUE, FALSE
explicitly qualified built-ins with resolved FunctionSnapshot:
  pg_catalog.now()
  pg_catalog.clock_timestamp()
```

Unqualified calls → `default_volatility=unknown`.

Domain default that is present but not classifiable under MVP allowlist / coercion rules:

```text
add.effective_default_unknown
  → execution=may_fail
  → rewrite=possible, scan=possible
  → index_rebuild=possible if indexes else no
  → risk=critical
```

Do **not** map “no written column DEFAULT” to `add.*.no_default` when a domain default exists.

| Rule key | execution | rewrite | scan | index_rebuild | risk |
|---|---|---|---|---|---|
| `add.coercion_invalid` | would_fail | not_applicable | not_applicable | not_applicable | critical |
| `add.nullable.no_default` (effective_default=NULL) | applies | no | no | no | warning |
| `add.nullable.const_or_nonvolatile_valid` | applies | no | no | no | warning |
| `add.not_null.nonvolatile_valid.proven_nonnull` | applies | no | no | no | warning |
| `add.not_null.nullability_null_or_unknown` | may_fail | no | possible | no | critical |
| `add.not_null.no_default` (effective_default=NULL) | may_fail | no | possible | no | critical |
| `add.volatile_valid` + indexes (A3) | applies | yes | yes | yes | critical |
| `add.volatile_valid` + no indexes | applies | yes | yes | no | critical |
| `add.effective_default_unknown` + indexes | may_fail | possible | possible | possible | critical |
| `add.effective_default_unknown` + no indexes | may_fail | possible | possible | no | critical |
| `add.any_required_unknown` + indexes | may_fail | possible | possible | possible | critical |
| `add.any_required_unknown` + no indexes | may_fail | possible | possible | no | critical |
| `add.domain_with_constraints` + indexes | applies | yes | yes | yes | critical |
| `add.domain_with_constraints` + no indexes | applies | yes | yes | no | critical |

**Domain constraints rule:** for every major in **14–18**, `ADD COLUMN` of a domain type that has constraints → `add.domain_with_constraints` (rewrite/scan/index_rebuild as above), in addition to effective_default analysis. Version overlays may refine later if a major is proven different; until then this single result applies to the whole matrix.

**A3 normative shape:**

```sql
ALTER TABLE … ADD COLUMN … timestamptz DEFAULT pg_catalog.clock_timestamp();
```

→ `effective_default` = column DEFAULT; `default_volatility=proven_volatile`; rule `add.volatile_valid`.

Mandatory limitation for NOT NULL without proven empty table:

```text
Table emptiness is not proven from catalog evidence (n_live_tup is an estimate).
```

### 3.8 DROP COLUMN

```text
table_rewrite = no
table_scan = no
index_rebuild = no
lock = AccessExclusiveLock
```

| Case | analysis | execution | risk |
|---|---|---|---|
| only internal/automatic deps | analyzed | applies | warning |
| external blockers + RESTRICT/default | analyzed | would_fail | critical |
| CASCADE + external/cascade deps | analyzed | applies | critical |
| truncated / required deps missing | unsupported_evidence | not_evaluated | not_applicable → incomplete |

Limitation: catalog-proven deps only; textual/dynamic refs undetectable.

### 3.9 Exit aggregation

```text
any incomplete (any unsupported_* card or preflight incomplete) → 3
else any would_fail → 2
else any critical → 2
else any warning → 1
else → 0
```

Safer rollout: advisory `steps` / `assumptions` / `preconditions` only; **no** executable SQL field.

---

## 4. `ImpactCommandResult` / report contract

### 4.1 Schema identity

```text
urn:pginspect:schema:impact-command-result:0.1
urn:pginspect:schema:impact-statement-card:0.1
```

Foundation Finding / CommandResult `1.0` untouched.

### 4.2 Enums

```text
Outcome: completed | incomplete | failed
Risk: critical | warning | safe | not_applicable
AnalysisStatus: analyzed | unsupported_parser | unsupported_resolution |
                unsupported_scope | unsupported_evidence | unsupported_sequence
ExecutionPrediction: applies | no_op | would_fail | may_fail | not_evaluated
LockMode: AccessExclusiveLock | ShareUpdateExclusiveLock | not_applicable | unknown
PhysicalTriState: yes | no | possible | unknown | not_applicable
NoOpReason: target_missing_if_exists | column_missing_if_exists |
            column_already_exists_if_not_exists
ImpactRole: target | internal | automatic | blocker | cascade | rebuilt | related
EvidenceKind: server_fact | catalog_object | dependency_edge |
              metric_observation | semantic_rule
ObjectKind: table | column | index | constraint | view | function | type |
            collation | other
PreflightStatus: passed | incomplete | failed
AnalysisStage: connect | preflight | parse | resolve | catalog | rules | complete
```

### 4.3 Nested models

```text
ImpactConfidence:
  lock, rewrite, execution, dependencies, impact_scale
  # enums per §3.4

SaferRollout:
  steps: tuple[str, ...]
  assumptions: tuple[str, ...]
  preconditions: tuple[str, ...]

AffectedObjectRef:
  object_kind: ObjectKind
  identity: str
  schema: str | null
  name: str
  parent_identity: str | null
  impact_role: ImpactRole
  detail: str | null

ImpactEvidence:
  evidence_id: str
  kind: EvidenceKind
  summary: str
  attributes: map[str, JSON scalar]   # no secrets, no raw SQL, no full paths

ImpactConnectionContext:
  server_version: str
  server_version_num: int
  server_major: int
  database: str
  role: str
  session_user: str
  current_schema: str | null
  search_path_raw: str
  standard_conforming_strings: str
  server_encoding: str
  client_encoding: str
  transaction_isolation: str
  transaction_read_only: str
  in_recovery: bool
  max_identifier_length: int

ImpactPreflightCheck:
  id: str
  status: passed | failed | skipped
  detail: str

ImpactPreflight:
  status: PreflightStatus
  analysis_stage_reached: AnalysisStage
  checks: tuple[ImpactPreflightCheck, ...]
  limitations: tuple[str, ...]

ImpactSnapshot:
  catalog_snapshot_at: datetime
  metrics_observed_at: datetime | null
  metrics_consistency: "best_effort"
  server_version_num: int

ImpactInputMeta:
  path_basename: str
  source_statement_count: int
  card_count: int
  control_statement_count: int

ImpactSummary:
  overall_risk: Risk
  critical_count: int
  warning_count: int
  safe_count: int
  not_applicable_count: int
  would_fail_count: int
  may_fail_count: int
  unsupported_count: int
  no_op_count: int
  analyzed_count: int
  incomplete: bool
```

### 4.4 `ImpactStatementCard`

```text
statement_index: int
start_line: int
end_line: int
statement_fingerprint: str
sanitized_preview: str

analysis_status: AnalysisStatus
execution_prediction: ExecutionPrediction
no_op_reason: NoOpReason | null

risk: Risk
confidence: ImpactConfidence

lock: LockMode
table_rewrite: PhysicalTriState
table_scan: PhysicalTriState
index_rebuild: PhysicalTriState

affected_objects: tuple[AffectedObjectRef, ...]
why: tuple[str, ...]
safer_rollout: SaferRollout | null
limitations: tuple[str, ...]
evidence_refs: tuple[str, ...]
```

### 4.5 Top-level `ImpactCommandResult`

```text
schema_version: "0.1"
command: "impact"
outcome: Outcome
exit_code: 0 | 1 | 2 | 3 | 5
started_at: datetime          # RFC 3339 UTC
duration_ms: int              # >= 0
app_version: str

input: ImpactInputMeta
connection_context: ImpactConnectionContext | null
preflight: ImpactPreflight
snapshot: ImpactSnapshot | null     # null if ended before catalog phase
summary: ImpactSummary
statements: tuple[ImpactStatementCard, ...]
evidence: tuple[ImpactEvidence, ...]
error: ExecutionError | null        # Foundation-style catalogued error
```

### 4.6 Validators & invariants

```text
completed:
  exit_code ∈ {0,1,2}
  error = null
  summary.incomplete = false
  no card with analysis_status starting with unsupported_
  snapshot may be non-null

incomplete:
  exit_code = 3
  summary.incomplete = true
  statements may be partial
  error may be null

failed:
  exit_code ∈ {3,5}
  error != null
  statements = ()
  summary.overall_risk = not_applicable
  summary.incomplete = true

exit 4 or 130:
  ImpactCommandResult MUST NOT be produced
```

```text
critical_count + warning_count + safe_count + not_applicable_count
  = len(statements)

overall_risk = max observed card risk
  (incomplete + critical still reports overall_risk=critical with exit 3)

source_statement_count = supported + unsupported + control
card_count = len(statements)
every evidence_ref ∈ evidence.evidence_id
every evidence entry is referenced at least once
no raw SQL / secrets / full paths in public fields
```

### 4.7 Deterministic ordering

```text
statements sorted by statement_index ascending
affected_objects sorted by (impact_role, object_kind, identity)
evidence sorted by evidence_id ascending
why / limitations preserve rule-defined order
JSON serialization ends with exactly one newline
```

### 4.8 Renderers

Text: summary block, then cards in order.  
JSON: exactly one object on stdout. Streams/`--debug` per §5.3.

---

## 5. CLI / layout / fixtures / tests

### 5.1 Process exits

```text
ImpactCommandResult produced → process exit = result.exit_code
usage / malformed local input → exit 4, no result
KeyboardInterrupt → exit 130, no result
catastrophic wrapper / serialization / output failure → exit 5, no result
```

### 5.2 Connection options (Foundation contract)

```text
--service
-h / --host
-p / --port
-d / --dbname
-U / --user
--sslmode
--connect-timeout
--statement-timeout
--lock-timeout
--idle-in-transaction-session-timeout
--format text|json
--debug
```

```text
no --dsn
no --password
no interactive password prompt
PG* delegated to libpq
Foundation precedence unchanged
```

### 5.3 Streams and `--debug`

```text
text:
  stdout = report
  stderr = debug diagnostics only when requested

json:
  stdout = exactly one ImpactCommandResult
  stderr = empty
  debug lives in typed error/debug fields when applicable
```

`--debug` never disables redaction; never emits a second JSON object; never prints raw SQL, full path, or driver message; may leave successful output unchanged.

### 5.4 Module layout

```text
src/pginspect/impact/
  __init__.py
  cli.py
  input.py
  run.py
  preflight.py
  parser/
    split.py
    tokens.py
    classify.py
    grammar_alter.py
  resolve.py
  catalog.py
  sequence.py
  rules/
    type_change.py
    add_column.py
    drop_column.py
    severity.py
  models/
    result.py
    card.py
    evidence.py
    enums.py
  renderers/
    text.py
    json.py
```

No `grammar_drop_index.py` in this design.

### 5.5 Demo-proof fixture matrix

Root: `tests/fixtures/impact/<fixture_id>/` with:

```text
setup.sql
migration.sql
expected/common.json
expected/pgNN.json     # only when majors differ
```

Each expected JSON declares: outcome, exit, card fields, `semantic_rule` evidence ids, limitations.  
Setup runs only on **fixture-admin** connection. Subject impact session never executes `migration.sql`.  
Schemas are fixture-local (`impact_t1`, …).

Every analyzed card includes limitation:

```text
Authorization failures are not modeled; analysis assumes sufficient privileges.
```

#### TYPE family

**T1 — proven rewrite (`integer → text`)**

```text
fixture_id: T1
majors: 14–18
setup.sql:
  CREATE SCHEMA impact_t1;
  CREATE TABLE impact_t1.t (
    id int PRIMARY KEY,
    payload integer NOT NULL
  );
  CREATE INDEX impact_t1_payload_idx ON impact_t1.t (payload);
migration.sql:
  ALTER TABLE impact_t1.t ALTER COLUMN payload TYPE text;
expected/common.json:
  outcome=completed, exit=2
  analysis_status=analyzed
  execution_prediction=applies
  table_rewrite=yes, table_scan=yes, index_rebuild=yes
  lock=AccessExclusiveLock, risk=critical
  evidence_ids:
    [rule:type.proven_rewrite,
     coercion:integer_to_text_assignment,
     index:impact_t1_payload_idx]
  CoercionEvidence for integer→text:
    context=assignment
    method=automatic_io
    origin=server_generic_rule
  limitations: [authorization_not_modeled]
```

**T2 — binary `text → varchar` (per-major index_rebuild)**

```text
fixture_id: T2
majors: 14–18
setup.sql:
  CREATE SCHEMA impact_t2;
  CREATE TABLE impact_t2.t (
    id int PRIMARY KEY,
    label text NOT NULL
  );
  CREATE INDEX impact_t2_label_idx ON impact_t2.t (label);
migration.sql:
  ALTER TABLE impact_t2.t ALTER COLUMN label TYPE varchar;
rule_key: type.binary.text_to_varchar.same_collation.no_domain.no_using
expected/pg14.json:
  outcome=completed, exit=2
  rewrite=no, scan=no, index_rebuild=yes, risk=critical
  evidence_ids: [rule:type.binary.text_to_varchar.same_collation.no_domain.no_using, …]
expected/pg15.json … expected/pg18.json:
  outcome=completed, exit=1
  rewrite=no, scan=no, index_rebuild=no, risk=warning
  evidence_ids: [rule:type.binary.text_to_varchar.same_collation.no_domain.no_using, …]
```

**T3 — no cast path**

```text
fixture_id: T3
majors: 14–18
setup.sql:
  CREATE SCHEMA impact_t3;
  CREATE TABLE impact_t3.t (
    id int PRIMARY KEY,
    payload text NOT NULL
  );
migration.sql:
  ALTER TABLE impact_t3.t ALTER COLUMN payload TYPE integer;
expected/common.json:
  outcome=completed, exit=2
  execution_prediction=would_fail
  physical=not_applicable
  risk=critical
  evidence_ids: [rule:type.no_assignment_cast.no_using]
```

#### ADD COLUMN family

**A1 — nullable, effective_default=NULL**

```text
fixture_id: A1
majors: 14–18
setup: CREATE SCHEMA impact_a1; CREATE TABLE impact_a1.t (id int PRIMARY KEY);
migration: ALTER TABLE impact_a1.t ADD COLUMN note text;
expected: completed, exit=1
  execution=applies, rewrite=no, scan=no, index_rebuild=no, risk=warning
  evidence_ids: [rule:add.nullable.no_default]
  # target is plain text (no domain default)
```

**A2 — constant DEFAULT**

```text
fixture_id: A2
majors: 14–18
setup: CREATE SCHEMA impact_a2; CREATE TABLE impact_a2.t (id int PRIMARY KEY);
migration: ALTER TABLE impact_a2.t ADD COLUMN flag boolean DEFAULT false;
expected: completed, exit=1
  execution=applies, rewrite=no, scan=no, index_rebuild=no, risk=warning
  evidence_ids: [rule:add.nullable.const_or_nonvolatile_valid]
```

**A3 — volatile qualified DEFAULT**

```text
fixture_id: A3
majors: 14–18
setup:
  CREATE SCHEMA impact_a3;
  CREATE TABLE impact_a3.t (id int PRIMARY KEY);
  CREATE INDEX impact_a3_id_idx ON impact_a3.t (id);
migration:
  ALTER TABLE impact_a3.t
    ADD COLUMN seen_at timestamptz DEFAULT pg_catalog.clock_timestamp();
expected: completed, exit=2
  execution=applies, rewrite=yes, scan=yes, index_rebuild=yes, risk=critical
  evidence_ids:
    [rule:add.volatile_valid,
     function:pg_catalog.clock_timestamp(),
     index:impact_a3_id_idx]
```

**A4 — NOT NULL, effective_default=NULL**

```text
fixture_id: A4
majors: 14–18
setup:
  CREATE SCHEMA impact_a4;
  CREATE TABLE impact_a4.t (id int PRIMARY KEY);
  -- rows may exist; n_live_tup must not change expectation
migration: ALTER TABLE impact_a4.t ADD COLUMN required_col text NOT NULL;
expected: completed, exit=2
  execution=may_fail, rewrite=no, scan=possible, index_rebuild=no, risk=critical
  evidence_ids: [rule:add.not_null.no_default]
  limitations:
    [table_emptiness_not_proven_from_catalog,
     authorization_not_modeled]
```

**A5 — same as A4 with empty-looking stats**

```text
fixture_id: A5
majors: 14–18
setup: same shape as A4; ANALYZE so n_live_tup may be 0
migration: identical to A4
expected: identical to A4 (n_live_tup is never proof of emptiness)
  evidence_ids: [rule:add.not_null.no_default]
```

#### DROP COLUMN family

**D1 — internal index only**

```text
fixture_id: D1
majors: 14–18
setup:
  CREATE SCHEMA impact_d1;
  CREATE TABLE impact_d1.t (
    id int PRIMARY KEY,
    obsolete text
  );
  CREATE INDEX impact_d1_obsolete_idx ON impact_d1.t (obsolete);
migration: ALTER TABLE impact_d1.t DROP COLUMN obsolete;
expected: completed, exit=1
  execution=applies, rewrite=no, scan=no, index_rebuild=no, risk=warning
  affected: column target + automatic index
  evidence_ids: [rule:drop.internal_only]
```

**D2 — view blocker, RESTRICT**

```text
fixture_id: D2
majors: 14–18
setup:
  CREATE SCHEMA impact_d2;
  CREATE TABLE impact_d2.t (
    id int PRIMARY KEY,
    secret text
  );
  CREATE VIEW impact_d2.v AS SELECT id, secret FROM impact_d2.t;
migration: ALTER TABLE impact_d2.t DROP COLUMN secret RESTRICT;
expected: completed, exit=2
  execution=would_fail, risk=critical
  evidence_ids: [rule:drop.external_blocker_restrict, dep:view:impact_d2.v]
```

**D3 — same deps, CASCADE**

```text
fixture_id: D3
majors: 14–18
setup:
  CREATE SCHEMA impact_d3;
  CREATE TABLE impact_d3.t (
    id int PRIMARY KEY,
    secret text
  );
  CREATE VIEW impact_d3.v AS SELECT id, secret FROM impact_d3.t;
migration: ALTER TABLE impact_d3.t DROP COLUMN secret CASCADE;
expected: completed, exit=2
  execution=applies, risk=critical
  cascade dependents listed (view impact_d3.v)
  evidence_ids: [rule:drop.cascade_external, dep:view:impact_d3.v]
```

#### Cross-cutting

**X1 — supported + unsupported**

```text
fixture_id: X1
majors: 14–18
setup: CREATE SCHEMA impact_x1; CREATE TABLE impact_x1.t (id int PRIMARY KEY);
migration:
  ALTER TABLE impact_x1.t ADD COLUMN note text;
  CREATE TABLE impact_x1.other (id int);
expected: incomplete, exit=3
  cards: analyzed warning (ADD) + unsupported_parser (CREATE TABLE)
```

**X2 — malformed unclosed string**

```text
fixture_id: X2
majors: any (local only)
migration.sql:
  ALTER TABLE impact_x2.t
    ADD COLUMN x text DEFAULT 'unclosed;
expected:
  no ImpactCommandResult
  process exit=4
  no DB connection
  # quote opens a string that never closes before EOF;
  # NOT a comment-embedded apostrophe
```

**X3 — comment-only**

```text
fixture_id: X3
majors: any (local only)
migration: -- only comments
expected: no result, exit=4, no DB connection
```

Human Demo-proof uses recorded reports from **T1**, **A4**, and **D2** (same commit + PostgreSQL major).

### 5.6 Automated test layers

```text
unit:
  lexer, tokenizer, matchers, sequence analyzer, rule tables
  (no PostgreSQL)

contract/schema:
  completed exits 0 / 1 / 2
  incomplete exit 3
  failed exits 3 / 5
  schema drift
  Pydantic + JSON Schema round-trip
  evidence_ref integrity
  deterministic ordering

CLI:
  installed-entrypoint text/json
  stream contract
  malformed file → 4 before connection
  SIGINT → 130
  path/redaction canaries

integration:
  all Demo-proof fixtures T1–T3, A1–A5, D1–D3, X1 on PG 14–18
  X2/X3 local-only

resolution/preflight:
  qualified success
  unqualified visible candidate under captured path
  shadowed/undetermined → incomplete
  unsupported PG major
  non-UTF8 server/client encoding
  standard_conforming_strings=off
  partition/inheritance unsupported_scope

safety:
  migration SQL never sent to server
  catalog queries allowlisted/package-owned
  schema objects and definitions unchanged
  force rollback on success and failure
```

### 5.7 Human Demo-proof protocol

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

---

## 6. Explicit non-goals / deferred

```text
doctor hero path
HypoPG / workload / EXPLAIN
apply / executable migrations
offline dump mode
full search_path walk beyond captured current_schemas(true) ranking
partition / inheritance risk scoring in Demo-proof
authorization / privilege modeling (policy B)
DROP INDEX family (stretch; design later as separate amendment)
Foundation Finding / CommandResult 1.0 mutation
empty stubs / feature flags for deferred families
```

---

## 7. Next steps

1. Design status is **approved design**.
2. Implementation plan is **not** created by this document and remains unauthorized until explicitly requested.
3. No product `impact` implementation until an implementation plan is written and accepted.
4. Parallel Foundation close track remains independent.

---

## Document control

| Item | Value |
|---|---|
| Path | `docs/superpowers/specs/2026-07-23-change-impact-design.md` |
| Thesis | `2026-07-22-change-impact-product-thesis.md` |
| Status | approved design |
| Privilege policy | B — authorization not modeled |
| DROP INDEX | deferred / non-goal for this design |
| Final corrections | T2 major boundary 14 vs 15–18; X2 true unclosed string; Column/TypeSnapshot PG fields; effective_default; CoercionEvidence; local control recognizer |
