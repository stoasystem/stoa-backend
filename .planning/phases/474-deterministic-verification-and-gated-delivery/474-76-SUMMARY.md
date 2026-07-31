---
phase: 474-deterministic-verification-and-gated-delivery
plan: 76
subsystem: frontend-delivery-source-authority
tags: [github-actions, exact-ref, source-receipt, fail-closed, web]

requires:
  - phase: 474-27
    provides: canonical staging transaction validation
  - phase: 474-78
    provides: immutable served Web release pointer
  - phase: 474-93
    provides: historical cross-repository handoff policy
provides:
  - thin frontend formal and staging-eligibility workflow callers
  - owner-approved current frontend and infra source-ref receipts
  - exact root-only macOS metadata cleanliness exception with all other drift denied
affects: [474-33, 474-34, 474-35, 474-79, V9QUAL-01, V9QUAL-03, V9QUAL-06]

key-files:
  modified:
    - tests/test_frontend_workflow_contract.py
    - scripts/release_environment.py
    - tests/test_release_environment.py
  created:
    - scripts/issue_source_ref.py
    - tests/test_source_ref_issuer.py
    - evidence/phase-474/frontend-source-ref.json
    - evidence/phase-474/infra-source-ref.json
    - evidence/phase-474/474-76-source-ref-resolution.json
    - /Users/zhdeng/stoa-frontend/.github/workflows/deploy.yml

key-decisions:
  - "Frontend delivery validates exact refs and a SHA-256-bound canonical staging transaction, while staging authority remains backend-owned and production operations remain NOT RUN."
  - "Only one exact untracked path, the infrastructure repository root .DS_Store regular file, is excluded as macOS metadata; every nested or other untracked path and every tracked modification fails closed."
  - "Current source receipts require project-owner provenance, canonical approval time, and a closed non-empty approval scope before later inventory validation may consume them."

metrics:
  duration: 31min
  completed: 2026-07-31
  tasks_completed: 1
  files_created_or_modified: 9
status: complete
---

# Phase 474 Plan 76: Thin Exact-Ref Frontend Delivery Summary

**Frontend verification and staging eligibility now consume exact checked-out source and a digest-bound backend transaction without cloud authority, while current source refs are auditable and fail closed on every non-approved worktree drift.**

## Accomplishments

- Added the frontend `deploy.yml` as a manual, read-only exact-ref caller: it validates the frontend workflow revision, backend receipt path/digest, and checkout identities before invoking only `scripts/release_gate.py delivery-validate`.
- Kept the protected staging job as an explicit backend-owned authority boundary with no OIDC, cloud credential, build, upload, or provider command; production infrastructure, deploy, smoke, and rollback remain exact `NOT RUN`.
- Added a canonical local source-ref issuer that verifies approved commit, tree, lock digest, and worktree state before writing receipts with owner approval provenance, canonical UTC time, and scope.
- Resolved the prior `INFRA_WORKTREE_NOT_CLEAN` receipt without deleting or ignoring `.DS_Store`: only the exact regular root file in the infra repository is now recognized as non-source macOS metadata. Nested metadata, other untracked files, symlinks, and tracked changes remain hard failures.
- Issued current frontend and infra source refs for the approved coordinates and retained a resolution record linked to the earlier blocking receipt.

## Task Commits

1. `8fb22eb` — RED contract for the thin frontend delivery caller.
2. `a1ad044` (stoa-frontend) — GREEN frontend exact-ref staging-eligibility workflow.
3. `e73186b` — retained the initial fail-closed source-ref blocker evidence.
4. `8c322f3` — RED contract for the exact root-only worktree metadata policy.
5. `c501c00` — GREEN canonical source-ref issuer and approval validation.
6. `0ce5cda` — issued the current source-ref receipts and resolved the blocker audit chain.

## Verification

- `31 passed` across frontend workflow, source-ref issuer, and release-environment receipt tests.
- Ruff passed for all modified Python source and test files.
- The frontend source ref binds `a1ad044175517eb1896b386519640f938406ee49`, tree `c9c569e368d307c47f49ab353685dad2cc959928`, and package-lock SHA-256 `2a7762935fa88be068efa1cd3230e87cbc1e8899e4857a791a563da6d5ba5c17`.
- The infra source ref binds `56fc1b1f33cf74fa4d66bfb61aa74dc4404e412b`, tree `df1ec9fbda8506b86d7853d3d8de5faa59d23cf8`, and uv.lock SHA-256 `8c84a57b55b663b315f7d1b689e4f8ef6eba2c10c5b357d8914932731778bfd9`.
- Both receipts pass the closed `release_environment` source-ref validator after a fresh coordinate and worktree recheck.

## Deviations from Plan

### User-authorized scope clarification

- The original three-file workflow contract did not include source-ref issuance. The project owner explicitly authorized local auditable receipts only, then explicitly narrowed the retained infra root `.DS_Store` exception. The issuer, adversarial tests, approval validation, receipts, and resolution evidence are the minimum fail-closed implementation required to carry out that decision.

## Known Stubs

None. The backend-owned staging controller remains intentionally separate; this workflow contains no provider mutation path.

## External Operations

- Push, workflow dispatch, provider/AWS mutation, deploy, staging mutation, production infrastructure, production deploy, production smoke, and production rollback: exact `NOT RUN`.
- Plan 474-33 remains independently `BLOCKED`; its GitHub environment/ruleset/main-protection gaps and this Codex session's unavailable AWS SSO cache are not reclassified by this plan.

## Next Phase Readiness

- Source identity is now available for the blocked read-only Plan 474-33 inventory, but 474-34 and 474-79 remain blocked until 474-33 captures a complete safe provider/CDK before-state.
- The preserved blocker and resolution evidence make the `.DS_Store` policy auditable without treating it as source, build, or release content.

## Self-Check: PASSED

- All task and receipt commits above exist, the declared source refs and resolution evidence are present, and the frontend workflow remains in its dedicated repository.
- The infra `.DS_Store` remains untracked and untouched; no unexpected tracked-file deletion, provider call, or production action occurred.
