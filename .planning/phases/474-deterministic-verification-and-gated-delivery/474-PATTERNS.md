# Phase 474: Deterministic Verification And Gated Delivery - Pattern Map

**Mapped:** 2026-07-18
**Repositories searched:** `stoa-backend`, `/Users/zhdeng/stoa-frontend`, `/Users/zhdeng/stoa-infra`
**Scope:** backend, Web, infrastructure, workflow, evidence, and tests proposed by `474-CONTEXT.md` and `474-RESEARCH.md`

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `scripts/release_gate.py` | utility/orchestrator | batch, subprocess | `scripts/verify_phase473_evidence.py`; `scripts/release_evidence.py` | strong role-match |
| `scripts/release_manifest.py` | utility/model | transform, file-I/O | `scripts/build_lambda_dist.py` | exact data-flow |
| `scripts/dependency_policy.py` | utility/policy | batch, transform | `scripts/verify_phase473_evidence.py` | role-match |
| `scripts/phase474_pytest_guard.py` | pytest plugin | event-driven, file-I/O | `scripts/phase473_pytest_guard.py` | exact |
| `schemas/release/release-manifest-v1.schema.json` | schema | validation | Phase 473 manifest constants/validators | role-match |
| `schemas/release/gate-receipt-v1.schema.json` | schema | validation | Phase 473 receipt validation | role-match |
| `schemas/release/dependency-exceptions-v1.schema.json` | schema | validation | Phase 473 closed obligation maps | role-match |
| `scripts/build_lambda_dist.py` | build utility | file-I/O, batch | existing implementation (extend) | exact |
| `scripts/verify_phase473_evidence.py` | evidence verifier | Git/file-I/O | existing implementation (extend) | exact |
| `pyproject.toml`, `uv.lock`, `requirements.txt` | config/locks | dependency resolution | current dev extras + frozen export chain | exact |
| `tests/conftest.py` | test config | event-driven | `tests/security/conftest.py`, `scripts/phase473_pytest_guard.py` | strong |
| `tests/test_release_gate.py`, `tests/test_deterministic_gate.py` | tests | subprocess/batch | `tests/test_phase473_evidence_verifier.py` | strong |
| `tests/test_quality_gate_policy.py`, `tests/test_dependency_policy.py` | tests | transform | `tests/test_phase473_evidence_verifier.py` parametrized tamper cases | strong |
| `tests/test_release_manifest.py` | tests | file-I/O, transform | `tests/test_lambda_dist_build.py`, `tests/test_phase473_evidence_verifier.py` | strong |
| `tests/test_delivery_workflow_contract.py` | workflow contract test | transform | mobile workflow contract tests; Phase 473 verifier tests | partial |
| `tests/test_phase473_evidence_verifier.py` | test | Git/file-I/O | existing test (extend) | exact |
| `.github/workflows/deploy.yml` | workflow | event-driven | frontend CI job dependency shape; current deploy as negative fixture | partial |
| frontend `scripts/verify-release.mjs` | utility/orchestrator | batch, subprocess | backend `scripts/release_gate.py`; frontend `scripts/vite.mjs` | partial |
| frontend release Playwright config/project | test config | request-response | frontend `playwright.config.ts` | exact role-match |
| frontend `public/runtime-config.json.template` + schema | config/schema | file-I/O, request-response | current deploy `VITE_*` block (contract source only) | partial |
| frontend release/runtime/contract tests | tests | request-response | `tests/e2e/helpers.ts` and existing `*.spec.ts` | strong |
| frontend `package.json`, `package-lock.json` | config/lock | dependency resolution | existing scripts and `npm ci` workflow | exact |
| frontend `.github/workflows/frontend-ci.yml`, `.github/workflows/deploy.yml` | workflow | event-driven | existing workflows (split verify/build/promote) | partial |
| frontend `playwright.config.ts`, Vite config/env and selected API/auth adapters | config/provider boundary | request-response | current config and adapters | role-match |
| infra `stacks/release_delivery_stack.py` | CDK stack | event-driven/provisioning | `stacks/storage_stack.py`, `api_stack.py`, `frontend_stack.py` | strong composite |
| infra `tests/test_release_topology.py` | CDK assertion test | transform | no local infra tests; backend contract tests | no exact analog |
| infra `app.py`, `api_stack.py`, `frontend_stack.py`, `storage_stack.py`, `lambda_dist_guard.py` | config/stacks | provisioning | existing implementations (extend/harden) | exact |
| infra `.github/workflows/deploy.yml`, `pyproject.toml`, `uv.lock` | workflow/config | event-driven/dependency | current workflow (harden) | exact |

