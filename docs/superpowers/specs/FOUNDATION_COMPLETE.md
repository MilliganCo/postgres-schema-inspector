# Foundation status: **code-complete** (not yet `FOUNDATION_COMPLETE`)

Local engineering for Spec §§1–14 is implemented (package, CLI, models, unit tests,
workflow definitions). That is **Foundation code-complete**.

True **`FOUNDATION_COMPLETE`** is **blocked** while **A-10** remains open. This
document records owner decisions from the Foundation close attestation packet.
It does **not** authorize visibility changes or `PUBLICATION_APPROVED`.

**Date (UTC):** 2026-07-29  
**Repo:** `MilliganCo/postgres-schema-inspector`  
**Visibility:** **private** (A-18) — do not flip to public from this checklist.  
**Verified engineering HEAD (A-11 review through):** `483b0ce39e3046785f5c2fd5eadaa07c00e82774`  
**Checklist documentation commit:** this file on private `main` (SHA = current `origin/main` after push)

## Repository state notes

| Fact | Status |
| --- | --- |
| GitHub remote | **Created** — `https://github.com/MilliganCo/postgres-schema-inspector.git` |
| Visibility | **private** (A-18 approved; keep private) |
| Green GHA on reviewed HEAD | **Yes** through `483b0ce39e3046785f5c2fd5eadaa07c00e82774` — unit/lint/schema/integration(14–18)/safety(14–18)/coverage/latest-stack/secret-scan |
| `PUBLICATION_APPROVED` | **false** (A-19 approved as prepared-but-unsigned) |
| Legacy archive | **Not archived** — A-08 timed exception |
| Legacy description | **Updated** (A-09) |
| Credential rotation attestation | **Open** (A-10) — blocks `FOUNDATION_COMPLETE` |
| Pre-first-push review | **Exception recorded** (A-11) — missed procedural gate |

## Automated (CI / tests)

Covered by workflows and/or pytest as mapped in
`2026-07-22-foundation-test-traceability.md`:

- [x] Package, CLI `version` / `connect-test`, models, schemas, renderers
- [x] Unit matrix Python 3.11–3.14 (`unit.yml`)
- [x] Architecture boundaries, ruff, mypy (`lint-type.yml`)
- [x] Schema drift + goldens (`schema.yml`)
- [x] Integration matrix PG 14–18 / Py 3.11 (`integration.yml`)
- [x] Safety write-probes PG 14–18 (`safety.yml`)
- [x] Coverage ≥ 90% unit+integration+safety on PG18/Py3.11 (`coverage.yml`)
- [x] Latest-stack smoke Py 3.14 + PG 18 (`latest-stack.yml`)
- [x] Gitleaks full-history (`secret-scan.yml`) — A-12
- [x] Default `pytest` = `tests/unit` only (F-01)
- [x] G-* non-presence enforced by boundary tests
- [x] Private remote + push after local secret review

## Human gates (owner decisions recorded 2026-07-29)

| Gate ID | Decision | Notes |
| --- | --- | --- |
| A-06 | **approved** | Independent-history provenance attested (see attestation below) |
| A-07 | **approved** | Legacy repository remains private |
| A-08 | **timed_exception** | Do **not** archive; see exception record below |
| A-09 | **authorized / applied** | Legacy description updated to proposed superseded text |
| A-10 | **open** | Rejected for now — no factual owner attestation of rotation/revocation |
| A-11 | **exception** | Pre-first-push review was not completed; see exception record below |
| A-13 | **accepted** | Intentional test canaries; no scanner exclude |
| A-17 | **approved** | README/SECURITY skim |
| A-18 | **approved** | Keep new repository private; do not change visibility |
| A-19 | **approved** | Publication checklist prepared but unsigned; `PUBLICATION_APPROVED` remains false |

### A-06 owner attestation

> I attest that postgres-schema-inspector was created as a greenfield repository
> and that no Git history from database-count-and-truncate was imported,
> grafted, merged, mirrored, or rewritten into it.

### A-08 timed exception (legacy disposition)

- **Decision:** `timed_exception` — do **not** archive the legacy repository under
  this decision.
- **Reason:** Credential rotation has not yet received a factual owner
  attestation. The legacy repository must remain available privately until A-10
  is resolved and a separate archive authorization is issued.
- **Owner:** MilliganCo project owner
- **Compensating controls:**
  - repository remains PRIVATE
  - no new development is permitted
  - description must state that the repository is superseded
  - no releases, packages, Pages, deployments, or active workflows
  - legacy history must never be imported into postgres-schema-inspector
- **next_review_date:** 2026-08-12
- **exception_expires:** 2026-08-29

### A-09 legacy description (applied)

```text
Superseded by MilliganCo/postgres-schema-inspector.
Retained for historical reference only. No new development.
```

### A-10 credential rotation (open)

- **Decision:** rejected for now — keep **open**.
- **Reason:** No factual owner attestation confirming revocation or rotation has
  been supplied. Do not infer credential rotation from repository scans.
- **Required future attestation:**

> I attest that all credentials exposed in the legacy repository have been
> revoked or rotated and that the previous values are no longer valid.

### A-11 pre-first-push review (exception)

- **Status:** not completed before first push — documented exception.
- **Exception record:** The required staged-content review was not completed
  before the first push. The repository history and tracked content were
  subsequently reviewed through commit
  `483b0ce39e3046785f5c2fd5eadaa07c00e82774`.
- **Compensating evidence:**
  - repository remained private
  - full-history Gitleaks scan passed
  - TruffleHog findings were limited to reviewed test canaries
  - current tracked tree and complete new history were reviewed
  - no unintended legacy data or credentials were found
  - publication remains unapproved
- This exception records a **missed procedural gate**. It must **not** be
  rewritten as a claim that pre-first-push review occurred.

### A-13 TruffleHog canaries

> Accepted as intentional test canaries, not credentials.
> No scanner exclusion added.
> Exact files and matched values reviewed.

## Explicitly out of scope here

- [ ] `PUBLICATION_APPROVED` sign-off
- [ ] Visibility → public
- [ ] PyPI / TestPyPI / GitHub Release
- [ ] SBOM publication / announcements
- [ ] `pginspect impact` implementation plan / product code
- [ ] Archiving `MilliganCo/database-count-and-truncate` (requires separate
      authorization after A-10)

## Definition reminder

> `FOUNDATION_COMPLETE` = all atomic criteria A–G satisfied; repo remains private.  
> `PUBLICATION_APPROVED` = FOUNDATION_COMPLETE + pre_publication_gate + human sign-off.

**Current blocker for `FOUNDATION_COMPLETE`:** A-10 (credential rotation
attestation). Status remains **Foundation code-complete**.
