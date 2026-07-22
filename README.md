# pginspect

**postgres-schema-inspector** — explainable, read-only PostgreSQL diagnostics.

> **Status:** Foundation work in progress (private). Not yet published to PyPI.

## What it is

`pginspect` connects to PostgreSQL using libpq-compatible configuration, establishes a fail-closed read-only diagnostic session, and reports structured findings. It does **not** truncate data, run maintenance writes, or provide a GUI.

## Planned Foundation commands

| Command | Purpose |
| ------- | ------- |
| `pginspect version` | Print the installed package version |
| `pginspect connect-test` | Verify connectivity and session safety settings |

Implementation lands in later Foundation tasks. There are no other product commands in scope for Foundation.

## Authentication

Connection parameters (`--host`, `--port`, `--dbname`, `--user`, `--service`, SSL mode, timeouts) are explicit CLI options where supported. **Passwords are not accepted on the command line.** Use libpq mechanisms (environment variables, `.pgpass`, service files) — the application does not define host, port, user, database, or password defaults.

## Install from source

```bash
pip install -e .
pip install -r requirements/ci.txt
```

## Documentation

- Design: [`docs/superpowers/specs/2026-07-22-foundation-design.md`](docs/superpowers/specs/2026-07-22-foundation-design.md)
- Implementation plan: [`docs/superpowers/plans/2026-07-22-foundation.md`](docs/superpowers/plans/2026-07-22-foundation.md)

## License

MIT — see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md).
