---
phase: 474-deterministic-verification-and-gated-delivery
plan: 28
subsystem: release-workflow
tags: [github-actions, immutable-refs, staging, oidc-boundary, production-not-run]

requires:
  - phase: 474-27
    provides: canonical staging-only delivery transaction validation
  - phase: 474-78
    provides: immutable Lambda and served-Web release topology
provides:
  - thin infrastructure workflow bound to exact backend and infrastructure commits
  - receipt digest/path validation before protected staging authority
  - explicit credential-free preflight and production NOT RUN boundary
affects: [474-32, 474-76, 474-79, staging-delivery, production-policy]

tech-stack:
  added: []
  patterns: [exact-receipt-boundary, credential-free-preflight, controller-owned-staging-authority]

key-files:
  created: []
  modified:
    - /Users/zhdeng/stoa-infra/.github/workflows/deploy.yml
    - tests/test_infra_workflow_contract.py

key-decisions:
  - "The verify job has neither an environment nor id-token authority; it fails closed when an actual deployed-state CDK read needs credentials."
  - "Plan 32 alone may add a protected staging read-only inventory/controller; Plan 28 does not borrow ambient or static credentials to make CDK diff pass."
  - "Production infrastructure, deployment, smoke, and rollback remain four separate exact NOT RUN obligations."

patterns-established:
  - "Validate exact immutable backend/infra SHAs, workflow identity, receipt path, and receipt bytes before calling the canonical delivery validator."
  - "Keep OIDC scoped to an environment-protected staging boundary and prohibit provider commands from the thin workflow."

requirements-completed: [V9QUAL-01, V9QUAL-06]

coverage:
  - id: D1
    description: "The infrastructure workflow validates exact source and staging-transaction identities, runs frozen topology preflight, and invokes only the canonical delivery validator."
    requirement: V9QUAL-01
    verification:
      - kind: unit
        ref: tests/test_infra_workflow_contract.py#test_workflow_matches_the_complete_fixed_contract
        status: pass
      - kind: unit
        ref: tests/test_infra_workflow_contract.py#test_identity_validation_script_fails_closed
        status: pass
    human_judgment: false
  - id: D2
    description: "Verification stays credential-free, staging OIDC is protected and dependency-closed, and production operations remain exact NOT RUN."
    requirement: V9QUAL-06
    verification:
      - kind: unit
        ref: tests/test_infra_workflow_contract.py#test_credential_free_diff_defers_deployed_state_reads_to_plan32_controller
        status: pass
      - kind: unit
        ref: tests/test_infra_workflow_contract.py#test_workflow_has_only_the_canonical_gate_and_no_production_mutation
        status: pass
    human_judgment: false

duration: 31min
completed: 2026-07-31
status: complete
---

# Phase 474 Plan 28: Thin Infrastructure Workflow Summary

**The infrastructure workflow validates an exact receipted release transaction and frozen topology before any protected staging identity, while all production operations stay explicit NOT RUN.**

## Accomplishments

- Replaced the duplicated formal caller with a thin infrastructure caller bound to exact backend and infrastructure SHAs plus a SHA-256-verified staging receipt below a bounded path.
- Required frozen topology verification and the canonical delivery validator before the protected staging boundary; no alternate gate exists.
- Kept verification free of environments and OIDC, constrained OIDC to the dependency-closed staging environment, and emitted separate production infrastructure/deploy/smoke/rollback NOT RUN obligations.
- Locked the owner decision that deployed-state reads cannot use ambient/static credentials here; Plan 32 owns the later protected staging read-only inventory/controller.

## Task Commits

1. Task 1 RED: b3ed032 (backend test).
2. Task 1 GREEN: b8692097 (backend) and 7e717c0 (infra).
3. Task 2: d3f805e (backend test) and 56fc1b1 (infra).

## Files Created/Modified

- /Users/zhdeng/stoa-infra/.github/workflows/deploy.yml - exact-ref, receipt-bound, credential-free verification and protected staging eligibility workflow.
- tests/test_infra_workflow_contract.py - closed YAML, mutable-ref, receipt, credential, canonical-gate, and production-NOT-RUN contract coverage.

## Decisions Made

- The authentication boundary is intentionally fail-closed: a real deployed-state CDK diff cannot gain provider access from the verify job.
- This plan records that handoff instead of pretending a diff succeeded. Plan 32 must provide the separately authorized protected staging inventory/controller.
- No production environment, OIDC capability, CDK apply, provider command, smoke, rollback, or deployment is defined in this workflow.

## Deviations from Plan

### Auto-fixed Issues

**1. Rule 1 - Bug: explicit fail-closed shell checks**
- **Found during:** Task 1 GREEN verification.
- **Issue:** Bash errexit does not reliably terminate this workflow shape on a false double-bracket predicate.
- **Fix:** Added explicit failure exits to workflow/ref, digest, and receipt-path predicates.
- **Files modified:** tests/test_infra_workflow_contract.py and /Users/zhdeng/stoa-infra/.github/workflows/deploy.yml.
- **Verification:** 17 workflow-contract tests and Ruff passed.
- **Committed in:** b8692097 and 7e717c0.

**Total deviations:** 1 auto-fixed Rule 1 issue.

## Issues Encountered

- CDK diff may require deployed AWS state. The owner selected the fail-closed path: no ambient/static credential workaround is allowed, and Plan 32 owns the protected staging read-only controller.

## Known Stubs

None. The deployed-state read is an explicit authorization boundary owned by Plan 474-32.

## User Setup Required

None. No AWS, provider, deployment, smoke, rollback, or production action was attempted.

## Verification

- Targeted workflow contract: 8 passed, 9 deselected.
- Full workflow contract: 17 passed.
- Ruff for the contract test: passed.

## Next Phase Readiness

- Plan 474-32 can add the protected staging read-only inventory/controller without weakening this boundary.
- Plan 474-76 can make frontend workflows equally thin consumers of the canonical gate.
- Production infrastructure, deployment, smoke, and rollback remain exact NOT RUN unless later explicitly authorized.

## Self-Check: PASSED

- b3ed032, b8692097, 7e717c0, d3f805e, and 56fc1b1 exist in task order.
- The workflow and backend contract test exist and are covered by the passing targeted suite.
- No provider SDK/client call, AWS credential, deployment command, production mutation, or untracked generated backend file was introduced.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-31*
