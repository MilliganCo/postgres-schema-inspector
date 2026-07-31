# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Prototype (private repository only): `pginspect impact` change-impact analysis with
  committed `impact-command-result` / `impact-statement-card` **0.1** JSON Schemas,
  Demo fixtures, and safety gates. Not a published or stability-guaranteed release.
- Foundation design, plan, security baseline, and MIT licensing.
- Installable `pginspect` package (Python ≥3.11) with console script entrypoint.
- CLI commands `version` and `connect-test` (text/JSON); fail-closed read-only
  `DiagnosticSession`; typed Finding / CommandResult contracts; committed JSON Schemas.
- Unit, schema, integration (PostgreSQL 14–18), safety write-probe, coverage, and
  latest-stack CI workflows; Gitleaks full-history secret scan.
- Traceability matrix mapping Spec §13 criteria A-01…G-10 to tests and human gates.
- `FOUNDATION_COMPLETE` checklist (repo remains private; publication is a separate gate).

### Security

- No CLI passwords/`--dsn`; libpq-only credentials; redaction/fingerprint helpers;
  canary leakage tests for JSON and text output.
