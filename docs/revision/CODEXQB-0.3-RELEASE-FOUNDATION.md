# CodexQB 0.3 Release Foundation

## Objective Status

**Complete.** CodexQB now has a capability-aware, descriptor-bound mount-identity layer; dependency-free human and JSON diagnostics; separate reproducible plugin and source distributions; strict verification and extraction; and split static, unit, platform, behavior, package, schema, privacy, and release gates.

This revision deliberately does not change Apply `VERIFIED`, host-attestation, receipt, review-ordering, or finalization semantics. No commit, push, tag, or release was performed.

## Objective

Make repository and filesystem security checks capability-aware without weakening existing guarantees; explain restricted-host failures safely; separate the installable plugin from the source distribution; and prove the result with current static, unit, platform, package, extraction, installation, and aggregate evidence.

## Baseline

Baseline was recorded on 2026-07-15 before implementation changes in an isolated worktree at the exact starting commit:

- Branch: `main`
- HEAD: `4b6aa90112e1cf679914f78313465b97c3f89eaa`
- `origin/main`: `4b6aa90112e1cf679914f78313465b97c3f89eaa`
- Tracked worktree: clean
- Platform: Darwin arm64, release 25.5.0
- Default Python: CPython 3.14.6
- Additional validation runtime: CPython 3.12.13 with `jsonschema` 4.26.0
- Existing ignored artifacts were classified and preserved: `.DS_Store`, Python caches, the historical `CodexQB-sanitized.zip`, and historical live-E2E evidence under `tmp/`.

Initial command evidence:

| Command | Baseline result |
| --- | --- |
| `python3 scripts/validate_apply_schema.py` | Environment failure: `jsonschema_validation_dependency_missing`; no code result inferred |
| `python3 -m compileall -q plugins scripts evals tests` | PASS |
| Selected safety/planner/artifact/evidence group | PASS, 109 tests |
| `make check-fast` in the exact isolated baseline worktree | PASS, 484 tests and 11 expected schema-dependency skips |
| `python3 -m unittest -v tests.test_goal_run` | PASS, 53 tests |
| `python3 -m unittest -v tests.test_apply_inventory` | PASS, 6 tests |
| `python3 -m unittest -v tests.test_package_manifest` | PASS, 17 tests |

At baseline, Darwin descriptor-bound `fstatfs` worked, while Linux `/proc/self/fdinfo`, `statx`, and `name_to_handle_at` were unavailable on the Darwin host. The implementation had no common provider result, assurance, reconciliation, failure-code, or operation-policy model.

## Confirmed Root Cause

At baseline, the primary defect was a shared mount-identity primitive limitation rather than independent Goal and Apply failures. `repository_evidence.py` directly implemented platform branches and exposed an opaque mount tuple, while Apply additionally used `st_dev` and path mount-point checks. Those checks remained useful defense in depth but could not prove a unique mount boundary or explain restricted Linux failures.

The packaging defect was shared-policy drift: producer exclusions were not fully enforced by the verifier, the source ZIP contained time-varying metadata, and the single historical `CodexQB-sanitized.zip` contract did not distinguish an installable plugin root from a source distribution.

## Security Invariants Preserved

- Filesystem identity (`st_dev`) is diagnostic only and is never promoted to high-assurance mount identity.
- Repository traversal remains descriptor-relative and no-follow.
- Atomic-write, provenance, workspace-drift, bounded-read, and post-open revalidation checks remain active.
- No path-based delete or replace fallback was introduced.
- Provider disagreement, malformed advertised providers, and absent high-assurance capability fail closed.
- Unsupported capability is reported as unsupported, never as supported.
- Doctor, exporter, verifier, and extractor diagnostics do not expose raw mount identities, usernames, home/repository paths, trust-key material, tokens, or untrusted exception text.
- Apply `VERIFIED`, host attestation, validation receipts, ordered review receipts, and finalization semantics remain unchanged; controller evidence alone still cannot produce trusted verification.
- Existing public error `secure_repository_mount_identity_unavailable` remains the compatibility boundary.
- Canonical extraction restores file modes and inner directory mode `0755`; strict installed-copy verification also accepts safe restrictive `0700` and `0750` directory mode bits while rejecting group- or world-writable modes.
- Plugin activation remains explicit-only through canonical `allow_implicit_invocation: false` metadata and `$codexqb` prompts.

