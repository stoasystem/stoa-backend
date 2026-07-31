# Phase 474: Deterministic Verification And Gated Delivery - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 474 establishes one deterministic, release-blocking verification and artifact path for the STOA Python backend and the real Web frontend in `/Users/zhdeng/stoa-frontend`. It owns clean target-runtime bootstrap, hermetic and repeated tests, lint and typing closure, dependency policy, cross-repository release identity, immutable build provenance, CI gate enforcement, and a complete staging deploy/smoke/rollback path. Production release control-plane work is deferred out of the phase to a separate future phase or milestone.

STOA is Web-first. Expo, React Native, iOS, Android, and the repository's `mobile/` skeleton are not part of the v9.0 release path. Native client work is deferred until the Web App has launched for testing and is stable. Phase 474 establishes the trustworthy delivery baseline; later replanned v9.0 phases complete every retained production Web route, all student/parent/teacher/admin-operator journeys, and every known reachable backend/Web defect.

</domain>

<decisions>
## Implementation Decisions

### Deterministic Verification

- **D-01:** Local formal verification and CI must invoke one authoritative entry point. CI may orchestrate it but may not reimplement a different gate.
- **D-02:** Every formal run creates a fresh Python 3.12 environment from the committed `uv.lock` in frozen mode. A developer `.venv` is convenient but cannot produce release evidence.
- **D-03:** The formal complete-suite gate requires `skip=0`, `xfail=0`, and `xpass=0`. External checks that are not available must be represented by a separate, exact `NOT RUN` obligation and never counted as passing.
- **D-04:** The complete suite runs twice in separate fresh environments: once at a standard fixed time and once at an explicit future fixed time. Both runs deny ambient AWS credentials and all non-allowlisted network access, and record the Python version, `uv.lock` hash, test collection identity, deterministic seed, clock identity, exit status, and outcome counts.

### CI, Promotion, And Rollback Authority

- **D-05:** A `main` candidate that passes every required gate builds one immutable release set and deploys it automatically to `StoaReleaseStaging`. This phase creates no production GitHub Environment, AWS stack, IAM role, OIDC trust, deployment, smoke, rollback, or promotion eligibility path; all such production work is `DEFERRED_OUT_OF_SCOPE` to a separate future phase or milestone.
- **D-06:** STOA is currently a one-person team. GitHub has exactly one release Environment, `staging`, restricted to branch `main`, disallowing tags, and requiring no manual reviewer. The `deploy-staging`, `smoke-staging`, and `rollback-staging` jobs share that Environment while assuming separate least-privilege AWS roles named `StoaStagingDeployRole`, `StoaStagingReadRole`, and `StoaStagingRollbackRole`; all three roles trust only `repo:stoasystem/stoa-backend:environment:staging`.
- **D-07:** No staging path may deploy new or rebuilt code without the complete gate and staging smoke. A controlled staging failure may immediately roll back to a previously verified artifact; a hotfix still follows the normal gated staging path.
- **D-08:** A failed staging smoke automatically returns the Lambda staging alias and Web release pointer to the previous verified release set. The failed release IDs, request/run IDs, health evidence, rollback action, and rollback result remain durable evidence.

### Typing And Dependency Risk

- **D-09:** Phase 474 must first attempt to reduce full-repository mypy errors to zero. It must not begin by accepting the audit's old error count as debt. Only after a concrete repair attempt may irreducible errors, root causes, and remediation costs be returned to the owner for an explicit temporary-baseline decision. Executors cannot silently freeze errors or weaken typing with broad `Any`, exclusions, or ignores.
- **D-10:** Missing third-party types are addressed with trustworthy maintained stubs or a narrow project-owned `Protocol`/typed adapter at the boundary. Global `ignore_missing_imports`, broad `Any`, and exclusion of provider integration modules are forbidden shortcuts.
- **D-11:** Critical and High dependency advisories block release by default; a production-reachable Medium advisory also blocks. A temporary exception is allowed only when a fix is unavailable or the path is proven unreachable, and records the exact package/advisory/version, reachability evidence, owner, expiry, and upgrade/removal target. Expired or broadened exceptions fail the gate.
- **D-12:** Dependency gates cover the backend lock and `/Users/zhdeng/stoa-frontend/package-lock.json`. They do not audit or gate the Expo `mobile/` skeleton for v9.0.

