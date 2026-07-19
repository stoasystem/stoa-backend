# Phase 474: Deterministic Verification And Gated Delivery - Research

**Researched:** 2026-07-18
**Domain:** Hermetic cross-repository verification, immutable release provenance, staged AWS delivery, and compensating rollback
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

> Provenance for every item in this section: copied verbatim from `474-CONTEXT.md`. [VERIFIED: 474-CONTEXT.md]

### Locked Decisions

### Deterministic Verification

- **D-01:** Local formal verification and CI must invoke one authoritative entry point. CI may orchestrate it but may not reimplement a different gate.
- **D-02:** Every formal run creates a fresh Python 3.12 environment from the committed `uv.lock` in frozen mode. A developer `.venv` is convenient but cannot produce release evidence.
- **D-03:** The formal complete-suite gate requires `skip=0`, `xfail=0`, and `xpass=0`. External checks that are not available must be represented by a separate, exact `NOT RUN` obligation and never counted as passing.
- **D-04:** The complete suite runs twice in separate fresh environments: once at a standard fixed time and once at an explicit future fixed time. Both runs deny ambient AWS credentials and all non-allowlisted network access, and record the Python version, `uv.lock` hash, test collection identity, deterministic seed, clock identity, exit status, and outcome counts.

### CI, Promotion, And Rollback Authority

- **D-05:** A `main` candidate that passes every required gate builds one immutable release set and deploys it automatically to staging. Production promotion requires manual approval of the exact staging-verified release set.
- **D-06:** STOA is currently a one-person team. The project owner is the sole production approver and may approve their own candidate through the protected production environment. Do not invent a two-person or no-self-approval policy until the team changes.
- **D-07:** No emergency path may deploy new or rebuilt code without the complete gate and staging smoke. An emergency may immediately roll back to a previously verified artifact; a hotfix still follows the normal path.
- **D-08:** A failed production smoke stops promotion and automatically returns the Lambda alias and Web release pointer to the previous verified release set. The failed release IDs, request/run IDs, health evidence, rollback action, and rollback result remain durable evidence.

### Typing And Dependency Risk

- **D-09:** Phase 474 must first attempt to reduce full-repository mypy errors to zero. It must not begin by accepting the audit's old error count as debt. Only after a concrete repair attempt may irreducible errors, root causes, and remediation costs be returned to the owner for an explicit temporary-baseline decision. Executors cannot silently freeze errors or weaken typing with broad `Any`, exclusions, or ignores.
- **D-10:** Missing third-party types are addressed with trustworthy maintained stubs or a narrow project-owned `Protocol`/typed adapter at the boundary. Global `ignore_missing_imports`, broad `Any`, and exclusion of provider integration modules are forbidden shortcuts.
- **D-11:** Critical and High dependency advisories block release by default; a production-reachable Medium advisory also blocks. A temporary exception is allowed only when a fix is unavailable or the path is proven unreachable, and records the exact package/advisory/version, reachability evidence, owner, expiry, and upgrade/removal target. Expired or broadened exceptions fail the gate.
- **D-12:** Dependency gates cover the backend lock and `/Users/zhdeng/stoa-frontend/package-lock.json`. They do not audit or gate the Expo `mobile/` skeleton for v9.0.

### Immutable Cross-Repository Release Evidence

- **D-13:** One cross-repository release manifest identifies a candidate by exact backend commit, frontend commit, both lockfile hashes, source-tree identities, backend and frontend artifact digests, target runtime/platform, verification run IDs, and gate results. Neither repository's branch name or mutable `latest` pointer is release identity.
- **D-14:** Backend and frontend use build once, promote unchanged. Staging and production consume byte-identical artifacts. Environment differences enter only through reviewed runtime configuration; production may not rebuild a frontend bundle or Lambda package.
- **D-15:** Production manifests, artifacts, approvals, smoke evidence, and rollback evidence are retained long term. Failed and staging-only candidates remain available for at least 90 days. The current and most recent known-good rollback artifacts are never automatically deleted.
- **D-16:** Every CI/gate change runs automated intentional-failure scenarios for tests, Ruff, mypy, dependency policy, provenance, and artifact tampering and proves the deploy job cannot receive an artifact. Initial activation and every structural gate redesign also perform a controlled non-production failure exercise with retained CI run IDs.

### v9.0 Web-First Product Correction

- **D-17:** v9.0 exists to complete the Web App and backend for early real testing: close every known audit defect, test-discovered defect, Phase 473 follow-up, and launch-blocking defect reachable through any retained production Web route. “Fix all bugs” is not an unbounded claim about undiscovered theoretical defects, but known Web/backend defects cannot be silently deferred.
- **D-18:** The current Phase 477/478 native-mobile roadmap is invalid for the product direction and must be replaced with Web foundation/contract convergence plus complete student, parent, teacher, and admin/operator journeys. A bounded executable route inventory must prove every retained production Web route works against real services or is intentionally removed/disabled. All later phases and the final reality gate use Web/browser evidence rather than Expo, iOS, Android, or device evidence.

### the agent's Discretion

- Exact fixed timestamps, deterministic seed representation, safe network allowlist needed only for dependency acquisition, evidence file formats, manifest schema versioning, CI job names, and artifact storage implementation.
- Exact mypy repair sequencing and typed-adapter structure, provided the executor first pursues full zero and does not create an unapproved baseline.
- Exact staging smoke endpoints and bounded automatic rollback timing, provided they cover the core Web/backend release and preserve the immutable release identity.

### Deferred Ideas (OUT OF SCOPE)

- Native Expo/iOS/Android client development, dependency repair, native builds, device E2E, push/offline client behavior, and app distribution are deferred until the Web App has launched for testing and reached stable operation. They require a future milestone based on Web production evidence, not automatic continuation of the current Phase 477/478 text.
</user_constraints>

<phase_requirements>
## Phase Requirements

> Requirement text is copied from `.planning/REQUIREMENTS.md`. [VERIFIED: REQUIREMENTS.md]

| ID | Description | Research Support |
|----|-------------|------------------|
| V9QUAL-01 | Local formal verification and CI invoke one authoritative cross-repository entry point that creates a fresh Python 3.12 environment from committed `uv.lock` in frozen mode and a clean Web install from committed `package-lock.json`; neither CI nor a developer environment may substitute a weaker gate. | Canonical orchestrator, bootstrap contract, and CI dependency graph below. |
| V9QUAL-02 | The complete Python suite passes twice in separate fresh environments, once at a fixed standard time and once at an explicit future fixed time, with deterministic seed/collection identity, ambient AWS credentials denied, non-allowlisted network denied, and exactly zero skip, xfail, or xpass outcomes; unavailable external checks are separate exact `NOT RUN` obligations and never count as passing. | Two-run matrix, strict pytest accounting, ambient-denial fixtures, and receipt schema below. |
| V9QUAL-03 | The actual Web repository passes locked install, ESLint, TypeScript production build, dependency checks, focused backend/OpenAPI contract checks, and Playwright browser suites through the same formal gate; production-critical acceptance is not satisfied by demo login or route-intercepted APIs alone. | Web gate baseline, real-service acceptance boundary, Playwright policy, and runtime-config design below. |
| V9QUAL-04 | Ruff has zero errors and a full-repository mypy-zero repair attempt is completed before any temporary baseline is proposed; only an explicit owner decision may accept documented irreducible errors, and broad `Any`, exclusions, ignores, or global missing-import suppression are forbidden shortcuts. | Exact mypy command, measured baseline, repair sequence, and semantic weakening guard below. |
| V9QUAL-05 | Backend and Web lockfiles have no unaccepted release-blocking advisory: Critical/High block by default and production-reachable Medium also blocks; every temporary exception records exact package/advisory/version, reachability evidence, owner, expiry, and upgrade/removal target. | Lockfile-native audit commands, current red baseline, and exception-ledger schema below. |
| V9QUAL-06 | Phase 474 implements the minimum versioned cross-repository release infrastructure—staging/production release roles, immutable artifact/evidence storage, Lambda versions and aliases, Web release prefixes/pointers or an equivalent atomic mechanism, protected environments, and rollback authority—then one manifest binds exact backend/Web/infra commits, lock/source identities, runtimes, verification runs, and artifact digests. Artifacts build once, differ only through reviewed runtime configuration, and deploy unchanged to staging; the gate permits unchanged production promotion only after protected owner approval and staging smoke, prohibits bypass, and automatically restores the previously verified set after failed production smoke. Phase 474 proves promotion and rollback semantics through staging plus a controlled non-production failure exercise; the owner's policy selection does not authorize a real production mutation. Actual production promotion/smoke occurs only under later explicit operational approval, otherwise its evidence is exact `NOT RUN` and Phase 474 remains fully enforceable. Emergencies may only restore a previously verified set and hotfixes follow the normal gate. Production evidence, when generated, is retained long term; failed/staging candidates are retained at least 90 days and current/known-good rollback sets indefinitely; every gate change runs intentional-failure/tamper tests. | Minimum CDK topology, immutable manifest, promotion transaction, compensation, environment controls, retention, and failure-injection plan below. |
| V9QUAL-07 | Phase 473 evidence publication can be reverified from a later clean metadata HEAD by selecting the explicit candidate and its single direct publication commit, reading the four publication artifacts from immutable Git blobs, and proving the current HEAD descends from that publication without changing those blobs. | Explicit candidate/publication Git-blob algorithm and history tests below. |
</phase_requirements>

## Summary