## Pattern Assignments

### Authoritative gate and receipts

**Apply to:** `scripts/release_gate.py`, frontend `scripts/verify-release.mjs`, all three workflows, gate tests.

Copy the checked-in CLI convention from `scripts/release_evidence.py:19-40,75-110`: JSON is loaded as a typed top-level object, output uses `json.dumps(..., indent=2, sort_keys=True) + "\n"`, subcommands return `0` only for pass and `2` for policy failure, and `main(argv)` is testable without a process spawn.

```python
def command_validate(args: argparse.Namespace) -> int:
    bundle = load_json(args.input)
    if not isinstance(bundle, dict):
        raise SystemExit("release evidence input must be a JSON object")
    result = release_evidence_service.validate_release_bundle(bundle)
    write_json(result, args.output)
    return 0 if result["status"] == "passed" else 2
```

Copy receipt identity from `tests/test_phase473_evidence_verifier.py:109-163`: record exact `argv`, start/end, exit code, candidate SHA, clean HEAD before/after, artifact byte counts and SHA-256, closed outcome counts, and privacy/policy result. Canonicalize release JSON with `sort_keys=True, separators=(",", ":")`, then SHA-256 the encoded bytes. Workflows must only checkout exact refs, bootstrap pinned tools, call this entry point, upload its outputs, and express `needs:` dependencies; they must not restate Ruff/mypy/pytest/audit logic.

Formal backend verification must create two distinct temporary environments and run the same command twice with only clock identity changed: Python 3.12, `uv sync --frozen --extra dev`, seed `4740718`, clocks `2026-07-01T12:00:00Z` and `2035-01-15T12:00:00Z`. Dependency acquisition occurs before denial. Test subprocesses clear AWS credential variables, set `AWS_EC2_METADATA_DISABLED=true`, point AWS config/credential files at nonexistent paths, and deny sockets except an explicit loopback allowlist.

### Strict pytest outcome guard

**Apply to:** `scripts/phase474_pytest_guard.py`, `tests/conftest.py`, deterministic tests.

Copy the Phase 473 plugin’s session-finalization contract (`scripts/phase473_pytest_guard.py:74-97`): stable node ordering, explicit totals for passed/failed/error/skipped/xfail/xpass, sorted indented JSON, parent directory creation, and forced `ExitCode.TESTS_FAILED` if any non-pass category is nonzero.

```python
counts = {"total": len(nodes), "passed": ..., "failed": ..., "error": ...,
          "skipped": ..., "xfail": ..., "xpass": ...}
path.write_text(json.dumps({"schema_version": SCHEMA_VERSION,
    "nodes": nodes, "counts": counts}, sort_keys=True, indent=2) + "\n")
if any(counts[k] for k in ("failed", "error", "skipped", "xfail", "xpass")):
    session.exitstatus = ExitCode.TESTS_FAILED
```

Keep `tests/conftest.py` as the central integration point (currently imports shared security fixtures at lines 1-3). Add autouse clock/socket/AWS isolation there or register the guard through pytest config; do not patch individual tests. Gate tests should assert identical collection hashes across both runs, exact clock/seed/runtime/lock identities, and AWS/socket failures.

### Release manifest, artifact and schema

**Apply to:** `scripts/release_manifest.py`, three JSON schemas, `scripts/build_lambda_dist.py`, `tests/test_release_manifest.py`.

Copy hashing and stable traversal from `scripts/build_lambda_dist.py:37-65`: stream file bytes, sort tree paths, delimit relative path and digest with NULs. Copy Git identity checks from lines 68-88 and stable content hashing from lines 109-122. Extend the manifest pattern at lines 125-156 to include exact backend/frontend/infra commits, dirty=false, both lock hashes, source-tree identities, artifact byte digests, runtime/platform, config digest, verification run IDs and every gate result.

```python
encoded = json.dumps(stable_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
digest = hashlib.sha256(encoded).hexdigest()
```