### Immutable Cross-Repository Release Evidence

- **D-13:** One cross-repository release manifest identifies a candidate by exact backend commit, frontend commit, both lockfile hashes, source-tree identities, backend and frontend artifact digests, target runtime/platform, verification run IDs, and gate results. Neither repository's branch name or mutable `latest` pointer is release identity.
- **D-14:** Backend and frontend use build once for the staging release path. The verified Lambda package and Web bytes are deployed unchanged to staging; environment differences enter only through reviewed runtime configuration. Any later production phase must consume immutable, digest-bound artifacts and may not reinterpret this phase as production authorization.
- **D-15:** Staging manifests, artifacts, smoke evidence, controlled-failure evidence, and rollback evidence remain available for at least 90 days. The current and most recent known-good staging rollback artifacts are never automatically deleted. Production retention policy is `DEFERRED_OUT_OF_SCOPE` with the rest of the production control plane.
- **D-16:** Every CI/gate change runs automated intentional-failure scenarios for tests, Ruff, mypy, dependency policy, provenance, and artifact tampering and proves the deploy job cannot receive an artifact. Initial activation and every structural gate redesign also perform a controlled non-production failure exercise with retained CI run IDs.

### v9.0 Web-First Product Correction

- **D-17:** v9.0 exists to complete the Web App and backend for early real testing: close every known audit defect, test-discovered defect, Phase 473 follow-up, and launch-blocking defect reachable through any retained production Web route. “Fix all bugs” is not an unbounded claim about undiscovered theoretical defects, but known Web/backend defects cannot be silently deferred.
- **D-18:** The current Phase 477/478 native-mobile roadmap is invalid for the product direction and must be replaced with Web foundation/contract convergence plus complete student, parent, teacher, and admin/operator journeys. A bounded executable route inventory must prove every retained production Web route works against real services or is intentionally removed/disabled. All later phases and the final reality gate use Web/browser evidence rather than Expo, iOS, Android, or device evidence.

### the agent's Discretion

- Exact fixed timestamps, deterministic seed representation, safe network allowlist needed only for dependency acquisition, evidence file formats, manifest schema versioning, CI job names, and artifact storage implementation.
- Exact mypy repair sequencing and typed-adapter structure, provided the executor first pursues full zero and does not create an unapproved baseline.
- Exact staging smoke endpoints and bounded automatic rollback timing, provided they cover the core Web/backend release and preserve the immutable release identity.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.** The milestone documents contain stale native-mobile language and must be read together with D-17/D-18 until the Web-first replan is committed.

### Milestone And Phase Contract

- `.planning/PROJECT.md` — v9.0 product boundary, existing Web frontend workspace, AWS/CDK constraints, and historical delivery context; native-mobile statements are superseded for remaining v9.0 work by this context and the forthcoming replan.
- `.planning/REQUIREMENTS.md` — current V9QUAL-01..06 contracts and the requirements that must be rewritten from native mobile to Web.
- `.planning/ROADMAP.md` — current Phase 474 goal/evidence/exit gate and the Phase 477..481 sequence to be replanned Web-first.

### Audit Baseline

- `docs/audit/full-project-audit.md` — TEST-001, OPS-001, OPS-002, SEC-007, QUALITY-001, observed direct production deployment, old red baseline, dependency findings, and remediation evidence expectations.
- `docs/audit/findings.json` — machine-readable finding severity, affected files, required tests, and dependency relationships.

### Backend Verification And Delivery

- `pyproject.toml` — Python/runtime, dependency, Ruff, pytest, and current typing configuration source.
- `uv.lock` — authoritative Python resolution input for clean formal environments.
- `.github/workflows/deploy.yml` — unsafe direct main-to-production workflow that Phase 474 replaces.
- `scripts/build_lambda_dist.py` — existing arm64 Lambda build, source hash, handler inventory, and manifest validation primitives to extend rather than discard.
- `scripts/release_evidence.py` — existing release-evidence utilities and conventions.
- `tests/conftest.py` — central pytest isolation and deterministic fixture integration point.