## Capability Decision Table

| Operation class | Minimum assurance | Low/unavailable behavior |
| --- | --- | --- |
| Doctor/capability reporting | `unavailable` | Emit deterministic, path-safe diagnostics |
| Read-only repository evidence | `mount_unique_descriptor_bound` | Fail closed |
| Non-destructive artifact/package creation | `mount_unique_descriptor_bound` | Fail closed before output creation |
| Apply-run mutation | `mount_unique_descriptor_bound` | Fail closed before mutation |
| Replace/quarantine/delete | `mount_unique_descriptor_bound` plus provenance/atomic/no-follow guards | Fail closed before mutation |

Provider order is Linux fdinfo `mnt_id`, descriptor-bound Linux `statx`, descriptor-bound Linux `name_to_handle_at`, Darwin `fstatfs`, and finally diagnostic-only filesystem `fstat`. Comparable successful high-assurance providers must agree; disagreement fails closed.

## Capability Matrix

| Environment | Provider result | Assurance | Result |
| --- | --- | --- | --- |
| Darwin arm64, Python 3.14 | `darwin_fstatfs` selected; Linux providers expected unsupported; filesystem `fstat` diagnostic only | `mount_unique_descriptor_bound` | `ready`; all four guarded operation classes supported |
| Linux arm64 container, Python 3.14.6 | fdinfo and `statx` agree; `name_to_handle_at` reports stable expected-unsupported | `mount_reconciled` | `ready`; platform/repository/doctor suite 68/68 PASS |
| Restricted host with no high provider | filesystem `fstat` may remain diagnostic only | `filesystem_identity_only` or `unavailable` | mutation, replacement, quarantine, deletion, and package creation fail closed |

A real Linux same-`st_dev` nested bind-mount probe produced different descriptor mount identities and was rejected with `package_directory_nested_mount_rejected`.

## Checkpoints Completed

| Checkpoint | Status | Evidence |
| --- | --- | --- |
| 0 — Baseline and scope lock | COMPLETE | Exact baseline HEAD, platform, dependency state, initial tests, ignored artifacts, and root cause recorded |
| 1 — Mount identity providers and assurance policy | COMPLETE | Shared provider model, resolver/reconciliation, central operation policy, Goal/repository/Apply/package integration, Darwin and Linux proof |
| 2 — Doctor and blocker explanation | COMPLETE | Dependency-free human/JSON CLI, golden schema, privacy tests, ready/unsupported/failure distinctions |
| 3 — Separate reproducible artifacts | COMPLETE | Plugin/source layouts, schema v3, canonical ZIPs, v2 compatibility reader, immutable snapshot, bounded parser, strict extractor, red-team closure |
| 4 — Gate and CI split | COMPLETE | Separate Make targets, bounded test ownership, five-entry Ubuntu/macOS portability matrix, required platform policy on supported runners |
| 5 — Full validation and artifact cleanup | COMPLETE | Focused and aggregate suites, A/B artifacts, strict extraction, denylist scan, isolated install, release fail-closed check, final inventory |
| 6 — Documentation and final report | COMPLETE | README, installation, maintenance, changelog, compatibility notes, support matrix, and this evidence report aligned |

## Files Changed

The final published implementation scope is 21 modified tracked files and 12 new source/test files; there are no tracked binary, ZIP, cache, bytecode, macOS metadata, or `tmp/` artifacts.

