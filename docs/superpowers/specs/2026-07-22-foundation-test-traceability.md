# Foundation test traceability matrix

Maps every Spec §13 criterion ID (`A-01`…`G-10`) to an automated pytest node id,
CI job, and/or named human gate. Required CI jobs must not silently skip, use
`continue-on-error`, or automatic flaky retries (F-16).

**Spec:** `docs/superpowers/specs/2026-07-22-foundation-design.md` §13  
**Plan:** Tasks 14–17

## Legend

| Column | Meaning |
| --- | --- |
| Verification | pytest node id(s), workflow assertion, or human gate id |
| CI job | GitHub Actions workflow job name (or `local` / `human`) |
| Status | `automated` / `human` / `hybrid` |

Human gate ids are stable names used in `FOUNDATION_COMPLETE.md`.

---

## A. Repository & security

| ID | Criterion (short) | Verification | CI job | Status |
| --- | --- | --- | --- | --- |
| A-01 | Independent `git init` history | `human:owner_attests_independent_init` + `git rev-list --max-parents=0` single root | human + local | hybrid |
| A-02 | Exactly one root commit | `git rev-list --max-parents=0 --all` count == 1 | human gate `gate:single_root` (recorded in FOUNDATION_COMPLETE); re-check before publish | automated-check / human-record |
| A-03 | No git replace refs | `git replace -l` empty | `gate:no_replace_refs` | automated-check / human-record |
| A-04 | No imported legacy branches/tags/bundles | Owner review of refs + history; no legacy remotes | `gate:no_legacy_import` | hybrid |
| A-05 | Legacy `.git` not copied | Owner attestation | `gate:legacy_git_not_copied` | human |
| A-06 | Independent-history provenance attested | Owner sign-off | `gate:A-06_provenance` | human |
| A-07 | Legacy repo remains private | Owner check on GitHub | `gate:A-07_legacy_private` | human |
| A-08 | Legacy archived **or** named exception | Owner archive/exception note | `gate:A-08_legacy_archive_or_exception` | human |
| A-09 | Legacy description superseded | Owner updates legacy description | `gate:A-09_legacy_description` | human |
| A-10 | Credentials rotation confirmed (safe attestation) | Ops note outside public tree | `gate:A-10_rotation` | human |
| A-11 | Staged content reviewed before first push | Owner review | `gate:A-11_staged_review` | human |
| A-12 | Gitleaks full-history (fetch-depth 0, no baselines) | `.github/workflows/secret-scan.yml` gitleaks job | `secret-scan / gitleaks` | automated |
| A-13 | TruffleHog full-history | `gate:A-13_trufflehog` — run pinned TruffleHog on full history before publish (workflow may be added; recorded as human/ops until workflow lands) | human / ops | human |
| A-14 | Canary strings scanner-safe | `tests/unit/test_redaction.py::test_sanitize_strips_canaries`; `tests/unit/test_renderers.py::test_full_canary_leakage_json_text_and_text_debug`; fixture passwords are disposable CI values in `tests/fixtures/pginspect_probe.sql` | `unit` / `lint-type` | automated |
| A-15 | `SECURITY.md` present | Path exists (repo root) | `gate:files_present` + checkout | automated-check |
| A-16 | `LICENSE` (MIT) present | Path exists | `gate:files_present` | automated-check |
| A-17 | README has no hardcoded hosts/users/passwords | README review + no production DSN literals | `gate:A-17_readme_clean` + human skim | hybrid |
| A-18 | Visibility private at FOUNDATION_COMPLETE | Owner confirms private; no visibility flip in Foundation | `gate:A-18_remain_private` | human |
| A-19 | Publication checklist prepared (unsigned) | `docs/superpowers/specs/FOUNDATION_COMPLETE.md` | `gate:A-19_publication_checklist` | human |

---

## B. Package & toolchain