### Web Frontend Release Surface

- `/Users/zhdeng/stoa-frontend/package.json` — actual Web application scripts and dependency declarations.
- `/Users/zhdeng/stoa-frontend/package-lock.json` — authoritative Web dependency resolution input.
- `/Users/zhdeng/stoa-frontend/.github/workflows/frontend-ci.yml` — existing Web verification workflow to converge with the release manifest.
- `/Users/zhdeng/stoa-frontend/.github/workflows/deploy.yml` — existing Web deployment flow to change to build-once staging/production promotion.
- `/Users/zhdeng/stoa-frontend/playwright.config.ts` — Web end-to-end test entry point for later core-journey gates.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `scripts/build_lambda_dist.py` already creates a Python 3.12 manylinux arm64 package, hashes backend source and requirements, inventories both Lambda handlers, and rejects stale manifests. Extend it to lockfile-bound, artifact-byte-bound release provenance and compatible-runtime boot smoke.
- Phase 473's immutable evidence tooling demonstrates exact Git-blob hashing, command identity, result receipts, privacy scanning, and non-circular publication checks that can inform release evidence without copying Phase 473-specific logic.
- `/Users/zhdeng/stoa-frontend` already has `package-lock.json`, TypeScript build, ESLint, Playwright, Vite, and separate CI/deploy workflows; Phase 474 should integrate these real Web assets instead of the unused Expo tree.

### Established Patterns

- Backend tests use pytest and project-wide fixtures; Phase 474 should centralize ambient AWS/network denial and clock control rather than patching tests ad hoc.
- Security and privacy phases use closed evidence inventories, stable structured results, and exact source binding. Delivery gates should preserve that fail-closed approach.
- Infrastructure is CDK-owned in `/Users/zhdeng/stoa-infra`; Phase 474 must inspect existing roles, aliases, environments, and artifact stores before requiring infrastructure changes and must not invent manual production state.

### Integration Points

- `.github/workflows/deploy.yml` currently receives AWS credentials and updates both Lambda functions directly on every `main` push; split verification, immutable build, staging deploy/smoke, protected promotion, and rollback into dependency-closed jobs.
- Backend release identity must join the separate Web repository's commit/artifact/CI evidence without copying mutable source trees between repositories.
- `pyproject.toml`, `uv.lock`, `requirements.txt`, and Lambda packaging currently have overlapping dependency identities; planning must select one generated/verified chain and fail on drift.
- The future Web journey phases will consume this gate, so Phase 474 must make additional focused Web contract/E2E checks additive without allowing downstream workflows to bypass the common release entry point.

</code_context>

<specifics>
## Specific Ideas

- The project owner explicitly rejected native mobile as a current product goal: “网页端测试通过，开始稳定运行后，才去考虑推进客户端 app 的开发.” The owner also required completion of all Web App functionality and all known reachable bugs before early testing, including teacher/admin/operator routes rather than only student and parent journeys.
- The current operational flow is: verify both repositories → build once → deploy staging with `StoaStagingDeployRole` → smoke staging with `StoaStagingReadRole` → run the controlled failed-smoke exercise and restore the prior verified set with `StoaStagingRollbackRole`.
- The current one-person team uses one reviewer-free `staging` GitHub Environment. Separate deploy/read/rollback AWS roles provide permission separation without separate `staging-smoke` or `staging-rollback` GitHub Environments.

</specifics>

<deferred>
## Deferred Ideas

- Native Expo/iOS/Android client development, dependency repair, native builds, device E2E, push/offline client behavior, and app distribution are deferred until the Web App has launched for testing and reached stable operation. They require a future milestone based on Web production evidence, not automatic continuation of the current Phase 477/478 text.
- All production release-control-plane work is deferred to a separate future phase or milestone: no `production`, `production-smoke`, or `production-rollback` GitHub Environment; no production AWS stack, IAM role, or OIDC trust; and no production deployment, smoke, rollback, approval, or eligibility contract. Current receipts represent this as `DEFERRED_OUT_OF_SCOPE`, not `NOT RUN`.

</deferred>

---

*Phase: 474-Deterministic Verification And Gated Delivery*
*Context gathered: 2026-07-18*