- Capability/runtime: `repository_evidence.py`, `goal_run.py`, `apply_run.py`, new `mount_identity.py`, and new `doctor.py`.
- Packaging: `export_sanitized.py`, `verify_package_manifest.py`, new `extract_verified_package.py`, and new `package_policy.py`.
- Gates/CI: `Makefile`, `scripts/validate.sh`, new `scripts/run_test_suite.py`, `.github/workflows/validate.yml`, and `.gitignore`.
- Public contract: `README.md`, `docs/INSTALLATION.md`, `docs/MAINTAINING.md`, `CHANGELOG.md`, and this revision report.
- Tests: updated Apply, Goal, repository, exporter, package-manifest, and skill-content suites; new doctor, mount-identity, package-extraction, suite-partition, and platform-probe files.

## Commands Run and Result

All final results below are from changed code, not reused baseline results.

| Command/evidence | Final result |
| --- | --- |
| `python3 -m compileall -q plugins scripts evals tests` and focused `py_compile` | PASS |
| `git diff --check` | PASS |
| Selected safety/planner/artifact/evidence group | PASS, 109/109 |
| `python3 -m unittest -v tests.test_goal_run` | PASS, 56/56 |
| `python3 -m unittest -v tests.test_apply_inventory` | PASS, 7/7 |
| Full Apply regression | PASS, 164/164; trusted verification/finalization semantics retained |
| Package gate on Python 3.14 and Python 3.12 | PASS on both, 178 tests each with one expected case-insensitive-filesystem skip |
| `make check-static` | PASS; shell, YAML semantics, compile, and whitespace checks clean |
| `make check-fast` | PASS, 151/151 |
| `make check-unit` | PASS, 162/162 |
| `PLATFORM_POLICY=required make check-platform` | PASS, 26/26; Darwin doctor/probe `ready`, `mount_unique_descriptor_bound` |
| `make check-package` | PASS, 178 tests, one expected case-insensitive-filesystem skip |
| `make PYTHON=<dependency-backed-python> check-schema` | PASS, validator plus 11/11 schema parity tests |
| `make check-public-privacy` | PASS, 15 designated public files scanned, including the untracked pre-commit revision report |
| `make test` | PASS, 604 tests in 2288.154 seconds, 12 documented dependency/filesystem skips |
| `make check` | PASS; unit 162, platform 26, behavior 227 in 2280.451 seconds, metric/20-fixture checks, package 178 |
| Post-README/privacy follow-up | PASS; `make check-fast` 151/151, skill/documentation 43/43, package 179 with one expected skip, public privacy 15 files, and `git diff --check` |
| `make check-release` | Expected fail closed, exit 2: strict export reports path-safe `sanitized_export_failed` because release-only provenance conditions are intentionally unfinished |
| Ruff, mypy, pyright evaluation | Not installed and no new type/lint dependency was added; compile, static gates, focused tests, and both aggregate suites are the applicable proof |

Default Python 3.14 still lacks the intentional CI-only `jsonschema` dependency and returns `jsonschema_validation_dependency_missing`; the supported dependency-backed Python 3.12 environment passes the full schema gate.

## Artifact Inventory

Two independent worktree exports were produced for each artifact immediately before closing this report. The A/B pairs were byte-identical, verified as ZIPs, extracted with the no-follow helper under `umask 077`, verified again as strict roots, and scanned for `.git`, `__MACOSX`, `.DS_Store`, `__pycache__`, `*.pyc`, `tmp/`, ZIP members, and nested ZIP magic.

| Evidence pair | Type/root | Schema/layout | Files | Bytes | A/B SHA-256 | Result |
| --- | --- | --- | ---: | ---: | --- | --- |
| `plugin-a.zip` / `plugin-b.zip` | plugin; extraction root contains `.codex-plugin/plugin.json` | 3 / 1 | 44 | 1,166,356 | `b7ed30a799141c781122dc153cfc2136200a7277c9c029cc6e0100d99af055ab` | byte-identical; ZIP/extract/strict/denylist PASS |
| `source-a.zip` / `source-b.zip` | source; extraction root is `CodexQB/` | 3 / 1 | 165 | 3,960,904 | `1d91769691678a031f5aa8ee1e22f6f6eff708c376b12986e6738e4df5485a26` | byte-identical; ZIP/extract/strict/denylist PASS |

The source hash above intentionally precedes the final edit of this self-referential report. A second post-report A/B pair is produced for the terminal handoff; its exact hash is reported there without rewriting this file again.