Extend `zip_dist` (`build_lambda_dist.py:255-260`) by constructing normalized `ZipInfo` records (fixed timestamp, mode, sorted paths) rather than `archive.write`, then hash final ZIP bytes. Verify `requirements.txt` is byte-equivalent to a fresh `uv export --locked --no-dev --no-emit-project`; reject drift. Keep runtime identity constants (`python3.12`, `manylinux2014_aarch64`, `arm64`) and handler inventory (`build_lambda_dist.py:18-29,91-106`). Staging and production receive these exact artifact digests; neither rebuilds.

Schemas must be closed (`additionalProperties: false`), versioned, require every identity/gate field, constrain SHA-256/SHA formats, and distinguish `PASS`, `FAIL`, and exact `NOT RUN` obligations. Tests must mutate one field/byte at a time and prove rejection.

### Dependency and typing policy

**Apply to:** dependency script/schema, `pyproject.toml`, locks/export, quality/dependency tests, frontend package files.

Parse `pip-audit` and `npm audit --package-lock-only --json`; never scrape prose. Default blockers: Critical/High, plus production-reachable Medium. Exception records must require exact ecosystem, package, advisory, affected version, reachability evidence, owner, expiry, and upgrade/removal target; reject expired, wildcarded, or advisory/package/version drift. Audit backend `uv.lock`/verified export and frontend root `package-lock.json`; explicitly exclude `mobile/`.

Mypy invocation covers the full repository and first targets zero. For missing provider types use maintained stubs or narrow project-owned `Protocol` adapters. Tests must reject new global `ignore_missing_imports`, module exclusions, broad `Any`, or blanket ignores. Preserve the repository’s typed boundary style seen in `build_lambda_dist.py` (`Path`, `dict[str, Any]`, explicit return types, domain exception `DistVerificationError`) while narrowing provider-facing values with Protocols.

### Phase 473 publication verification

**Apply to:** `scripts/verify_phase473_evidence.py`, its test.

Reuse its immutable fixed-path and closed obligation declarations (`verify_phase473_evidence.py:18-42`). Extend verification to accept an explicit publication commit and read each required file with `git show <commit>:<path>` / `git cat-file`, compare blob OIDs and bytes to the signed manifest, and never assume current checkout HEAD is the publication. Copy the tamper matrix style from `tests/test_phase473_evidence_verifier.py:166-180`; add a later metadata-only HEAD case, missing blob, wrong publication commit, and manifest/blob mismatch.

### Web verification and Playwright

**Apply to:** frontend verifier, release config/project, runtime config, contract tests, workflows.

Preserve clean Web commands from `package.json:6-14` (`npm ci`, lint, `tsc -b`/Vite build, Playwright), but add one `verify:release` entry called by the backend authority. Reuse Playwright structure from `playwright.config.ts:3-37` (bounded timeout, baseURL, single Chromium project), but the release project must use real staging services, `retries: 0`, machine-readable JSON/JUnit output, no demo API/MSW/interception, and fail on skip/flaky/retry. Existing `retries: CI ? 1 : 0` and demo webServer env are explicitly not release evidence.

Reuse typed helpers (`tests/e2e/helpers.ts:1-26`) for role login/navigation shape, replacing demo credentials with CI-managed staging identities. Runtime config must move production-varying values currently embedded by frontend deploy (`deploy.yml:32-54`) to a reviewed, schema-validated, non-secret runtime document. Build generic bytes once; bind config digest separately in the release manifest. Tests cover schema rejection, config/artifact digest binding, real `/health` plus core browser smoke, API/auth adapter contract, and zero skipped/flaky outcomes.

Frontend CI’s current `npm ci` → lint → build (`frontend-ci.yml:13-29`) is the bootstrap analog. The current deploy’s `aws s3 sync --delete` and production rebuild (`deploy.yml:26-74`) are negative patterns: replace with immutable release prefixes/object versions and a bounded served pointer.

### CI gating, promotion and rollback

**Apply to:** all workflow files and `tests/test_delivery_workflow_contract.py`.

Replace backend’s direct main deployment (`.github/workflows/deploy.yml:11-75`) with jobs: exact checkout/bootstrap → canonical gate → immutable build/upload → staging pointer updates → staging smoke → protected `production` environment owner approval → promote exact object/version IDs → production smoke → compensation on failure. Credentials and artifacts must not be available to downstream deploy jobs unless all required `needs` passed. Pin every third-party action to a reviewed full commit SHA.

