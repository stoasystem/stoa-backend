---
phase: 474-deterministic-verification-and-gated-delivery
plan: 92
subsystem: infra-formal-workflow-caller
tags: [github-actions, exact-ref, infrastructure, no-oidc, no-deploy]

requires:
  - phase: 474-91
    provides: generic exact-ref caller and external-admissibility boundary
provides:
  - one generic manual read-only infra formal-verification workflow
  - exact infra workflow revision and checkout identity binding
  - complete removal of CI OIDC, PR-comment, CDK diff, and CDK deploy authority
  - portable local and materialized-snapshot infra contract
affects: [474-93, 474-94, V9QUAL-01, V9QUAL-02]

tech-stack:
  added: []
  patterns:
    - repository-owned SHA bound to workflow dispatch revision
    - shared closed caller graph with owner-specific validation
    - canonical project-marker root resolution
    - approved local dirt excluded from task commits and later evidence

key-files:
  modified:
    - /Users/zhdeng/stoa-infra/.github/workflows/deploy.yml
  created:
    - tests/test_infra_workflow_contract.py

key-decisions:
  - "Infra automation is a generic exact-ref verifier with no provider or release authority; Plan 93 and Plan 94 own external tuple admission."
  - "infra_sha must equal github.sha, while every checkout remains detached, exact, credential-nonpersistent, and post-verified."
  - "The approved infra-root .DS_Store stays untracked and excluded from this plan; clean-checkout handoff/formal evidence may not absorb it."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 92: Infrastructure Formal Workflow Caller Summary

**Infrastructure automation now has one immutable-source, verification-only formal caller and no OIDC, CDK diff, PR-comment, or CDK deploy path.**

## Accomplishments

- Replaced the two-job push/PR workflow with one manual three-SHA fixed candidate/formal runner.
- Bound `infra_sha` to the workflow event commit, fixed all action/runtime versions, disabled credentials/caches, and revalidated all detached checkout HEADs.
- Reused the exact fail-closed Linux namespace preflight, private evidence directory, and candidate-then-formal command graph from Plans 90 and 91.
- Removed OIDC and write permissions, explicit token/secrets, AWS retries/credentials, PR comment mutation, Node/npm/CDK installation, Lambda build, `cdk diff || true`, and retrying `cdk deploy`.
- Added full-object YAML equality, exact one-file nonsymlink workflow inventory, hostile-ref execution, Bash parsing, forbidden-provider vocabulary, and local/snapshot `stoa-infra`/`infra` root resolution.
- Shared the reviewed caller expectation through a deep copy, changing only the repository-owned `INFRA_SHA == WORKFLOW_SHA` assertion.

## Task Commits

1. Backend `1e91729` RED — define the infra workflow contract against OIDC/CDK diff/deploy automation.
2. Infra `6d545ad` GREEN — replace the only infra workflow with the generic exact-ref formal caller.

Planning commit `2dff594` established the two-file, one-infra-automation-boundary scope.

## Verification

- Focused infra workflow contract: `14 passed`, `0 failed`.
- Extended three-caller, formal aggregate, release gate, and manifest regression: `231 passed`, `0 failed`.
- Ruff: passed.
- Bash syntax validation for every infra workflow `run` block: passed.
- Backend/infra `git diff --check`: passed; backend and frontend clean, infra has only the pre-approved untracked root `.DS_Store`.
- Two independent read-only audits: final PASS with no blocker or major.
- Provider-hosted workflow execution and any V9QUAL admission: exact `NOT RUN`; no source was pushed and no workflow was dispatched.
- Production infrastructure, deploy, smoke, and rollback: exact `NOT RUN`, with zero cloud or production calls.

## Deviations from Plan

- No additional infra workflow or composite-action bypass existed; replacing the single file was sufficient.
- The contract intentionally imports and deep-copies the already-reviewed frontend caller expectation. All formal executions materialize all three sibling repositories, so the dependency remains portable and fail-closed.
- The root `.DS_Store` was not modified or staged. It must be absent from the final clean handoff/runtime roots even though candidate policy explicitly recognizes the owner's narrow exception.
- No IaC source, source-handoff artifact, provider, production, mobile, or native surface changed.

## Remaining Work

- Plan 93 must externally freeze one exact backend/frontend/infra tuple and machine-reject mismatching candidate/formal receipt identities; a prose-only record or self-issued candidate is insufficient.
- Plan 94 must independently materialize only that tuple, run the fixed formal aggregate twice in no-host-mount Linux, validate both receipts, and prove reproducibility.
- The three generic callers remain non-authoritative and provider execution remains `NOT RUN`; neither V9QUAL-01 nor V9QUAL-02 is complete yet.

## Self-Check: PASSED

- The infra task commit changes only the one workflow and excludes `.DS_Store`.
- The backend contract, infra workflow, RED/GREEN commits, focused/extended tests, and two audits exist.
- Provider/production/mobile/native execution was neither authorized nor claimed.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