Phase 474 should introduce one backend-owned, dependency-light release command that is the only authoritative path used locally and by CI. It must verify exact backend, frontend, and infrastructure commits; create fresh locked environments; emit content-addressed receipts; build one backend/Web artifact set; and drive staging, approval, promotion, smoke, and compensating rollback. The existing workflows instead deploy independently and directly from `main`, while the existing AWS CDK lacks Lambda aliases, isolated staging/production release roles, and an immutable Web release pointer. [VERIFIED: codebase grep across stoa-backend, stoa-frontend, and stoa-infra]

The current baseline is intentionally red, not close to release-ready: the existing Python 3.14 environment reports `2009 passed` and Ruff zero, but that is not a fresh Python 3.12 frozen run; the proposed full-repository mypy command reports 435 errors across 113 files; backend dependency audit reports nine advisories in five runtime packages; frontend Playwright reports two failures plus one skip; and frontend dependency audit reports two High, one Moderate, and one Low advisory. These findings must become explicit repair tasks before gate activation; the planner must not disguise them with a baseline, skip, retry, or exception. [VERIFIED: local diagnostic commands on 2026-07-18]

Observed checkout identities are planning evidence only, not release evidence: backend `b2b5281c777f29469a262ec82d9f7de8fd974319`, Web `0d0df6fa2a505bca372c5ddfc23e9a1fe3031387`, and infra `a4d5cfeb22163d6d7f8f70016a0f98be4732a7a9`; backend `uv.lock` SHA-256 is `f9f3de7dc008d791eeb29f154abf699ede27d47a95fe4bd6c1661f81b76c600b`, Web `package-lock.json` is `7549be39bf202adaff1f9dd056ba863707b95811b53191b552bbf826296e17e0`, and infra `uv.lock` is `77605e95bd0bd4e609fd68732855ad596a6c06ef054717646673611b9f581e9e`. The formal gate must recompute these from detached clean checkouts and reject dirt or ref movement. [VERIFIED: `git rev-parse HEAD` and `shasum -a 256` on 2026-07-18]

The delivery design must treat backend and Web promotion as a durable transaction with compensation, because changing Lambda aliases and a Web pointer cannot be one atomic AWS operation. Production mutation is outside this phase's present authority: implement and test the topology and exercise staging rollback, but record production promotion/smoke as exact `NOT RUN` unless separately approved. [VERIFIED: 474-CONTEXT.md and REQUIREMENTS.md] [CITED: https://docs.aws.amazon.com/lambda/latest/dg/configuring-alias-routing.html]