| ID | Criterion (short) | Verification | CI job | Status |
| --- | --- | --- | --- | --- |
| B-01 | src-layout package `pginspect` | `pyproject.toml` + import smoke | `unit / package-build-smoke` | automated |
| B-02 | `requires-python >= 3.11` | `pyproject.toml` | `unit` | automated |
| B-03 | Console script entry | `unit / package-build-smoke` runs `pginspect version` | `unit / package-build-smoke` | automated |
| B-04 | psycopg3, Typer, Rich, Pydantic v2 | `pyproject.toml` dependencies | `unit` | automated |
| B-05 | `python -m build` sdist+wheel | `unit.yml` package-build-smoke | `unit / package-build-smoke` | automated |
| B-06 | Wheel install + `pip check` | same | `unit / package-build-smoke` | automated |
| B-07 | Installed `pginspect version` | same | `unit / package-build-smoke` | automated |
| B-08 | Installed `pginspect connect-test --help` | same | `unit / package-build-smoke` | automated |
| B-09 | Wheel excludes tests/credentials | `unit.yml` Inspect wheel contents step | `unit / package-build-smoke` | automated |
| B-10 | Wheel smoke on 3.11 and 3.14 | matrix in `unit.yml` | `unit / package-build-smoke` | automated |
| B-11 | Ruff check | `lint-type.yml` | `lint-type` | automated |
| B-12 | Ruff format --check | `lint-type.yml` | `lint-type` | automated |
| B-13 | mypy strict | `lint-type.yml` | `lint-type` | automated |
| B-14 | Architecture boundaries §12 | `tests/unit/test_package_boundaries.py` (all tests) | `lint-type` / `unit` | automated |
| B-15 | `requirements/ci.txt` pins | workflows install `-r requirements/ci.txt` | `lint-type`, `schema`, `unit`, `integration`, `safety`, `coverage` | automated |
| B-16 | `contents: read`; actions SHA-pinned; PG digest policy | workflow YAML review; PG tags + digest-pin comment | `gate:B-16_ci_contract` | hybrid |
| B-17 | Fixed Linux runner; no `pull_request_target`; no write token | workflow YAML | `gate:B-17_runner_contract` | automated-check |

---

## C. CLI contract

| ID | Criterion (short) | Verification | CI job | Status |
| --- | --- | --- | --- | --- |
| C-01 | Only `version` / `connect-test` | `tests/unit/test_cli_usage.py::test_unknown_command_does_not_echo_token`; boundaries | `unit` | automated |
| C-02 | No `--password` / `-W` | `tests/unit/test_cli_usage.py` help/options; package boundaries | `unit` | automated |
| C-03 | No `--dsn` | same | `unit` | automated |
| C-04 | No interactive password prompt | CLI implementation + usage tests | `unit` | automated |
| C-05 | No app defaults for host/port/user/dbname/password | `tests/unit/test_connection_kwargs.py`; `tests/unit/test_config.py::test_connection_config_has_no_password_field` | `unit` | automated |
| C-06 | `--service` / libpq env/passfile | `tests/integration/test_connect_test_live.py::test_libpq_service_precedence_asserts_actual_database` | `integration` | automated |
| C-07 | `--connect-timeout` always applied | `tests/unit/test_connection_kwargs.py::test_build_connect_kwargs_sets_timeout_and_fallback_app_name` | `unit` | automated |
| C-08 | `fallback_application_name` from helper | same | `unit` | automated |
| C-09 | Full option set §10 | `tests/unit/test_cli_usage.py`; CLI source | `unit` | automated |
| C-10 | Command-local `--format`; root → 4 | `tests/unit/test_cli_usage.py::test_root_format_returns_4` | `unit` | automated |
| C-11 | Usage → exit 4, no echoed values | `tests/unit/test_cli_usage.py::test_port_abc_returns_4_without_echoing_value` (+ related) | `unit` | automated |
| C-12 | Empty argv → 4 | `tests/unit/test_cli_usage.py::test_empty_argv_returns_4` | `unit` | automated |
| C-13 | No completion; `-h` is host | `tests/unit/test_cli_usage.py::test_no_completion_options_in_help`; `test_connect_test_help_uses_h_for_host` | `unit` | automated |
| C-14 | SIGINT/KeyboardInterrupt → 130 | `tests/unit/test_main_wrapper.py::test_keyboard_interrupt_returns_130`; `tests/integration/test_entrypoint_sigint.py::test_entrypoint_sigint_exits_130_without_json` (POSIX) | `unit` / `integration` | automated |
| C-15 | Fatal → exit 5 | `tests/unit/test_main_wrapper.py::test_fatal_render_returns_5` | `unit` | automated |
| C-16 | No `sys.exit()` in src | `tests/unit/test_package_boundaries.py::test_no_src_module_calls_sys_exit` | `lint-type` / `unit` | automated |
| C-17 | Callbacks return `int`; `main()` wrapper | `tests/unit/test_main_wrapper.py` | `unit` | automated |
| C-18 | Stream contracts §10 | `tests/unit/test_main_wrapper.py::test_connect_test_json_debug_leaves_stderr_empty`; renderer tests | `unit` | automated |
| C-19 | No `Exit: N` in text | `tests/unit/test_renderers.py::test_no_exit_n_line_in_text` | `unit` | automated |
| C-20 | version text exact | `tests/unit/test_renderers.py::test_version_text_exact` | `unit` | automated |

---

## D. Session & connect-test