Persist transaction state before mutation: release manifest ID, previous/target Lambda versions and aliases, previous/target Web pointer object/version, request/run IDs. On smoke failure restore both halves, then verify both restored identities and retain failure, action, and result receipts. A rollback-only emergency input may select a previously verified manifest; it may not build new bytes. Until separate production mutation authority exists, production promote/smoke is recorded exactly as `NOT RUN`, while staging and rollback exercises are executable.

Contract tests should parse YAML and intentionally fail tests, Ruff, mypy, dependency policy, provenance, and artifact digest in turn, proving no deploy job can receive credentials/artifacts. Also assert protected environment usage, self-approval-compatible single owner policy, smoke-to-rollback dependency, no mutable `latest`, no branch-as-release-ID, and no direct function/S3-root overwrite.

### CDK release topology

**Apply to:** new release stack, existing infra stacks/app/guard, infra workflow/locks, topology tests.

Compose existing patterns:

- `storage_stack.py:59-77`: private encrypted, SSL-enforced, versioned Object Lock bucket with retained removal policy. Extend retention: production/approval/smoke/rollback long-term; failed/staging at least 90 days; current and latest known-good never lifecycle-expired.
- `api_stack.py:42-57,86-94`: one verified asset shared by both Python 3.12 arm64 functions. Add published `Version` resources and environment aliases; promotion changes aliases only.
- `frontend_stack.py:27-36,55-92`: private OAC bucket and CloudFront SPA behavior. Replace destructive bucket policy with immutable release prefixes plus a bounded pointer/config origin design.
- `app.py:16-60`: context-derived environment, shared tags, explicit resource passing between stacks. Instantiate the release stack and pass existing functions/buckets/distribution rather than discovering names manually.

Delete the release-capable bypass in `lambda_dist_guard.py:33-39`; retain its fail-fast subprocess verification and validated 64-character asset hash (`lines 41-78`). Split OIDC roles by verify/upload, staging promotion, production promotion, and rollback; constrain repository/ref/environment trust and least-privilege resources. Infra workflow must use `uv sync --frozen`, exact backend/infra refs from the candidate manifest, full action SHAs, and the canonical gate rather than rebuilding an unrelated backend HEAD.

`tests/test_release_topology.py` has no local exact analog; use CDK assertions to check Lambda aliases/versions, Object Lock + versioning + retention, no public buckets, immutable prefixes/pointer resources, role trust/resource boundaries, rollback permissions, and absence of the stale-dist bypass. Preserve existing resource logical IDs/imports where replacement would destroy production resources.

## Shared Fail-Closed Patterns

- **Closed inventories:** Phase 473 constants and receipt node sets show the pattern: enumerate required gates/files/obligations; unknown, missing, duplicate, skipped, or broadened entries fail.
- **Evidence privacy:** record IDs, hashes, counts, commands, versions and status; never credentials, tokens, raw private payloads, or browser storage.
- **Errors:** distinguish malformed input (`SystemExit`/schema failure), policy failure (structured receipt + exit 2), and unexpected execution failure (nonzero with captured stdout/stderr digest).
- **Tests:** load scripts as modules via `importlib.util` (`test_phase473_evidence_verifier.py:84-91`), use `tmp_path`, synthesize minimal receipts, and parameterize single-axis tampering.
- **Identity:** exact commit/blob/object/version/digest only. Branch names, tags, `latest`, mutable S3 roots, and rebuilt artifacts are never release identity.

## No Exact Analog Found

| File/Capability | Reason / planner instruction |
|---|---|
| infra `tests/test_release_topology.py` | Infra currently has no tests; use AWS CDK assertion APIs and the listed resource constructs. |
| cross-repository promotion coordinator | No existing atomic coordinator; implement explicit transaction + compensation receipts, not an atomicity claim. |
| frontend runtime-config schema/pointer | Current Web build embeds `VITE_*`; use the manifest/schema conventions and CDK S3/CloudFront patterns. |
| dependency exception evaluator | No current advisory policy engine; implement from the closed-schema/fail-closed verifier pattern. |

## Metadata

**Strong analogs read:** backend release evidence CLI, Lambda builder, Phase 473 verifier/plugin/tests; backend/frontend workflows; frontend Playwright/package/helpers; infra app, API/frontend/storage stacks, Lambda guard and workflow.
**Important negative analogs:** direct Lambda code updates, frontend production rebuild plus `s3 sync --delete`, mutable action tags, CI Playwright retries, and `ALLOW_STALE_LAMBDA_DIST`.