**Primary recommendation:** implement a canonical `scripts/release_gate.py` command plus versioned JSON schemas, backed by CDK-owned immutable storage, Lambda versions/aliases, Web release prefixes/pointer, scoped OIDC roles, and protected GitHub environments; make all three repository workflows thin callers of this command and fail closed on any missing or mismatched evidence. [VERIFIED: codebase architecture inspection] [CITED: https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Gate orchestration and evidence validation | CI / release control plane | Repository scripts | CI owns credentials and job dependencies; a checked-in script keeps local and CI semantics identical. [VERIFIED: D-01] |
| Fresh Python verification | Backend runtime | CI | Tests execute in Python 3.12 environments constructed from `uv.lock`; CI only provisions and invokes. [VERIFIED: D-02] |
| Locked Web verification | Frontend build/browser tier | CI | `npm ci`, TypeScript/Vite, contract checks, and Playwright operate on the real Web repository. [VERIFIED: stoa-frontend package.json and D-12] |
| Cross-repository candidate identity | Release control plane | Git repositories | The control plane joins exact Git and lock identities without treating a branch as identity. [VERIFIED: D-13] |
| Backend artifact and Lambda routing | API / Backend + AWS Lambda | CI release role | Lambda versions hold immutable code/config snapshots and aliases route to published versions. [CITED: https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html] |
| Web artifact and release pointer | CDN / Static storage | CI release role | Immutable prefixes retain bytes; one bounded pointer change selects the active release. [VERIFIED: D-14/D-15] |
| Production approval | GitHub protected environment | Project owner | Environment approval gates secret/OIDC availability while allowing the sole owner to approve. [CITED: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments] |
| Promotion and rollback transaction | CI / release control plane | Lambda + S3/CloudFront | The coordinator records previous/target state and compensates both service pointers after smoke failure. [VERIFIED: D-08] |
| Artifact/evidence retention | S3 Object Lock storage tier | Lifecycle policy | Versioned WORM retention supplies durable, non-overwritable evidence. [CITED: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html] |
| Phase 473 publication verification | Git object database | Repository script | Explicit commit/blob reads remain valid from a later metadata HEAD without checkout mutation. [VERIFIED: V9QUAL-07 and existing verifier inspection] |

## Project Constraints (from AGENTS.md)

No repository `AGENTS.md` exists, so there are no additional project directives to copy. No project-local `.codex/skills` or `.agents/skills` directory exists. [VERIFIED: filesystem inspection]

## Standard Stack

### Core

| Library / service | Version | Purpose | Why Standard |
|-------------------|---------|---------|--------------|
| Python | 3.12.13 locally; require `3.12.x` and record exact patch | Authoritative backend gate/runtime family | The project declares Python `>=3.12`, Lambda packaging targets 3.12, and D-02 locks formal verification to 3.12. [VERIFIED: pyproject.toml, build_lambda_dist.py, environment probe] |
| uv | lock tool at `0.11.16`; pin the gate bootstrap to a reviewed exact version | Frozen environment creation and lock validation | `uv sync --frozen` avoids lock mutation; `--python` selects the interpreter. [CITED: https://docs.astral.sh/uv/concepts/projects/sync/] [CITED: https://docs.astral.sh/uv/concepts/python-versions/] |
| pytest | 9.0.3 | Backend suite and gate self-tests | Already locked and used by 2,009 passing backend tests in the current environment. [VERIFIED: uv.lock and local pytest run] |
| Ruff | 0.15.14 | Python lint gate | Already locked; the current repository is clean under `ruff check .`. [VERIFIED: uv.lock and local Ruff run] |
| mypy | 2.1.0 | Full repository static type gate | Already locked; Phase 474 must define one exact invocation and pursue zero. [VERIFIED: uv.lock and local mypy diagnostics] |
| Node.js + npm | Pin Node 20 patch in CI; `package-lock.json` lockfileVersion 3 | Web build/test environment and exact install | Existing Web workflows use Node 20 and `npm ci` installs from the lock without rewriting it. [VERIFIED: frontend workflows/package-lock.json] [CITED: https://docs.npmjs.com/cli/commands/npm-ci/] |
| Playwright Test | 1.60.0 | Browser acceptance | Already locked and provides retries/flaky classification plus machine-readable reporters. [VERIFIED: frontend package-lock.json] [CITED: https://playwright.dev/docs/test-retries] |
| AWS CDK | `aws-cdk-lib` 2.257.0 | Versioned release infrastructure | Already locked in stoa-infra and owns current Lambda, S3, CloudFront, and evidence resources. [VERIFIED: stoa-infra/uv.lock and app.py] |
| GitHub Actions environments + AWS OIDC | GitHub-hosted service | Protected approval and scoped credentials | Environment rules can require approval before environment secrets are available; AWS recommends constraining OIDC trust conditions. [CITED: https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments] [CITED: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws] |
| S3 versioning + Object Lock | AWS service | Immutable release artifacts and receipts | Object Lock provides WORM retention on versioned objects. [CITED: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `time-machine` | 3.2.0 | Suite-wide fixed wall clock | Autouse fixture for standard and future runs with `tick=False`; it patches standard-library date/time APIs. [VERIFIED: PyPI registry + slopcheck] [CITED: https://time-machine.readthedocs.io/en/latest/usage.html] |
| `pytest-socket` | 0.8.0 | Deny ambient Python socket access | Formal Python test process, allowing only explicitly documented loopback endpoints if a test genuinely requires them. [VERIFIED: PyPI registry + slopcheck] [CITED: https://pypi.org/project/pytest-socket/] |
| `pip-audit` | 2.10.1 | Backend lock vulnerability audit | Run against the committed hashed export/locked project and parse JSON into STOA policy. [VERIFIED: PyPI registry + slopcheck] [CITED: https://github.com/pypa/pip-audit] |
| `boto3-stubs` | 1.43.16, matching locked `boto3` | Maintained AWS SDK types | Add only the needed service extras, or use narrow project `Protocol`s when the provider boundary is smaller. [VERIFIED: PyPI registry + stoa-backend uv.lock + slopcheck] [CITED: https://boto3-stubs.readthedocs.io/en/stable/] |
| `types-python-jose` | 3.5.0.20260408 | Maintained jose stubs | Use to eliminate verified `python-jose` missing-import typing errors. [VERIFIED: PyPI registry + slopcheck] [CITED: https://typing.python.org/en/latest/spec/distributing.html] |
| Python standard library `hashlib`, `json`, `subprocess`, `pathlib` | Python 3.12 | Gate orchestration, canonical receipts, digests, subprocess isolation | Keeps the authoritative gate auditable and avoids a second workflow framework. [VERIFIED: Python standard library] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Checked-in Python gate | Duplicate shell/YAML logic | Rejected because it creates divergent local/CI semantics and violates D-01. [VERIFIED: D-01] |
| S3 Object Lock evidence store | GitHub Actions artifacts only | Actions supports per-artifact retention, but repository retention is bounded and does not meet indefinite known-good/production retention by itself. [CITED: https://docs.github.com/en/actions/tutorials/store-and-share-data] |
| Immutable Web prefixes + pointer | `aws s3 sync --delete` to the bucket root | Existing direct deploy destroys release identity and makes bounded rollback unreliable. [VERIFIED: stoa-frontend deploy workflow inspection] |
| Lambda published versions + aliases | Direct `update-function-code` on the function | Existing direct updates lack a stable version identity and rollback pointer. [VERIFIED: backend deploy workflow] [CITED: https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html] |

**Installation:** lock tools in the backend `dev` optional extra, then regenerate and verify the hashed runtime export. Do not install them ad hoc in CI. [VERIFIED: current pyproject dependency layout]

```bash
uv add --optional dev 'pip-audit==2.10.1' 'time-machine==3.2.0' \
  'pytest-socket==0.8.0' 'boto3-stubs==1.43.16' \
  'types-python-jose==3.5.0.20260408'
uv lock --check
uv export --format requirements-txt --no-dev --no-emit-project --locked > /tmp/requirements.generated.txt
cmp /tmp/requirements.generated.txt requirements.txt
```

The executor must resolve and pin every third-party GitHub Action to a full reviewed commit SHA; a tag is mutable while a full commit SHA is immutable. [CITED: https://docs.github.com/en/actions/reference/security/secure-use]

## Package Legitimacy Audit

The audit used `slopcheck 0.6.1`; that release does not support the requested `--json` option, so its human-readable `[OK]` verdicts were retained. Versions, first-release dates, and source repositories were cross-checked through official PyPI metadata. [VERIFIED: slopcheck CLI + PyPI registry]

| Package | Registry | Age / first release | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|---------------------|-----------|-------------|-----------|-------------|
| `uv` | PyPI | 2024-02-15 | Registry API does not expose downloads | `github.com/astral-sh/uv` | OK | Approved; bootstrap tool, pin exact reviewed version. [VERIFIED: PyPI registry + slopcheck] |
| `pip-audit` | PyPI | 2021-09-16 | Registry API does not expose downloads | `github.com/pypa/pip-audit` | OK | Approved. [VERIFIED: PyPI registry + slopcheck] |
| `time-machine` | PyPI | 2020-05-04 | Registry API does not expose downloads | `github.com/adamchainz/time-machine` | OK | Approved. [VERIFIED: PyPI registry + slopcheck] |
| `pytest-socket` | PyPI | 2017-06-01 | Registry API does not expose downloads | `github.com/miketheman/pytest-socket` | OK | Approved. [VERIFIED: PyPI registry + slopcheck] |
| `boto3-stubs` | PyPI | 2019-11-10 | Registry API does not expose downloads | `github.com/youtype/mypy_boto3_builder` | OK | Approved at the version matching boto3. [VERIFIED: PyPI registry + slopcheck] |
| `types-python-jose` | PyPI | 2022-04-12 | Registry API does not expose downloads | `github.com/python/typeshed` | OK | Approved. [VERIFIED: PyPI registry + slopcheck] |
| `pytest` | PyPI | Established project; locked version 9.0.3 | Registry API does not expose downloads | `github.com/pytest-dev/pytest` | OK | Already approved/locked. [VERIFIED: uv.lock + PyPI registry + slopcheck] |

**Packages removed due to slopcheck [SLOP] verdict:** none. [VERIFIED: slopcheck output]

**Packages flagged as suspicious [SUS]:** none. [VERIFIED: slopcheck output]

## Architecture Patterns

### System Architecture Diagram

```text
exact backend SHA + exact frontend SHA + exact infra SHA
                         |
                         v
              canonical release_gate.py
                         |
          +--------------+---------------+
          |                              |
          v                              v
 backend fresh Python 3.12 x2       frontend clean checkout
 fixed/future clocks                npm ci + lint + build
 no AWS / no network                audit + contract + Playwright
 Ruff + mypy + audit                no fail/skip/flaky
          |                              |
          +------------ all green -------+
                         |
                         v
             build once, hash bytes
       Lambda ZIP + generic Web artifact + reviewed configs
                         |
                         v
       signed-by-digest release manifest + receipts
                         |
                         v
       immutable S3 artifact/evidence object versions
                         |
                         v
       staging Lambda aliases + staging Web pointer
                         |
                  staging smoke
                   /          \
              fail/            \pass
                 v              v
       durable failure      protected production environment
       evidence only            owner approval
                                  |
                            explicit authority?
                              /          \
                      no -> NOT RUN       yes
                                           |
                         promote exact Lambda versions + Web object version
                                           |
                                     production smoke
                                      /          \
                                  pass            fail
                                   |               |
                            commit success     restore both previous
                                               verified pointers and
                                               retain rollback evidence
```

This is a compensation workflow, not a claim of atomic cross-service mutation. [VERIFIED: D-08 and AWS service boundary inspection]

### Recommended Project Structure

```text
stoa-backend/
├── scripts/
│   ├── release_gate.py                 # sole local/CI command surface
│   ├── release_manifest.py             # canonical schema, hashing, validation
│   ├── dependency_policy.py            # advisory + exact exception evaluation
│   └── verify_phase473_evidence.py      # explicit candidate/publication verification
├── schemas/release/
│   ├── release-manifest-v1.schema.json
│   ├── gate-receipt-v1.schema.json
│   └── dependency-exceptions-v1.schema.json
└── tests/
    ├── test_release_gate.py
    ├── test_release_manifest.py
    ├── test_dependency_policy.py
    └── test_delivery_workflow_contract.py

stoa-frontend/
├── scripts/verify-release.mjs           # Web checks called by canonical gate
├── public/runtime-config.json.template  # reviewed config contract, not secrets
└── tests/release/                        # real-service and pointer/config tests

stoa-infra/
├── stacks/release_delivery_stack.py     # roles, aliases, stores, prefixes/pointers
└── tests/test_release_topology.py        # CDK assertions and policy tests
```

Paths are prescriptive planner targets; preserve existing repository conventions where a nearby module already owns the responsibility. [VERIFIED: three-repository structure inspection]

### Exact Files Likely Modified

| Repository | Existing files to change | New files likely needed | Purpose |
|------------|--------------------------|-------------------------|---------|
| backend | `.github/workflows/deploy.yml`, `pyproject.toml`, `uv.lock`, `requirements.txt`, `tests/conftest.py`, `scripts/build_lambda_dist.py`, `scripts/verify_phase473_evidence.py`, `tests/test_phase473_evidence_verifier.py` | `scripts/release_gate.py`, `scripts/release_manifest.py`, `scripts/dependency_policy.py`, `scripts/phase474_pytest_guard.py`, release JSON schemas, and the Wave 0 tests listed below | Replace direct deployment, create the single gate, close deterministic test/type/dependency/provenance gaps, and extend later-HEAD verification. [VERIFIED: backend inspection] |
| Web | `.github/workflows/frontend-ci.yml`, `.github/workflows/deploy.yml`, `package.json`, `package-lock.json`, `playwright.config.ts`, Vite environment/config modules, and production API/auth adapters selected by the focused OpenAPI check | `scripts/verify-release.mjs`, a release-only Playwright config/project, runtime-config schema/template, and release/contract tests | Make CI a thin common-gate caller, remove build-at-production, build generic bytes once, and separate real-service acceptance from demo/intercepted UI tests. [VERIFIED: Web inspection] |
| infra | `app.py`, `stacks/api_stack.py`, `stacks/frontend_stack.py`, `stacks/storage_stack.py`, `stacks/lambda_dist_guard.py`, `.github/workflows/deploy.yml`, `pyproject.toml`, `uv.lock` | `stacks/release_delivery_stack.py` and `tests/test_release_topology.py` (or equivalent existing-stack extensions) | Add environment-specific roles/stacks, aliases, immutable stores/prefixes, served Web pointer, policy denials, retention, and rollback authority; remove the stale-dist bypass from release-capable paths. [VERIFIED: infra inspection] |

Do not let the backend plan silently absorb uncommitted edits to the sibling repositories: the phase needs coordinated commits in all three repositories, and the release manifest must bind their exact SHAs. [VERIFIED: D-13 and three-repository layout]

### Pattern 1: Canonical Gate With Content-Addressed Receipts

**What:** one Python CLI owns ordering, exact commands, exit interpretation, and evidence. Workflow YAML checks out exact refs, bootstraps a pinned toolchain, and calls it; it must not duplicate commands. Each subcommand writes canonical JSON containing input SHAs/hashes, command argv, tool versions, counts, timestamps/clock ID, result, and SHA-256 of the receipt. [VERIFIED: D-01/D-04/D-13]

**When to use:** every formal local run, pull-request validation, `main` candidate, staging deployment, production promotion, rollback, or later additive product gate. [VERIFIED: phase boundary]

```python
# Source: Python 3.12 standard library; schema fields derive from D-04/D-13.
payload = {
    "schema": "stoa.release.gate-receipt.v1",
    "candidate": exact_candidate_triplet,
    "command": argv,
    "runtime": runtime_identity,
    "lock_sha256": lock_sha256,
    "collection_sha256": collection_sha256,
    "seed": 4740718,
    "clock": "2026-07-01T12:00:00Z",
    "status": "PASS",
    "outcomes": outcomes,
}
encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
receipt_sha256 = hashlib.sha256(encoded).hexdigest()
```

Use `2026-07-01T12:00:00Z`, `2035-01-15T12:00:00Z`, and integer seed `4740718` as the phase defaults; record them rather than relying on ambient environment. These values are selected under the agent's discretion and have no business semantics. [VERIFIED: D-04 discretion]

### Pattern 2: Fresh, Hermetic Two-Run Python Matrix

Acquire dependencies through the documented package-host allowlist before entering the test boundary. Create two different temporary `UV_PROJECT_ENVIRONMENT` paths and run `uv sync --frozen --python 3.12 --extra dev`, then execute identical `python -m pytest` commands with only the clock changed inside a Linux network namespace or OCI container with networking disabled. `pytest-socket` remains defense in depth, not the primary boundary, because a Python plugin cannot constrain arbitrary child processes. Clear AWS variables, set `AWS_EC2_METADATA_DISABLED=true`, point shared credentials/config to nonexistent files, mount no credential directories or sockets, freeze time, and use a deterministic hash/test seed. An intentional self-test must prove both direct Python networking and a spawned network client fail. [CITED: https://docs.astral.sh/uv/concepts/projects/sync/] [CITED: https://pypi.org/project/pytest-socket/] [CITED: https://time-machine.readthedocs.io/en/latest/usage.html]

Extend the existing `phase473_pytest_guard` accounting pattern: collect sorted node IDs, hash the collection, record setup/call/teardown reports, and fail on any skipped, xfailed, xpassed, error, or failed outcome. Compare collection hashes between runs. [VERIFIED: scripts/phase473_pytest_guard.py inspection]

The current backend command with `PYTHONPATH=.` reports `2009 passed`; without it, collection fails importing `scripts`. Install/sync the project and invoke `python -m pytest` from the exact checkout rather than making `PYTHONPATH=.` an undocumented CI special case. [VERIFIED: local pytest diagnostics]

### Pattern 3: Exact Web Gate With Real-Service Boundary

Run `npm ci`, `npm run lint`, a new explicit `npm run typecheck` (`tsc -b`), a production `npm run build`, dependency policy, focused OpenAPI/backend contract checks, and Playwright through the same orchestrator, with a separate receipt for each boundary. The current `build` script embeds typecheck before Vite, but a standalone script is needed so an intentional type failure can prove that exact gate independently. Configure zero retries for the release gate or add `--fail-on-flaky-tests`; parse JSON/JUnit output and fail on failed, flaky, skipped, or fixme tests. Playwright documents that tests passing only on retry are “flaky,” and skipped/fixme annotations do not execute normally. [VERIFIED: frontend package.json/tsconfig inspection] [CITED: https://playwright.dev/docs/test-retries] [CITED: https://playwright.dev/docs/test-annotations]

The current Web baseline is `2 failed, 1 skipped, 69 passed`; its config enables demo APIs and mock checkout, and 94 `page.route` calls are present across 11 specs. Keep isolated UI tests, but require a bounded production-critical suite against the staging API with no demo login and no API route interception. Rewrite the conditional notification skip into explicit projects/parameters so every claimed obligation runs. [VERIFIED: frontend Playwright run and codebase grep]

Generate canonical sorted backend OpenAPI JSON from the exact verified backend commit in the fresh environment, hash it, and pass that immutable file to the Web gate. A project-owned focused checker should map each release-critical adapter operation/path/method plus request/response field aliases, enum values, required fields, structured error envelope, and idempotency header to that schema; it must import/inspect the real adapter modules or their explicit checked inventory, not search source strings. Phase 474 establishes this additive adapter boundary and fails drift; Phase 477 may broaden/fix the full product contract but cannot replace or bypass this check. [VERIFIED: current backend `app.openapi()` support, missing Web OpenAPI tooling, V9QUAL-03, and Phase 477 roadmap boundary]

### Pattern 4: Build Once, Promote Exact Bytes

The backend builder should derive runtime dependencies from the frozen lock, verify that the committed hashed `requirements.txt` exactly equals a fresh locked export, normalize archive entry order/timestamps/modes, hash the final ZIP bytes, and perform a Python 3.12 arm64-compatible import/handler smoke in CI. The current builder targets manylinux2014/aarch64 and records useful source/handler metadata, but its checked-in `dist` is stale and ZIP member timestamps are not normalized. [VERIFIED: scripts/build_lambda_dist.py and dist validation]

The Web build currently reads `VITE_*` environment values at compile time, so staging and production builds cannot be byte-identical. Replace release-varying compile-time values with a reviewed non-secret runtime JSON contract. Precompute a non-circular release ID from the exact source/lock identities, build once with asset URLs under immutable `releases/<release-id>/`, and bind the resulting whole-artifact digest afterward. Make the actually served stable `index.html` (or a CloudFront Function/KVS mapping if already justified) the atomic release pointer. Upload immutable assets first, then copy the already-built byte-identical index/pointer into the stable served key with versioning and digest preconditions; rollback restores the exact previous S3 VersionId/bytes and performs only the bounded HTML/pointer invalidation. A passive JSON pointer that CloudFront never resolves is not sufficient. Do not run `s3 sync --delete` against a shared root. [VERIFIED: frontend env.ts/amplify.ts/api.ts, deploy workflow, D-13/D-14]

### Pattern 5: Published Lambda Versions and Aliases

Publish each verified function version with `CodeSha256` and `RevisionId` preconditions, then point separate staging and production aliases at published versions. API integrations and permissions must reference aliases, not the unqualified function or `$LATEST`. AWS documents that published versions are immutable and aliases point to versions. [CITED: https://docs.aws.amazon.com/lambda/latest/api/API_PublishVersion.html] [CITED: https://docs.aws.amazon.com/lambda/latest/dg/configuring-alias-routing.html]

Environment configuration may produce distinct Lambda version numbers, but the manifest must prove both versions use the same code digest. Promotion roles may read immutable artifacts, change aliases/pointers, write evidence, and invalidate bounded CDN paths; they may not build, overwrite artifact keys, or update unqualified function code. [VERIFIED: D-14 and least-privilege design]

### Pattern 6: Durable Promotion Transaction and Compensation

Before mutation, persist a transaction with release ID, previous and target Lambda version/alias state, previous and target Web pointer object version/digest, request/run ID, and `PREPARED` state. Update both pointers, run bounded smoke, then record `COMMITTED`; on any failure, restore both previous verified values and record each compensation result. Keep promotion and rollback in the same protected job so its scoped credentials remain available on failure. [VERIFIED: D-08]

Never seed “known good” from an unverified live deployment. The first rollback target must be an artifact that passed the new gate and staging exercise; any later production state requires explicit operational approval and evidence. [VERIFIED: D-07 and current lack of release evidence]

### Pattern 7: Later-HEAD Git-Blob Verification

Change the Phase 473 verifier to require `--candidate` and `--publication`. Verify `publication^ == candidate`, the publication changes exactly the four evidence paths, and current `HEAD` descends from publication. Read every artifact with `git show <publication>:<path>` and compare its blob OID/bytes with `HEAD:<path>`; never read the worktree as publication truth. [VERIFIED: V9QUAL-07 and current verifier inspection]

Tests must accept later metadata-only descendants and reject a mutated artifact, unrelated/sideways ancestry, a merge publication, a non-direct candidate/publication pair, or an extra path in the publication commit. [VERIFIED: V9QUAL-07]

### Dependency Policy

Run backend audit from the authoritative lock/export with hashes and frontend audit from `package-lock.json`; parse machine-readable results rather than scraping prose. The current backend audit reports nine vulnerability records across `cryptography`, `ecdsa`, `pydantic-settings`, `python-multipart`, and `starlette`; the current Web audit reports two High, one Moderate, and one Low result, including production-reachable `form-data`. Both gates are red before repairs. [VERIFIED: `pip-audit --require-hashes -r requirements.txt` and `npm audit --package-lock-only --json` on 2026-07-18]

Because pip-audit does not provide a uniform severity for all advisory sources, make every backend runtime advisory blocking unless an exact exception proves the D-11 conditions. For Web, block all Critical/High and production-reachable Medium results. The exception ledger must bind package, advisory, installed version, lock hash, dependency scope, severity/reachability evidence, owner, expiry timestamp, and upgrade/removal target; wildcard IDs, version ranges, or expired entries fail. [VERIFIED: D-11 and observed audit output]

### Mypy Closure Sequence

Define one configuration and command before repairs:

```bash
MYPYPATH=src:tests python -m mypy --explicit-package-bases src/stoa scripts tests
```

This measured command currently reports `435 errors in 113 files (checked 221 source files)`, with the largest categories including `arg-type` (150), `import-untyped` (81), `index` (44), and `union-attr` (30). Different plausible commands produced materially different totals, so the exact scope is part of the gate contract. [VERIFIED: local mypy diagnostics]

Repair in this order: (1) import/package-root resolution and maintained stubs, (2) shared DTOs and narrow provider Protocols/adapters, (3) service/repository/router cascades, (4) scripts and tests, then (5) the full command. Add a semantic guard that rejects new/broadened `Any`, `type: ignore`, `exclude`, `follow_imports=skip`, or `ignore_missing_imports`. Only after this concrete zero attempt may the owner receive an exact residual report and decide whether to authorize a temporary baseline. [VERIFIED: D-09/D-10 and measured error topology]

### Anti-Patterns to Avoid

- **Green-by-omission:** never translate skip/xfail/xpass, unavailable external systems, a missing browser, or missing AWS credentials into PASS. [VERIFIED: D-03]
- **CI-only semantics:** never place authoritative commands or result interpretation solely in workflow YAML. [VERIFIED: D-01]
- **Ambient developer evidence:** never reuse `.venv`, `node_modules`, ignored `dist`, or the current uncredentialed machine state as release evidence. [VERIFIED: D-02 and filesystem inspection]
- **Rebuild on promotion:** never rerun Vite or Lambda packaging after staging verification. [VERIFIED: D-14]
- **Mutable identity:** never identify release bytes by branch, tag, `latest`, S3 root contents, or an unqualified Lambda. [VERIFIED: D-13]
- **Split-brain success:** never record promotion success before both pointers and smoke are durable; compensate both after either side fails. [VERIFIED: D-08]
- **Bypass flags:** remove `ALLOW_STALE_LAMBDA_DIST=1` from any release-capable path; no emergency new-code bypass exists. [VERIFIED: stoa-infra dist_guard.py and D-07]
- **Unpinned supply chain:** never install `uv` ad hoc or reference third-party Actions by mutable tags in the release workflow. [VERIFIED: current backend workflow] [CITED: https://docs.github.com/en/actions/reference/security/secure-use]
- **Fake Web acceptance:** production-critical acceptance cannot depend on demo users or `page.route` API interception. [VERIFIED: V9QUAL-03]
- **Typing suppression as repair:** no global ignores, broad `Any`, provider exclusions, or silent old-error baseline. [VERIFIED: D-09/D-10]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dependency resolution | Custom requirements merger | Frozen `uv.lock`, `uv sync --frozen`, and verified `uv export` | Lock semantics and hash resolution already exist. [CITED: https://docs.astral.sh/uv/concepts/projects/sync/] |
| Browser runner/retry accounting | Custom browser automation | Playwright Test reporters with zero retries or fail-on-flaky | Playwright already classifies failed/flaky/skipped outcomes. [CITED: https://playwright.dev/docs/test-retries] |
| Time patching | Ad hoc monkeypatches per test | `time-machine` autouse fixture | It patches standard-library time/date APIs consistently. [CITED: https://time-machine.readthedocs.io/en/latest/usage.html] |
| Network isolation | Patch individual SDK calls or rely only on a pytest plugin | OS/container `network=none` boundary plus `pytest-socket` and AWS env/metadata denial | The OS boundary also constrains spawned processes; the plugin catches in-process mistakes with clearer diagnostics. [CITED: https://pypi.org/project/pytest-socket/] |
| Vulnerability database/client | Custom CVE fetcher | `pip-audit` and `npm audit`, wrapped only by project policy | Official ecosystem tools provide lock-aware machine output. [CITED: https://github.com/pypa/pip-audit] [CITED: https://docs.npmjs.com/cli/v7/commands/npm-audit/] |
| Cryptographic primitives | Custom signing/encryption | SHA-256 from standard library/AWS digests; AWS-managed encryption and Object Lock | The gate needs integrity binding, not novel cryptography. [VERIFIED: D-13] |
| Lambda routing | Copy ZIPs between functions | Published versions and aliases | AWS supplies immutable versions and controlled pointers. [CITED: https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html] |
| Evidence immutability | Append-only naming convention alone | Versioned S3 Object Lock bucket | Naming does not prevent overwrite/deletion; WORM controls do. [CITED: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html] |
| Cross-service “atomicity” | Pretend two AWS mutations are one transaction | Durable transaction record + idempotent compensation | Lambda and Web pointers are separate service mutations. [VERIFIED: architecture inspection] |
| Third-party SDK typing | Broad `Any` wrappers | Maintained stubs or narrow `Protocol` adapters | Preserves checked provider boundaries without suppressing the repository. [CITED: https://typing.python.org/en/latest/spec/distributing.html] |

**Key insight:** reuse ecosystem determinism and AWS immutability primitives, while hand-writing only STOA's small policy/orchestration layer and schemas. [VERIFIED: phase architecture]

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | Live Lambda versions/aliases, S3 objects/version IDs, CloudFront state, and CloudFormation resources could not be inventoried because no AWS credentials are available. The local backend `dist` fails its own freshness checks; no `lambda.zip` exists. [VERIFIED: AWS CLI and builder diagnostics] | Add a read-only live-state inventory checkpoint before any CDK deployment. Treat current live state as unverified, not known-good. No application-data migration is indicated; infrastructure imports/replacements must be resolved from inventory. |
| Live service config | GitHub reports zero environments in backend/frontend/infra; branch protection queries returned 404; current workflows independently deploy direct to production. AWS role/alias live config is `NOT RUN`. [VERIFIED: GitHub API and workflow inspection] | Owner/admin creates staging/production environments, reviewer/branch rules, OIDC trust, and cross-repo credential; executor records AWS inventory as PASS or exact NOT RUN. |
| OS-registered state | No launchd/systemd/pm2/task registrations are part of the release path. Docker CLI exists but its daemon is unavailable. [VERIFIED: repository search and environment probe] | None for OS registration. Provision Docker/Podman or an equivalent Linux network namespace before local formal evidence; run arm64 artifact boot smoke in the same capable isolated runner. |
| Secrets/env vars | GitHub API exposes no repository Actions secret or variable names. Existing workflows rely on OIDC role ARNs; local AWS credentials are absent. Cross-repo check dispatch/write authority is not configured. [VERIFIED: GitHub API, workflows, and AWS CLI] | Create environment-scoped OIDC roles and a least-privilege GitHub App/fine-grained credential for cross-repo status/dispatch if needed; never pass credentials to verification jobs. |
| Build artifacts | Backend `dist` is stale, Web `dist` is ignored, and local `.venv`, `node_modules`, infra `.venv`, and `cdk.out` are ignored developer artifacts. [VERIFIED: filesystem and git-ignore inspection] | Delete/rebuild only inside the formal build task after a green gate; publish new content-addressed artifacts. Never promote any existing local artifact. |

The canonical post-edit question—what remains outside Git—therefore has two unresolved live systems: AWS resource state and owner-controlled GitHub environment/branch policy. The plan needs explicit inventory/configuration checkpoints rather than assumptions. [VERIFIED: runtime probes]

## Common Pitfalls

### Pitfall 1: A Gate That Is Deterministic Only on CI

**What goes wrong:** local and CI commands drift, or a warm `.venv` hides import/resolution failures. [VERIFIED: current PYTHONPATH-sensitive pytest behavior]

**Why it happens:** workflow YAML becomes the implementation and developer environments are reused. [VERIFIED: current workflow structure]

**How to avoid:** one checked-in command, fresh temp environments, exact tool versions, and receipts that include argv/runtime/lock/collection identity. [VERIFIED: D-01/D-04]

**Warning signs:** different pass counts, undocumented `PYTHONPATH`, CI-only flags, or receipts without collection hashes. [VERIFIED: current diagnostics]

### Pitfall 2: Clock Freeze and Network Denial That Miss Paths

**What goes wrong:** direct imports cache real time functions, subprocesses escape pytest socket hooks, or boto credential discovery reaches metadata. [CITED: https://time-machine.readthedocs.io/en/latest/usage.html] [VERIFIED: Python process boundaries]

**Why it happens:** patching app functions instead of the process boundary and conflating dependency acquisition with test execution. [VERIFIED: test architecture]

**How to avoid:** acquire first; run tests inside a credential-free OS/container network namespace; use `time-machine`, pytest socket denial, metadata disablement, nonexistent AWS config paths, and intentional direct/subprocess self-tests that fail if real clock/network/AWS access succeeds. [VERIFIED: D-04]

**Warning signs:** tests pass only with live network, AWS “no credentials” latency, or different collections between clock runs. [VERIFIED: deterministic-gate semantics]

### Pitfall 3: Calling a Retried Playwright Test Green

**What goes wrong:** a test fails first, passes on retry, and release proceeds. [CITED: https://playwright.dev/docs/test-retries]

**Why it happens:** default report/exit status is consumed without flaky-count policy. [CITED: https://playwright.dev/docs/test-retries]

**How to avoid:** release profile uses zero retries or `--fail-on-flaky-tests`, parses machine output, and rejects skip/fixme/flaky. [CITED: https://playwright.dev/docs/test-cli]

**Warning signs:** nonzero retry config, HTML-only evidence, conditional `test.skip`, or missing result-count assertions. [VERIFIED: current frontend config]

### Pitfall 4: “Build Once” While Vite Embeds Environment Values

**What goes wrong:** staging and production bundles have different bytes even though the pipeline claims promotion. [VERIFIED: frontend `import.meta.env` use]

**Why it happens:** Vite replaces `VITE_*` at build time. [VERIFIED: frontend build design]

**How to avoid:** move release-varying non-secret settings into reviewed runtime JSON and bind both artifact digest and config digest in the manifest. [VERIFIED: D-14]

**Warning signs:** production job runs `npm run build`, accepts `VITE_*`, or uploads `dist` without checking the staging digest. [VERIFIED: current frontend deploy workflow]

### Pitfall 5: Rollback Only One Half of the Release

**What goes wrong:** Web and API point at different release sets after failed smoke. [VERIFIED: two-repository delivery topology]

**Why it happens:** independent workflows and no transaction record. [VERIFIED: current workflows]

**How to avoid:** persist previous/target pair before mutation; compensate both pointers; verify both after rollback; retain evidence even if compensation partially fails. [VERIFIED: D-08]

**Warning signs:** separate manual rollback commands, mutable “latest,” or evidence with only one service identity. [VERIFIED: D-13]

### Pitfall 6: CDK Replaces Existing Production Resources

**What goes wrong:** adding environment-specific stacks changes hard-coded names or replaces bucket/distribution/function resources. [VERIFIED: current stoa-infra hard-coded production resources]

**Why it happens:** designing desired state before inventorying deployed CloudFormation and physical IDs. [VERIFIED: AWS credentials unavailable]

**How to avoid:** first run read-only AWS/CloudFormation inventory and `cdk diff`; import/adopt resources or isolate additive alias/role/pointer resources; require explicit approval for any replacement. [VERIFIED: safe migration practice]

**Warning signs:** `Replacement: true`, bucket deletion policy, hard-coded function name collision, or unknown old role ownership. [VERIFIED: current CDK inspection]

### Pitfall 7: Dependency Exceptions That Quietly Broaden

**What goes wrong:** package-level ignores suppress new advisory IDs or fixed versions indefinitely. [VERIFIED: D-11]

**Why it happens:** free-form allowlists lack lock hash, exact version, reachability, and expiry. [VERIFIED: D-11]

**How to avoid:** exact schema validation and negative tests for changed lock, new advisory, wildcard, missing evidence, and expired timestamp. [VERIFIED: D-16]

**Warning signs:** `|| true`, package-name-only allowlist, no UTC expiry, or exceptions not copied into the release manifest. [VERIFIED: fail-closed policy]

## Code Examples

### Exact Fresh Environment Per Clock

```bash
# Source: https://docs.astral.sh/uv/concepts/projects/sync/
export UV_PROJECT_ENVIRONMENT="$RUN_TEMP/venv"
uv sync --frozen --python 3.12 --extra dev
"$UV_PROJECT_ENVIRONMENT/bin/python" -m pytest \
  -p scripts.phase474_pytest_guard \
  --disable-socket \
  --stoa-fixed-clock '2026-07-01T12:00:00Z' \
  --stoa-seed 4740718
```

The orchestrator supplies a validated explicit temporary path and must not reuse the variable across the two runs. [VERIFIED: D-02/D-04]

### Lambda Version Preconditions

```python
# Source: https://docs.aws.amazon.com/lambda/latest/api/API_PublishVersion.html
published = lambda_client.publish_version(
    FunctionName=function_name,
    CodeSha256=expected_aws_code_sha256,
    RevisionId=observed_revision_id,
    Description=f"stoa release {release_id}",
)
assert published["CodeSha256"] == expected_aws_code_sha256
```

Persist the returned version and code digest before changing either alias. [VERIFIED: D-13/D-14]

### Explicit Git Publication Reads

```python
# Source: Git object model and V9QUAL-07.
def git_bytes(repo: Path, commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout

assert rev_parse(f"{publication}^") == candidate
assert is_ancestor(publication, "HEAD")
publication_bytes = git_bytes(repo, publication, evidence_path)
head_bytes = git_bytes(repo, "HEAD", evidence_path)
assert publication_bytes == head_bytes
```

Use `git diff-tree --no-commit-id --name-only -r <publication>` to enforce the exact four-path publication boundary. [VERIFIED: V9QUAL-07]

### Exact Dependency Exception Shape

```json
{
  "schema": "stoa.dependency-exceptions.v1",
  "package": "example-package",
  "advisory": "GHSA-EXACT-ID",
  "installed_version": "1.2.3",
  "lock_sha256": "64-lowercase-hex",
  "scope": "runtime",
  "reachability": {"status": "unreachable", "evidence": "receipt-sha256"},
  "owner": "project-owner",
  "expires_at": "2026-08-01T00:00:00Z",
  "target": "upgrade to 1.2.4 when released"
}
```

The gate validates every field exactly and fails when time, lock, package version, advisory, or reachability evidence changes. [VERIFIED: D-11]

## Recommended Plan Decomposition

1. **Wave 0 — Gate contracts and red self-tests:** freeze command names, JSON schemas, exact mypy scope, test result accounting, failure-injection matrix, and test infrastructure. [VERIFIED: D-01/D-16]
2. **Wave 1 — Backend deterministic verification:** fresh Python 3.12 x2, fixed clocks, network/AWS denial, strict pytest receipts, Ruff, Phase 473 verifier fix. [VERIFIED: V9QUAL-01/02/07]
3. **Wave 2 — Quality closure:** mypy zero repair attempt plus backend/frontend dependency remediation and exact exception policy. [VERIFIED: V9QUAL-04/05]
4. **Wave 3 — Web release gate:** runtime-config refactor, locked build, contract checks, Playwright repair and real-service staging acceptance. [VERIFIED: V9QUAL-03/D-14]
5. **Wave 4 — Minimum infrastructure:** read-only live inventory, CDK assertions, immutable stores, aliases, Web prefixes/pointer, staging/prod roles, protected environments, cross-repo authority. [VERIFIED: V9QUAL-06]
6. **Wave 5 — Build/promotion coordinator:** deterministic artifact bytes, cross-repo manifest, staging auto-deploy/smoke, approval boundary, exact production NOT RUN behavior, compensation. [VERIFIED: V9QUAL-06]
7. **Wave 6 — Adversarial activation:** intentional failures for test/Ruff/mypy/dependency/provenance/tamper, prove deploy receives neither artifacts nor credentials, then controlled staging failure/rollback exercise with retained IDs. [VERIFIED: D-16]

Do not parallelize waves that would allow infrastructure/promotion to be declared complete before gate contracts and red-baseline repairs are closed. [VERIFIED: dependency structure]

The activation order inside Wave 5/6 is strict: synth/policy tests -> provision isolated staging substrate -> upload content-addressed artifacts -> automatic staging promotion -> staging smoke -> injected nonproduction smoke failure -> automatic two-pointer rollback -> verify restored backend/Web digests -> configure the protected production job. The production job must stop after policy/manifest validation and emit exact `NOT RUN` obligations unless a later, separate operational authorization explicitly permits mutation. [VERIFIED: D-05/D-08/D-16 and V9QUAL-06]

### Verification Command Matrix

| Boundary | Command the plan should converge on | Required interpretation |
|----------|-------------------------------------|-------------------------|
| Canonical local/CI | `python scripts/release_gate.py verify --backend-ref <sha> --frontend-ref <sha> --infra-ref <sha>` | Sole authoritative entry; clean detached inputs only; emits receipts, not deployment credentials. [VERIFIED: D-01/D-13] |
| Backend lock | `uv lock --check` then fresh `uv sync --frozen --python 3.12 --extra dev` in each unique temp environment | Lock must not change; a warm `.venv` cannot issue evidence. [CITED: https://docs.astral.sh/uv/concepts/projects/sync/] |
| Backend suite | fresh-env `python -m pytest -p scripts.phase474_pytest_guard ...` twice | Same collection hash/seed, fixed and future clocks, zero skip/xfail/xpass/fail/error, AWS/network denial assertions present. [VERIFIED: D-03/D-04] |
| Python quality | fresh-env `python -m ruff check src tests scripts --no-cache` and `MYPYPATH=src:tests python -m mypy --explicit-package-bases src/stoa scripts tests` | Ruff zero; mypy zero pursued before any owner checkpoint; no weakening flags. [VERIFIED: V9QUAL-04] |
| Backend dependencies | generate/verify locked runtime input, then machine-readable `pip-audit` policy evaluation | Any advisory blocks unless one exact unexpired D-11 exception matches. [VERIFIED: D-11] |
| Web | clean checkout `npm ci`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm audit --package-lock-only --json`, focused OpenAPI adapter check, release Playwright project | No lock mutation; distinct lint/type/build receipts; zero failed/flaky/skipped release obligations; critical acceptance cannot use demo login or intercepted APIs. [VERIFIED: V9QUAL-03] |
| Lambda artifact | `python scripts/build_lambda_dist.py --zip <path>` plus manifest/ZIP digest verification and Linux arm64 handler boot smoke | Build once from lock-bound dependencies; normalized bytes and both handlers proven. [VERIFIED: existing builder + V9QUAL-06] |
| Infra | infra locked sync, `cdk synth`, `cdk diff`, and CDK assertion tests | No replacement/destruction accepted without resolved inventory; aliases, roles, stores, pointer, retention, rollback permissions present. [VERIFIED: V9QUAL-06] |
| Phase 473 publication | `python scripts/verify_phase473_evidence.py verify-publication --candidate <sha> --publication <sha>` from later clean HEAD | Direct child, exact four paths, immutable blob equality, valid ancestry. [VERIFIED: V9QUAL-07] |
| Staging/rollback | canonical deploy subcommand on the bound manifest, then smoke and injected-failure exercise | Automatic staging is mandatory; both pointers restore exact known-good digests without rebuild. [VERIFIED: V9QUAL-06/D-16] |
| Production | protected job validating the same manifest/artifacts | No mutation absent later explicit authorization; approval/deploy/smoke/rollback each record exact `NOT RUN`. [VERIFIED: V9QUAL-06] |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Mutable Lambda function code | Published immutable versions selected by aliases | AWS current documented model | Enables exact version identity and pointer rollback. [CITED: https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html] |
| Environment-specific frontend rebuild | Generic immutable artifact + reviewed runtime config/pointer | Phase 474 decision D-14 | Makes staging/prod artifact bytes provably identical. [VERIFIED: D-14] |
| Action tags such as `@v6` | Full commit SHA pins | GitHub current security guidance | Reduces action supply-chain tag mutation risk. [CITED: https://docs.github.com/en/actions/reference/security/secure-use] |
| Pass after retry | Explicit flaky result that blocks release | Playwright current runner semantics | Prevents intermittent failures from silently passing. [CITED: https://playwright.dev/docs/test-retries] |
| Mutable evidence objects | S3 versioning + Object Lock WORM | AWS current documented model | Meets durable artifact/evidence retention and tamper resistance. [CITED: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html] |
| Worktree-relative evidence verification | Explicit immutable commit/blob verification | V9QUAL-07 | Metadata-only descendants remain verifiable without weakening publication binding. [VERIFIED: V9QUAL-07] |

**Deprecated/outdated:**

- Direct `main` push to `aws lambda update-function-code` is incompatible with the phase gate and must be removed from release authority. [VERIFIED: current backend deploy workflow and D-05]
- Frontend `s3 sync --delete` to a production root is incompatible with immutable prefixes and rollback retention. [VERIFIED: current frontend deploy workflow and D-14/D-15]
- CDK `ALLOW_STALE_LAMBDA_DIST=1` is not an allowed emergency release path. [VERIFIED: stoa-infra dist_guard.py and D-07]
- Current demo/mocked Playwright suites are useful UI tests but cannot alone satisfy production-critical acceptance. [VERIFIED: V9QUAL-03 and frontend test inspection]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | None. Recommendations are derived from locked decisions, repository/runtime observations, or cited official documentation. | — | — |

## Open Questions (RESOLVED)

1. **RESOLVED — What exact AWS resources and CloudFormation stacks are live?**
   - What we know: the repository CDK uses hard-coded production names and no alias/pointer topology. [VERIFIED: stoa-infra inspection]
   - What's unclear: live physical IDs, deployed templates, roles, bucket lock state, aliases, and safe import/replacement boundaries because credentials are unavailable. [VERIFIED: AWS CLI probe]
   - Selected answer: Plan 474-33 performs the blocking, read-only AWS/CloudFormation inventory and retained `cdk diff` before Plan 474-34 may apply the staging-only substrate. Unknown resources, replacements, destructive changes, or unavailable read authority block staging; production is always exact `NOT RUN` in Phase 474. [RESOLVED: Plans 474-33/34, D-03]
2. **RESOLVED — Who has GitHub admin authority to create protected environments and cross-repo credentials?**
   - What we know: all three repositories currently report zero environments; the current token cannot establish admin configuration. [VERIFIED: GitHub API]
   - What's unclear: whether the executor or only the owner can configure environment reviewers, deployment branches, OIDC subjects, and a GitHub App/fine-grained token. [VERIFIED: current token capability]
   - Selected answer: Plan 474-79 configures and verifies protected environments; Plan 474-80 is the blocking owner verification after both GitHub and staging evidence exist. The sole project owner is the required production reviewer and self-approval is allowed; no second reviewer or prevent-self-review policy is invented, and the checkpoint grants no production mutation authority. [RESOLVED: Plans 474-79/80, D-06] [CITED: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments]
3. **RESOLVED — Can the initial mypy-zero attempt complete within the phase?**
   - What we know: the defined full command reports 435 errors across 113 files, with concentrated import/type-cascade categories. [VERIFIED: local mypy run]
   - What's unclear: the irreducible residual and repair cost until stubs/package roots/shared DTOs are repaired. [VERIFIED: D-09 sequencing]
   - Selected answer: Plans 474-07 through 474-21 plus split Plans 474-39 through 474-71 perform the coherent-domain repairs, and Plan 474-22 accepts only repository-wide mypy zero. Any residual remains release-blocking and is returned to the owner after execution; there is no preplanned baseline/disposition checkpoint and no historical or invented baseline is eligible. [RESOLVED: Plans 474-07..22/39..71, D-09]
4. **RESOLVED — Which endpoints form bounded staging smoke?**
   - What we know: smoke must cover the core Web/backend set and exact release identity. [VERIFIED: agent discretion in CONTEXT.md]
   - What's unclear: the stable authenticated fixture/user and minimal teacher/admin route set after later Web route inventory work. [VERIFIED: current phase boundary]
   - Selected answer: Phase 474 smoke is bounded to public health/release identity, one authenticated API, and one real Web boot/API call in Plans 474-25 and 474-35. Later Web route journeys extend the same closed gate registry and cannot replace or bypass these obligations. [RESOLVED: Plans 474-25/35, D-01/D-17]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.12 | Formal backend gate | ✓ | 3.12.13 | None needed. [VERIFIED: environment probe] |
| uv | Frozen environment | ✓ | 0.11.16 local; registry 0.11.29 | Pin an exact reviewed version in CI rather than ambient latest. [VERIFIED: CLI + PyPI registry] |
| Node.js/npm | Web gate | ✓ | Node 26.0.0 / npm 11.12.1 locally | Formal gate uses a pinned Node 20 patch matching current workflows until deliberately upgraded. [VERIFIED: environment and workflow probe] |
| Playwright browser runtime | Web E2E | ✓ | Playwright 1.60.0 suite executed | CI installs exact locked browser dependencies. [VERIFIED: frontend run/package-lock] |
| AWS CLI | Deployment/inventory | Partial | 2.34.58; no credentials | Exact `NOT RUN` for live operations until environment-scoped OIDC/operator credentials exist. [VERIFIED: AWS CLI probe] |
| AWS CDK CLI/library | Infrastructure synth/diff | ✓ | CLI 2.1125.0; library 2.257.0 | Use locked infra environment for synthesis. [VERIFIED: CLI and stoa-infra uv.lock] |
| GitHub CLI/API | Environment/workflow inspection | Partial | gh 2.96.0; non-admin token | Owner/admin checkpoint for protected configuration. [VERIFIED: GitHub API probe] |
| Docker/Podman or Linux network namespace | Formal network-denied runs and arm64 Lambda smoke | Partial | Docker CLI 29.6.1; daemon unavailable | A capable isolated runner is required before local formal evidence can be issued; CI may provide it, but cannot turn an unsupported local run into PASS. [VERIFIED: Docker probe and D-03/D-04] |
| `act` | Local Actions emulation | ✗ | — | Not required; test the checked-in command and workflow contract directly. [VERIFIED: environment probe] |
| `cosign` / `syft` | Optional signing/SBOM | ✗ | — | Not required by locked decisions; SHA-256 manifest and ecosystem audits are sufficient phase scope. [VERIFIED: environment probe and phase requirements] |

**Missing dependencies with no fallback:** AWS credentials/admin authority block live inventory/configuration/deployment. Production mutation remains unauthorized independently of credentials. [VERIFIED: environment probe and V9QUAL-06]

Staging deployment/smoke and the controlled nonproduction failed-promotion/two-pointer rollback are not optional external checks: they are Phase 474 completion evidence. If staging OIDC/admin authority cannot be supplied, the plan may continue through local/CDK work but the phase remains blocked; exact `NOT RUN` is permitted for production mutation, not as a substitute for the required staging exercise. [VERIFIED: V9QUAL-06, D-05, D-16]

**Missing dependencies with fallback:** GitHub Actions emulation is replaced by script/workflow-contract tests. The absent local isolation runtime is not a silent fallback: local formal evidence remains exact `NOT RUN` until Docker/Podman or an equivalent network namespace is available, while CI must still run the complete isolated gate. [VERIFIED: environment probe and D-03/D-04]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Backend pytest 9.0.3; frontend Playwright 1.60.0 plus existing ESLint/TypeScript; infra pytest/CDK assertions to be added. [VERIFIED: lockfiles] |
| Config file | `pyproject.toml`, frontend `playwright.config.ts`, and Wave 0 infra pytest config. [VERIFIED: repository inspection] |
| Quick run command | `python -m pytest tests/test_release_gate.py tests/test_release_manifest.py tests/test_dependency_policy.py tests/test_delivery_workflow_contract.py -q` [VERIFIED: recommended Wave 0 contract] |
| Full suite command | `python scripts/release_gate.py verify --backend-ref <sha> --frontend-ref <sha> --infra-ref <sha>` [VERIFIED: D-01 recommended interface] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| V9QUAL-01 | Local and CI resolve to identical argv; both fresh locked installs; warm env rejected | integration/contract | `python -m pytest tests/test_release_gate.py -q` | ❌ Wave 0 |
| V9QUAL-02 | Two separate clocks/envs, same collection, AWS/network denial, zero non-pass outcomes, exact NOT RUN | integration/adversarial | `python -m pytest tests/test_deterministic_gate.py -q` | ❌ Wave 0 |
| V9QUAL-03 | Locked Web lint/build/audit/contract/E2E; skip/flaky/demo-only acceptance rejected | cross-repo integration | `node scripts/verify-release.mjs --self-test && npm run test:e2e -- --fail-on-flaky-tests` | ❌ Wave 0; current real suite red |
| V9QUAL-04 | Ruff zero; exact full mypy scope; suppression/baseline weakening rejected | static/contract | `python -m pytest tests/test_quality_gate_policy.py -q` plus canonical Ruff/mypy commands | ❌ Wave 0; current mypy red |
| V9QUAL-05 | Current advisory, expired/wildcard/wrong-lock exception blocks | unit/integration | `python -m pytest tests/test_dependency_policy.py -q` | ❌ Wave 0; current audits red |
| V9QUAL-06 | CDK topology/policies; manifest binding/tamper; staging promote/smoke/compensate; failed gate cannot expose artifact/credentials | unit/integration/controlled staging | `python -m pytest tests/test_release_manifest.py tests/test_delivery_workflow_contract.py -q` and infra `python -m pytest tests/test_release_topology.py -q` | ❌ Wave 0 |
| V9QUAL-07 | Later clean HEAD passes; mutation/ancestry/publication-shape violations fail | Git integration | `python -m pytest tests/test_phase473_evidence_verifier.py -q` | ✅ exists; requires extension |

### Sampling Rate

- **Per task commit:** run the exact targeted test file plus Ruff/mypy over changed Python modules. [VERIFIED: phase validation design]
- **Per wave merge:** run all new release-gate tests, existing backend suite once, frontend lint/build and focused Playwright, and infra assertions. [VERIFIED: phase validation design]
- **Phase gate:** canonical full command from clean exact refs; backend suite twice; all self/failure tests green; staging controlled failure exercise retained; production exact NOT RUN absent later explicit authorization. [VERIFIED: V9QUAL-01..06]

### Wave 0 Gaps

- [ ] `tests/test_release_gate.py` — local/CI parity, job dependency, clean bootstrap, exact result aggregation. [VERIFIED: missing file scan]
- [ ] `tests/test_deterministic_gate.py` — clocks, seed, collection, AWS/network denial, strict outcomes. [VERIFIED: missing file scan]
- [ ] `tests/test_quality_gate_policy.py` — exact mypy scope and forbidden weakening. [VERIFIED: missing file scan]
- [ ] `tests/test_dependency_policy.py` — audit/exception schema and expiry. [VERIFIED: missing file scan]
- [ ] `tests/test_release_manifest.py` — cross-repo identity, canonical JSON, artifact/config digests, tamper. [VERIFIED: missing file scan]
- [ ] `tests/test_delivery_workflow_contract.py` — action SHA pins, no artifact/credentials after failure, protected promotion dependency, rollback-on-smoke-fail. [VERIFIED: missing file scan]
- [ ] Extend `tests/test_phase473_evidence_verifier.py` for explicit publication and later metadata HEAD. [VERIFIED: existing test inspection]
- [ ] Frontend `scripts/verify-release.mjs` self-tests, runtime-config tests, real-service release Playwright project, and zero skip/flaky result parser. [VERIFIED: missing frontend gate scan]
- [ ] Infra `tests/test_release_topology.py` using CDK assertions for aliases, Object Lock/versioning/retention, role boundaries, and pointer resources. [VERIFIED: stoa-infra has no tests]
- [ ] Controlled staging failure fixture/exercise that records CI run IDs and proves compensation. [VERIFIED: D-16]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No direct application-auth change | Existing app auth remains out of this delivery-control scope. [VERIFIED: phase boundary] |
| V3 Session Management | No direct session change | Smoke uses bounded existing auth; it must not introduce a parallel session mechanism. [VERIFIED: phase boundary] |
| V4 Access Control | Yes | Environment-protected OIDC roles, exact repository/environment subjects, least-privilege staging/prod actions, and no credentials in verify jobs. [CITED: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws] |
| V5 Input Validation | Yes | Validate Git refs, canonical JSON schemas, hashes, paths, advisory exceptions, config allowlist, and AWS returned identities before mutation. [VERIFIED: release-control input surface] |
| V6 Cryptography | Yes | SHA-256 standard/AWS digests and AWS-managed encryption/Object Lock; never custom cryptography. [VERIFIED: D-13] |

### Known Threat Patterns for Release Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Artifact substitution after verification | Tampering | Content digest in manifest, immutable object version, Lambda `CodeSha256` precondition, and pre-promotion revalidation. [CITED: https://docs.aws.amazon.com/lambda/latest/api/API_PublishVersion.html] |
| Candidate ref changes between jobs | Tampering | Resolve SHAs once, check out detached exact commits, bind tree/lock hashes, never consume branch names as identity. [VERIFIED: D-13] |
| OIDC token used from wrong repo/branch/environment | Spoofing / elevation | IAM trust conditions for exact repository/ref/environment and separate staging/production roles. [CITED: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws] |
| Verification job leaks deployment authority | Elevation / information disclosure | No AWS credentials/environment on verification; artifact handoff occurs only after every required job; failure-injection tests assert deploy cannot start or receive artifact. [VERIFIED: D-16] |
| Mutable third-party Action tag | Tampering | Pin full commit SHA and review updates. [CITED: https://docs.github.com/en/actions/reference/security/secure-use] |
| Direct old role bypasses gate | Elevation | Remove direct update policies/workflows and stale-build bypass; production role can promote only manifest-bound immutable objects. [VERIFIED: current role/workflow inspection and D-07] |
| Partial rollback leaves split-brain release | Tampering / denial of service | Durable prior/target transaction, idempotent compensation of both pointers, verify restored identity, retain partial-failure evidence. [VERIFIED: D-08] |
| Evidence overwrite/deletion | Repudiation | S3 versioning, Object Lock retention, lifecycle rules that do not remove locked/current/known-good versions. AWS notes lifecycle cannot delete a protected object version until retention permits it. [CITED: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html] |
| Runtime config injects secret or unreviewed endpoint | Information disclosure / tampering | Non-secret allowlisted runtime schema, digest in manifest, separate review, CSP/origin validation; secrets stay server-side. [VERIFIED: D-14] |

### Security Verification Requirements

- Pin every third-party Action by full SHA and add a workflow-contract test. [CITED: https://docs.github.com/en/actions/reference/security/secure-use]
- Assert verify jobs have no `id-token: write`, AWS role, environment, or release bucket write. [VERIFIED: least-privilege design]
- Assert staging and production roles cannot overwrite content-addressed artifact keys or build artifacts. [VERIFIED: D-14]
- Treat manifest/config/artifact mismatch as tamper, fail before deployment, and retain the failure receipt. [VERIFIED: D-13/D-16]
- Privacy-scan receipts/logs and record IDs/digests rather than credentials, tokens, or student payloads. [VERIFIED: existing release_evidence/Phase 473 convention]

## Sources

### Primary (HIGH confidence)

- `474-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` — locked scope, decisions, requirements, and production non-authorization. [VERIFIED: repository files]
- Three repository code, workflows, lockfiles, test configurations, and CDK source — current architecture and version baseline. [VERIFIED: codebase grep]
- Local diagnostic runs dated 2026-07-18 — pytest, Ruff, mypy, Playwright, builds, dependency audits, GitHub API, and environment availability. [VERIFIED: command output]
- https://docs.astral.sh/uv/concepts/projects/sync/ — frozen/locked synchronization. [CITED: https://docs.astral.sh/uv/concepts/projects/sync/]
- https://docs.astral.sh/uv/concepts/python-versions/ — Python selection. [CITED: https://docs.astral.sh/uv/concepts/python-versions/]
- https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments — reviewers and self-review behavior. [CITED: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments]
- https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments — approval and environment secrets. [CITED: https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments]
- https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws — AWS OIDC trust constraints. [CITED: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws]
- https://docs.github.com/en/actions/reference/security/secure-use — immutable full-SHA Action pins. [CITED: https://docs.github.com/en/actions/reference/security/secure-use]
- https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html — immutable Lambda versions. [CITED: https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html]
- https://docs.aws.amazon.com/lambda/latest/api/API_PublishVersion.html — publish preconditions. [CITED: https://docs.aws.amazon.com/lambda/latest/api/API_PublishVersion.html]
- https://docs.aws.amazon.com/lambda/latest/dg/configuring-alias-routing.html — aliases and published versions. [CITED: https://docs.aws.amazon.com/lambda/latest/dg/configuring-alias-routing.html]
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html and `object-lock-managing.html` — WORM retention and lifecycle interaction. [CITED: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html]
- https://docs.npmjs.com/cli/commands/npm-ci/ and `npm-audit` — lock-exact install and audit interface. [CITED: https://docs.npmjs.com/cli/commands/npm-ci/]
- https://playwright.dev/docs/test-retries, `test-annotations`, and `test-cli` — flaky/skip/result policy. [CITED: https://playwright.dev/docs/test-retries]
- https://github.com/pypa/pip-audit — backend audit behavior. [CITED: https://github.com/pypa/pip-audit]
- https://time-machine.readthedocs.io/en/latest/usage.html — fixed time. [CITED: https://time-machine.readthedocs.io/en/latest/usage.html]
- https://pypi.org/project/pytest-socket/ — socket denial. [CITED: https://pypi.org/project/pytest-socket/]
- https://boto3-stubs.readthedocs.io/en/stable/ and https://typing.python.org/en/latest/spec/distributing.html — maintained typing boundary. [CITED: https://boto3-stubs.readthedocs.io/en/stable/]

### Secondary (MEDIUM confidence)

- None; critical claims were verified against repository/runtime state or cited official documentation. [VERIFIED: source audit]

### Tertiary (LOW confidence)

- None. [VERIFIED: source audit]

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — exact locked/current versions and package legitimacy were verified; capabilities use official docs. [VERIFIED: registries, lockfiles, slopcheck, official docs]
- Architecture: HIGH — driven by locked decisions, direct inspection of all three repositories, and AWS/GitHub service documentation. [VERIFIED: codebase + official docs]
- Pitfalls: HIGH — most are already observable in current workflows, test runs, artifacts, or configuration. [VERIFIED: local diagnostics]
- Live deployment state: LOW until an authorized AWS read-only inventory occurs. [VERIFIED: no AWS credentials]

**Research date:** 2026-07-18

**Valid until:** 2026-07-25 for dependency/advisory and GitHub/AWS live-state findings; 2026-08-17 for stable architecture findings. [VERIFIED: volatility assessment]