The separately authorized README/privacy follow-up changed source-distribution bytes after the artifact table was closed. The source hashes in this section therefore remain reproducible Goal-closure evidence, not release truth for the eventual `main` commit. Any tagged release must regenerate both strict artifacts from the final tagged tree and satisfy `make check-release`.

An isolated local-marketplace smoke with Codex CLI 0.142.0 also passed under `umask 077`: network access was denied, writes to the real home and Codex directories were denied, install/cache location stayed in the isolated environment, installed contents matched the verified artifact byte-for-byte, strict installed-root verification passed, and installed `openai.yaml` remained canonical with `allow_implicit_invocation: false`.

The historical ignored `CodexQB-sanitized.zip` was preserved because it predates this Goal and may be user-retained evidence: 1,565,808 bytes, SHA-256 `9cf16d0d5c88dc9bf4937f4ba5cc9ac1f076142386925cdda8198ab15f6cfa52`. It is not used as current package proof.

## Known Unsupported Environments

- Non-Linux/non-Darwin runtimes have no declared high-assurance mount provider.
- Restricted Linux hosts where fdinfo, descriptor `statx`, and `name_to_handle_at` all fail cannot perform guarded writes or package creation.
- Darwin hosts without descriptor-bound `fstatfs` cannot perform guarded writes or package creation.
- Unusual filesystems that do not support descriptor `fchmod`, directory `fsync`, or atomic no-replace publication fail closed.

These environments receive deterministic diagnostics and do not silently fall back to `st_dev`.

## Artifact and Worktree Hygiene

- Tracked forbidden artifact count: 0.
- Final expected source scope: 21 modified tracked files plus 12 new source/test files.
- Final ignored inventory still contains the baseline-classified categories: 18 cache directories, 101 `.pyc` files, root `.DS_Store`, historical `tmp/` evidence, and the historical ZIP. The counts were unchanged across the pre-final inventory and final gates; no user-owned ignored artifact was deleted.
- All new package/extraction/install evidence was written outside the repository.

## Remaining Blockers and Security Trade-offs

- Goal blockers: none.
- Release-only blockers remain intentionally open: the worktree contains the reviewed implementation, `CHANGELOG.md` remains `Unreleased`, no final `v0.3.0` tag exists, and strict clean/tag/origin provenance is therefore unavailable. `make check-release` fails closed as designed.
- The GitHub-hosted five-entry matrix is defined but was not observed remotely in this local Goal; real Darwin and real Linux container evidence were obtained locally.
- Explicit-only activation is proven by packaged metadata, negative package tests, canonical validation, and installed-copy parity. A fresh live-host negative model invocation was not run, so this report does not overclaim model behavior beyond the enforced metadata contract.
- Manifest hashes are unkeyed consistency records, not publisher signatures, trusted timestamps, or host attestation.
- Descriptor-bound mount assurance cannot absolutely prevent an external same-UID or privileged writer from mutating data immediately after the last verification checkpoint. Stronger atomicity would require an immutable filesystem snapshot/seal or exclusion of concurrent writers.
- Fresh live schema-v3 trusted completion evidence and final release tagging remain separate release gates. Apply continues to keep `VERIFIED` and finalization closed without trusted host/agent attestation.

## Goal Closure State

The values below record the completed release-foundation Goal before the user's separately authorized commit/push follow-up. They are historical closure evidence, not a claim about refs after publication.

- Branch: `main`
- HEAD: `4b6aa90112e1cf679914f78313465b97c3f89eaa`
- `origin/main`: `4b6aa90112e1cf679914f78313465b97c3f89eaa`
- Expected implementation worktree: dirty by design, with only the 33 reviewed source/test/document changes listed above
- Commit/push/tag/release: not performed during the release-foundation Goal; a later commit/push requires separate user authorization, while tag/release remain gated

## Recommended Next Goal

Controller-assured completion ile host-attested trusted completion’ı iki ayrı finalization seviyesi olarak modelle.

## Final Status

Objective status: **complete**.
