# Contributing to pginspect

Thank you for helping build **pginspect** (`postgres-schema-inspector`). Foundation is read-only diagnostics only — no truncate, GUI, or write actions.

## Development Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate

pip install -e .
pip install -r requirements/ci.txt
```

`requirements/ci.txt` is added in a later Foundation task; until then, editable install may be incomplete — follow the implementation plan in `docs/superpowers/plans/`.

## Running Tests

Default pytest discovery runs **unit tests only**:

```bash
pytest
```

Integration and safety suites require PostgreSQL and are invoked explicitly, for example:

```bash
pytest tests/integration
pytest tests/safety
```

## Test Data

- Do **not** use production databases, dumps, or real credentials in fixtures.
- Use local throwaway PostgreSQL instances or deterministic mocks.
- Canary strings in tests must remain scanner-safe (no real secrets).

## Pull Request Checklist

Before opening a PR, confirm alignment with Foundation acceptance criteria in:

`docs/superpowers/specs/2026-07-22-foundation-design.md` (§13)

At minimum:

- [ ] No `--password` / `-W` / `--dsn` or application connection defaults
- [ ] No persistent database mutation in production paths
- [ ] Public models use `extra=forbid`, frozen semantics, `allow_inf_nan=False`
- [ ] Redaction and error catalog rules preserved
- [ ] Unit tests pass locally; integration/safety run when touching DB code
- [ ] No secrets, `.env`, or `.pgpass` files committed

## Commits

Use conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `build:`). Keep changes small and reviewable.
