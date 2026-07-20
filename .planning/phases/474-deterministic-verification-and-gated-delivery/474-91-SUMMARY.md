---
phase: 474-deterministic-verification-and-gated-delivery
plan: 91
subsystem: frontend-formal-workflow-caller
tags: [github-actions, exact-ref, cross-repository, no-deploy, portable-tests]

requires:
  - phase: 474-90
    provides: reviewed exact workflow shape and Linux namespace/evidence controls
provides:
  - one generic manual read-only frontend formal-verification workflow
  - exact frontend workflow revision and checkout identity binding
  - complete removal of the frontend S3/CloudFront deployment workflow
  - portable local and materialized-snapshot workflow contract
affects: [474-92, 474-93, 474-94, V9QUAL-01, V9QUAL-02]

tech-stack:
  added: []
  patterns:
    - generic exact-ref executor separated from release admissibility
    - repository-owned SHA bound to workflow dispatch revision
    - exact one-file nonsymlink workflow directory
    - canonical sibling-root resolution across local and isolated layouts

key-files:
  modified:
    - /Users/zhdeng/stoa-frontend/.github/workflows/frontend-ci.yml
    - tests/test_frontend_workflow_contract.py
  deleted:
    - /Users/zhdeng/stoa-frontend/.github/workflows/deploy.yml

key-decisions:
  - "The frontend caller is a generic exact-ref verifier with no release authority; only the externally frozen Plan 93 tuple and independently checked Plan 94 receipts may make a run admissible."
  - "frontend_sha must equal github.sha, while the exact backend and infra inputs remain observable candidate coordinates rather than implicit approval."
  - "The backend-owned contract accepts exactly the local stoa-frontend sibling or formal materialization's frontend sibling after canonical project-marker validation, and rejects zero, multiple, or symlink matches."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 91: Frontend Formal Workflow Caller Summary

**Frontend automation now has one immutable-source, verification-only formal caller and no direct S3/CloudFront deployment path.**

## Accomplishments

- Replaced push/PR-triggered npm CI with the same closed manual three-SHA candidate/formal graph established by Plan 90.
- Bound the frontend input to the workflow's own commit, revalidated every checkout HEAD, retained only read-only contents permission, and used pinned Actions and exact runtime versions.
- Reproduced the exact Linux network/PID namespace preflight and private mode-0700 evidence controls without adding Node, npm, build, alternate-test, artifact, or cloud steps.
- Deleted `.github/workflows/deploy.yml`, including its OIDC, production Vite build, S3 writes, and CloudFront invalidation.
- Added complete-object YAML equality, exact one-file directory inventory, duplicate-key rejection, hostile-ref execution, Bash syntax, and mutation-vocabulary tests.
- Replaced the first machine-specific frontend path with a fail-closed resolver for exactly the two real layouts: local `stoa-frontend` and isolated snapshot `frontend`.

## Task Commits

1. Backend `2751794` RED — define the frontend workflow/deploy-removal contract against both unsafe workflows.
2. Frontend `13c4d10` GREEN — install the fixed formal caller and delete direct deployment.
3. Backend `0da4d23` GREEN fix — make the cross-repository contract portable to formal Linux materialization and close ambiguous/symlink roots.

Planning commit `5664ba5` established the three-file, one-frontend-automation-boundary scope.

## Verification

- Focused frontend workflow contract: `14 passed`, `0 failed`.
- Extended backend + frontend workflow, formal aggregate, release gate, and manifest regression: `217 passed`, `0 failed`.
- Ruff: passed.
- Bash syntax validation for every frontend workflow `run` block: passed.
- Backend and frontend `git diff --check`: passed; both worktrees clean after task commits.
- Two independent read-only audits: final PASS with no blocker or major after the snapshot-portability fix.
- Provider-hosted workflow execution and any V9QUAL admission: exact `NOT RUN`; no source was pushed and no workflow was dispatched.
- Production infrastructure, deploy, smoke, and rollback: exact `NOT RUN`, with zero cloud or production calls.

## Deviations from Plan

- The first contract used an absolute macOS frontend path, which would fail inside formal's `backend/frontend/infra` materialization. A canonical marker-validated dual-layout resolver and adversarial zero/multiple/symlink cases replaced it before completion.
- Review clarified that this caller validates exact source but does not approve it. An arbitrary exact backend input is non-authoritative until Plan 93 machine-binds the final tuple and Plan 94 independently accepts only matching receipts.
- No frontend business source, infra workflow, source-handoff artifact, provider, production, mobile, or native surface changed.

## Remaining Work

- Plan 92 must replace the infra CDK workflow with the same generic exact-ref formal caller.
- Plan 93 must externally freeze one exact backend/frontend/infra tuple and machine-reject every candidate/formal receipt whose source identities differ; documentation alone is insufficient.
- Plan 94 must run the fixed formal aggregate twice from that exact tuple in no-host-mount Linux and accept only independently verified matching receipts.
- Neither this workflow nor any future generic caller result may be used as a release or V9QUAL signal before Plans 93 and 94 close that trust boundary.

## Self-Check: PASSED

- The frontend task commit deletes the only direct deployment workflow and leaves one regular workflow file.
- All declared source/test files and three task commits exist; both repositories are clean.
- Provider/production/mobile/native execution was neither authorized nor claimed.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
