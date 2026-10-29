# Public source preview — 2026-10-29

pginspect is a PostgreSQL diagnostic source project with fail-closed read-only sessions.
The Foundation commands and impact-analysis prototype are described in README.md.
Public source visibility is distinct from PyPI publication or operational reliability guarantees.

## Publication evidence

- Complete reachable source history reviewed; no confirmed credential/private-data disclosure blocker.
- Semantic password/DSN hits are explicit synthetic redaction canaries and disposable CI fixtures.
- 208 historical Actions runs accounted for: 8 accessible logs scanned with no findings;
  200 returned HTTP410 (expired/unavailable, **not** counted as passed log scans).
- Workflow permissions are contents:read; PostgreSQL integration tests use disposable service
  containers. No production deployment, pull_request_target, model or secret invocation is enabled.
- Own documentation-push runs are checked separately before public visibility is enabled.

The legacy credential-rotation attestation remains historically unproven. This publication does
not authorize or expose the separate legacy repository/history; those remain private.
No live production database was contacted for this publication review.
