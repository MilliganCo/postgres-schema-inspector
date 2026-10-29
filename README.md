# pginspect

**postgres-schema-inspector** — explainable, read-only PostgreSQL diagnostics (Foundation).

> **Status:** Public source preview. Foundation and in-repository impact prototype; not published to PyPI. See [PUBLICATION.md](PUBLICATION.md) for current review and limitations.

## What it is

`pginspect` connects to PostgreSQL using libpq-compatible configuration, establishes a fail-closed read-only diagnostic session, and reports structured findings as text or JSON.

It does **not** truncate data, run maintenance writes, claim that a role is unable to write, or provide a GUI. Session safety means verified `default_transaction_read_only` / timeouts / `search_path` — write probes are CI-only adversarial tests, not a product feature.

## Commands

| Command | Purpose |
| ------- | ------- |
| `pginspect version` | Print the installed package version |
| `pginspect connect-test` | Verify connectivity and session safety settings |
| `pginspect impact` | **In-repository prototype** — catalog change-impact analysis for selected `ALTER TABLE` forms (not a shipped, reliability-guaranteed release) |

Foundation product surface remains `version` and `connect-test`. `impact` remains an in-repository prototype; public source visibility is not a reliability guarantee.

### Examples

```bash
pginspect version
pginspect connect-test --host db.example --port 5432 --dbname app --user monitor --format json
pginspect connect-test --service mylibpqservice --format text
```

## Authentication

Connection parameters (`--host` / `-h`, `--port`, `--dbname`, `--user`, `--service`, `--sslmode`, timeouts) are explicit CLI options where supported.

**Passwords are not accepted on the command line** (no `--password`, `-W`, or `--dsn`). Use libpq mechanisms:

- environment (`PGPASSWORD`, and other libpq variables as documented by PostgreSQL)
- `.pgpass`
- service files (`PGSERVICEFILE` / `--service`)

The application does **not** define host, port, user, database, or password defaults and does not copy `PG*` variables into connect kwargs.

## Install from source

```bash
pip install -e .
pip install -r requirements/ci.txt
pginspect version
```

Requires Python ≥ 3.11.

## Testing

```bash
# Default: unit tests only (no PostgreSQL required)
pytest

# Integration / safety (require a throwaway Postgres and PGINSPECT_TEST_DSN)
export PGINSPECT_TEST_DSN='postgresql://postgres:…@localhost:5432/postgres'
pytest tests/integration
pytest tests/safety
```

CI runs PostgreSQL 14–18 matrices via GitHub Actions service containers.

## Documentation

- Design: [`docs/superpowers/specs/2026-07-22-foundation-design.md`](docs/superpowers/specs/2026-07-22-foundation-design.md)
- Traceability: [`docs/superpowers/specs/2026-07-22-foundation-test-traceability.md`](docs/superpowers/specs/2026-07-22-foundation-test-traceability.md)
- Completion checklist: [`docs/superpowers/specs/FOUNDATION_COMPLETE.md`](docs/superpowers/specs/FOUNDATION_COMPLETE.md)
- Implementation plan: [`docs/superpowers/plans/2026-07-22-foundation.md`](docs/superpowers/plans/2026-07-22-foundation.md)

## License

MIT — see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md).