| ID | Criterion (short) | Verification | CI job | Status |
| --- | --- | --- | --- | --- |
| D-01 | One parameterized establish `set_config` SELECT | `tests/unit/test_session_state_machine.py`; session source | `unit` | automated |
| D-02 | One structured verify SELECT (ms) | `tests/integration/test_connect_test_live.py::test_guc_verification_ms_units_and_search_path` | `integration` | automated |
| D-03 | One atomic capability SELECT | `tests/unit/test_capabilities_sql_constants.py` | `unit` | automated |
| D-04 | No public `execute(query)` / `show(name)` | `tests/unit/test_package_boundaries.py::test_no_production_public_execute_query` | `lint-type` / `unit` | automated |
| D-05 | After SQL error → FAILED | `tests/unit/test_session_state_machine.py::test_after_sql_error_session_is_failed_and_rejects_further_queries` | `unit` | automated |
| D-06 | Capabilities only when READY | `tests/unit/test_session_state_machine.py::test_query_before_ready_raises_internal`; orchestration | `unit` | automated |
| D-07 | `force_rollback=True` | `tests/unit/test_session_state_machine.py::test_force_rollback_transaction_used` | `unit` | automated |
| D-08 | No persistent mutation by production | safety suite + boundaries; adversarial SQL only under `tests/safety/` | `safety` | automated |
| D-09 | `write_probe=not_run`; `verification_level=settings` | `tests/integration/test_connect_test_live.py::test_guc_verification_ms_units_and_search_path` | `integration` | automated |
| D-10 | Read-only config wording (not “role cannot write”) | renderer/text contract + design; `tests/unit/test_renderers.py` | `unit` | automated |
| D-11 | Custom `application_name` preserved | `tests/integration/test_connect_test_live.py::test_pgappname_custom_preserved` | `integration` | automated |
| D-12 | Version policy module only | `tests/unit/test_version_policy.py` | `unit` | automated |
| D-13 | Missing extensions → unavailable | `tests/unit/test_capabilities_sql_constants.py::test_extension_availability_map_deterministic` | `unit` | automated |

---

## E. Models & output

| ID | Criterion (short) | Verification | CI job | Status |
| --- | --- | --- | --- | --- |
| E-01 | Finding union of eight | `tests/unit/models/test_enums_and_context.py::test_finding_id_has_eight_values`; `test_findings.py` | `unit` / `schema` | automated |
| E-02 | Typed evidence per §9 | `tests/unit/models/test_findings.py` | `unit` | automated |
| E-03 | Severity/status fixed | `tests/unit/models/test_findings.py` | `unit` | automated |
| E-04 | CommandResult envelope | `tests/unit/models/test_command_result.py` | `unit` | automated |
| E-05 | `extra=forbid`, `allow_inf_nan=False` | `tests/unit/models/test_enums_and_context.py::test_known_extension_snapshot_rejects_extra_keys` | `unit` | automated |
| E-06 | Semantic validators | `tests/unit/models/test_command_result.py::test_reject_mismatched_exit_on_manual_construct` | `unit` | automated |
| E-07 | Deterministic finding order | `tests/unit/test_connectivity_orchestration.py::test_full_success_three_findings_context_exit_0`; renderers section order | `unit` | automated |
| E-08 | Schema `$id` URNs / Draft 2020-12 | `tests/unit/test_schema_drift.py::test_committed_schemas_declare_draft_and_ids` | `schema` / `unit` | automated |
| E-09 | Schema drift bytes | `tests/unit/test_schema_drift.py::test_committed_command_result_schema_matches_generated` (+ finding) | `schema` / `unit` | automated |
| E-10 | Goldens validate + round-trip | `tests/unit/test_schema_drift.py::test_golden_fixtures_validate_and_round_trip` | `schema` / `unit` | automated |
| E-11 | JSON sort_keys / indent / newline | `tests/unit/test_renderers.py::test_json_has_single_trailing_newline_and_sorted_keys` | `unit` | automated |
| E-12 | Text escapes controls/bidi | `tests/unit/test_renderers.py::test_ansi_and_bidi_are_escaped` | `unit` | automated |
| E-13 | database/role/session_user literals | `tests/unit/test_renderers.py::test_session_user_literal_when_different` | `unit` | automated |
| E-14 | Host only as fingerprint | `tests/unit/test_redaction.py::test_host_fingerprint_format`; canary tests | `unit` | automated |
| E-15 | Domain exceptions no raw cause | `tests/unit/test_connect_error_mapping.py::test_domain_exception_retains_no_raw_exception_object` | `unit` | automated |
| E-16 | Debug payload sanitized | `tests/unit/test_redaction.py::test_build_safe_debug_frames_no_home_paths_or_locals` | `unit` | automated |
| E-17 | E2E canary JSON+text | `tests/unit/test_renderers.py::test_full_canary_leakage_json_text_and_text_debug` | `unit` | automated |

---

## F. Tests & matrix

