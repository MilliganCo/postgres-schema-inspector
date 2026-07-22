# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.x     | Yes       |

Pre-1.0 releases may change behavior and contracts without a major-version bump while Foundation is in progress.

## Reporting a Vulnerability

Please report security issues through a **private** channel (not a public GitHub issue):

- **Email:** security@example.com *(placeholder — replace before public release)*

Include a description, steps to reproduce, and impact assessment. We aim to acknowledge reports within a few business days.

## Clean Public History

This repository was created as a **greenfield** project with an independent Git history. No commits, trees, tags, branches, reflogs, bundles, grafts, or automated imports from any legacy repository are included in release-reachable history.

Before the first push and again before any public release, maintainers run full-history secret scans (e.g. Gitleaks and TruffleHog with `fetch-depth: 0` and no baselines).

## Credential Handling

- **No CLI password values.** The `pginspect` CLI does not accept `--password`, `-W`, or `--dsn`. Credentials are delegated to libpq (environment, `.pgpass`, service files, etc.).
- **No application connection defaults.** The tool does not ship hardcoded host, port, user, database, or password defaults.
- **Redaction is always on.** Debug output must never disable credential, DSN, connection-option, or sensitive-value redaction.

## Query Text and Privacy (Future)

Future diagnostic features may observe SQL or catalog metadata. When that scope is added, output contracts and redaction rules will be documented here. Foundation (`version`, `connect-test`) does not collect or emit user query text.

## Scope

Foundation provides read-only diagnostic sessions against PostgreSQL. Persistent database mutation is forbidden in production code paths.
