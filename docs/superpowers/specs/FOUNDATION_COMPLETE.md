# Foundation status: **code-complete** (not yet `FOUNDATION_COMPLETE`)

Local engineering for Spec §§1–14 is implemented (package, CLI, models, unit tests,
workflow definitions). That is **Foundation code-complete**.

True **`FOUNDATION_COMPLETE`** still requires closed **human** security gates below
(even though private remote + green GHA PG 14–18 are now in place). This document
tracks that gap. It does **not** authorize visibility changes or
`PUBLICATION_APPROVED`.

**Date (UTC):** 2026-07-22 (updated 2026-07-29)  
**Repo:** `MilliganCo/postgres-schema-inspector`  
**Visibility:** **private** (A-18) — do not flip to public from this checklist.  
**Verified HEAD (local = origin/main):** `fd1e7d3162d07a5901341e8af92ca037f3f1e138`

## Repository state notes

| Fact | Status |
| --- | --- |
| GitHub remote | **Created** — `https://github.com/MilliganCo/postgres-schema-inspector.git` |
| Visibility | **private** (confirmed via `gh api`; `has_pages=false`; no releases) |
| Green GHA on HEAD | **Yes** — unit/lint/schema/integration(14–18)/safety(14–18)/coverage/latest-stack/secret-scan |
| `PUBLICATION_APPROVED` | **Not done** — separate gate |
| Legacy archive / description | Human remaining (A-08, A-09) |
| Credential rotation attestation | Human remaining (A-10); engineering path used zero legacy secrets |

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
- [x] Private remote + first push after local secret review

## Human remaining (required for true FOUNDATION_COMPLETE sign-off)

| Gate ID | Item | Notes |
| --- | --- | --- |
| A-06 | Independent-history provenance attested by owner | Sign after reviewing root commit / no legacy grafts |
| A-07 | Legacy repository remains private | Owner GitHub check |
| A-08 | Legacy archived **or** named exception + follow-up | Owner decision — **do not archive without explicit instruction** |
| A-09 | Legacy description states superseded | Owner updates legacy repo |
| A-10 | Credentials rotation confirmed (safe attestation only) | Ops note outside public tree |
| A-11 | Staged content reviewed before first push | Owner confirms review of pushed tree |
| A-13 | TruffleHog full-history scan | Local scan done; canary DSN false positives documented — owner accepts or adds minimal exclude |
| A-17 | README skim for host/user/password literals | Spot-check after Foundation README |
| A-18 | Visibility remains private | Confirmed private after push |
| A-19 | Publication checklist prepared (unsigned) | This file + pre_publication_gate in design §2 |

## Explicitly out of scope here

- [ ] `PUBLICATION_APPROVED` sign-off
- [ ] Visibility → public
- [ ] PyPI / TestPyPI / GitHub Release
- [ ] SBOM publication / announcements
- [ ] `pginspect impact` implementation plan / product code

## Definition reminder

> `FOUNDATION_COMPLETE` = all atomic criteria A–G satisfied; repo remains private.  
> `PUBLICATION_APPROVED` = FOUNDATION_COMPLETE + pre_publication_gate + human sign-off.

Owner should tick human gates above when evidence exists. Automated remote/CI
portion of Foundation close is ready for that review.