| ID | Criterion (short) | Verification | CI job | Status |
| --- | --- | --- | --- | --- |
| F-01 | Default pytest → `tests/unit` only | `pyproject.toml` `testpaths`; `pytest` with no path | local / `unit` | automated |
| F-02 | Integration PG 14–18 / Py 3.11 | `tests/integration/**` matrix | `integration` | automated |
| F-03 | Safety probes PG 14–18 | `tests/safety/**` matrix | `safety` | automated |
| F-04 | Unit Py 3.11–3.14 | `unit.yml` matrix | `unit` | automated |
| F-05 | Latest-stack 3.14+PG18 | `latest-stack.yml` | `latest-stack` | automated |
| F-06 | Fresh session; SQLSTATE 25006 | `tests/safety/test_write_probes.py::test_write_probe_rejected_with_25006[*]` | `safety` | automated |
| F-07 | Observer unchanged | same + reconnect variants | `safety` | automated |
| F-08 | Subject has real write grants | `tests/safety/conftest.py` / `_helpers.assert_subject_has_write_grants` | `safety` | automated |
| F-09 | Closed local port refused | `tests/integration/test_connect_test_live.py::test_closed_port_network` | `integration` | automated |
| F-10 | Loopback stall → timeout | `tests/integration/test_connect_test_live.py::test_loopback_stall_timeout` | `integration` | automated |
| F-11 | Real SIGINT → 130 | `tests/integration/test_entrypoint_sigint.py::test_entrypoint_sigint_exits_130_without_json` | `integration` | automated |
| F-12 | Libpq precedence actual DB | `tests/integration/test_connect_test_live.py::test_libpq_service_precedence_asserts_actual_database` | `integration` | automated |
| F-13 | Session establish atomicity | `tests/integration/test_connect_test_live.py::test_session_establishment_atomicity_discards_failed_session` | `integration` | automated |
| F-14 | Branch coverage ≥ 90% | `coverage.yml` `--cov-fail-under=90` | `coverage` | automated |
| F-15 | This matrix covers every §13 ID | this document | docs review | automated-check |
| F-16 | No silent skip / continue-on-error / auto retry | workflow YAML policy | `gate:F-16_ci_policy` | automated-check |

---

## G. Explicit non-presence

| ID | Criterion (short) | Verification | CI job | Status |
| --- | --- | --- | --- | --- |
| G-01 | No doctor/inventory/… commands | `tests/unit/test_cli_usage.py`; `tests/unit/test_package_boundaries.py` | `unit` / `lint-type` | automated |
| G-02 | No GUI | `tests/unit/test_package_boundaries.py::test_absent_deferred_packages_and_modules` | `lint-type` / `unit` | automated |
| G-03 | No production write path | boundaries + safety (writes only in tests) | `lint-type` / `safety` | automated |
| G-04 | Adversarial SQL only `tests/safety/` | `tests/safety/_adversarial_sql.py`; wheel excludes tests | `unit / package-build-smoke` / `safety` | automated |
| G-05 | No deferred dirs / `doctor.py` | `tests/unit/test_package_boundaries.py::test_absent_deferred_packages_and_modules` | `lint-type` / `unit` | automated |
| G-06 | No plugin protocols / SQL loader | boundaries + source layout | `lint-type` / `unit` | automated |
| G-07 | No deferred placeholders / feature flags | source review + boundaries | `lint-type` | automated |
| G-08 | No telemetry/SaaS | boundaries / network non-presence | `lint-type` | automated |
| G-09 | No outbound net except requested PG | design + no http clients in src | `lint-type` / `unit` | automated |
| G-10 | Schema `$id` not fetched at runtime | schema tests load local files only | `schema` / `unit` | automated |

---

## CI job index

| Workflow | Job | Suites / purpose |
| --- | --- | --- |
| `lint-type.yml` | `lint-type` | ruff, mypy, architecture |
| `unit.yml` | `unit`, `package-build-smoke` | unit matrix; wheel smoke |
| `schema.yml` | schema drift + goldens | schemas |
| `integration.yml` | `integration` | PG 14–18 × Py 3.11 |
| `safety.yml` | `safety` | write-probes PG 14–18 |
| `coverage.yml` | `coverage` | unit+integration+safety, fail_under=90 |
| `latest-stack.yml` | `latest-stack` | Py 3.14 + PG 18 smoke |
| `secret-scan.yml` | `gitleaks` | full-history secrets (A-12) |

---

## Notes

1. Integration/safety tests **skip** when `PGINSPECT_TEST_DSN` is unset (local without Postgres).
   CI sets the DSN from the service container — required jobs must not skip.
2. SIGINT entrypoint test skips on Windows with an explicit reason; POSIX CI covers F-11.
3. Human gates A-06, A-08, A-10, A-11, A-18, A-19 remain owner-owned at FOUNDATION_COMPLETE.
4. A-13 (TruffleHog) is listed as a named human/ops gate until a pinned workflow is added;
   A-12 (Gitleaks) is automated via `secret-scan.yml`.
