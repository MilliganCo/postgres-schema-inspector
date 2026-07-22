# FOUNDATION_COMPLETE checklist

Engineering record for Spec §13 `FOUNDATION_COMPLETE`. This document marks what is
**automated** vs **human remaining**. It does **not** authorize visibility changes
or `PUBLICATION_APPROVED`.

**Date (UTC):** 2026-07-22  
**Repo:** local greenfield `postgres-schema-inspector` (intended `MilliganCo/postgres-schema-inspector`)  
**Visibility:** remains **private** (A-18) — do not flip to public from this checklist.

## Repository state notes

| Fact | Status |
| --- | --- |
| GitHub remote | **May not exist yet** — do not push unless `origin` is configured and private |
| Visibility | Private (required at FOUNDATION_COMPLETE) |
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

## Human remaining (required for true FOUNDATION_COMPLETE sign-off)

| Gate ID | Item | Notes |
| --- | --- | --- |
| A-06 | Independent-history provenance attested by owner | Sign after reviewing root commit / no legacy grafts |
| A-07 | Legacy repository remains private | Owner GitHub check |
| A-08 | Legacy archived **or** named exception + follow-up | Owner decision |
| A-09 | Legacy description states superseded | Owner updates legacy repo |
| A-10 | Credentials rotation confirmed (safe attestation only) | Ops note outside public tree |
| A-11 | Staged content reviewed before first push | Before first remote push |
| A-13 | TruffleHog full-history scan | Named ops gate until pinned workflow added |
| A-17 | README skim for host/user/password literals | Spot-check after Foundation README |
| A-18 | Visibility remains private | Confirmed; no flip |
| A-19 | Publication checklist prepared (unsigned) | This file + pre_publication_gate in design §2 |
| — | Create private GitHub remote if missing | `gh repo create … --private` then `git push -u` |
| — | Push `main` when remote exists | Do **not** push if no remote / wrong visibility |
| — | Archive or contain legacy project | Out of band |
| — | Run GHA matrices on GitHub | Local Docker may be unavailable; CI is source of truth for F-02…F-05 |

## Explicitly out of scope here

- [ ] `PUBLICATION_APPROVED` sign-off
- [ ] Visibility → public
- [ ] PyPI / TestPyPI / GitHub Release
- [ ] SBOM publication / announcements

## Definition reminder

> `FOUNDATION_COMPLETE` = all atomic criteria A–G satisfied; repo remains private.  
> `PUBLICATION_APPROVED` = FOUNDATION_COMPLETE + pre_publication_gate + human sign-off.

Owner should tick human gates above when evidence exists, then treat engineering
Foundation as closed for product scope §§1–13.
