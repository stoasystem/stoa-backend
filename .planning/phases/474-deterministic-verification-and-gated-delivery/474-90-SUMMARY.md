---
phase: 474-deterministic-verification-and-gated-delivery
plan: 90
subsystem: backend-formal-workflow-caller
tags: [github-actions, exact-ref, release-gate, namespaces, no-deploy]

requires:
  - phase: 474-89
    provides: fixed non-selectable candidate-bound Python then Web formal aggregate
provides:
  - one manual read-only backend formal-verification workflow
  - exact three-repository SHA and checkout identity binding
  - proved Linux network and PID namespace preconditions
  - closed no-deploy workflow contract
affects: [474-91, 474-92, 474-93, 474-94, V9QUAL-01, V9QUAL-02]

tech-stack:
  added: []
  patterns:
    - workflow revision owns the backend gate implementation SHA
    - pinned actions and exact runtime patch versions
    - complete ordered workflow-step contract
    - ephemeral private evidence with fail-closed namespace proof

key-files:
  modified:
    - .github/workflows/deploy.yml
  created:
    - tests/test_backend_workflow_contract.py

key-decisions:
  - "Backend workflow dispatch accepts three lowercase full SHAs, and backend_sha must equal github.sha so a new workflow cannot execute an older unchecked gate implementation."
  - "The caller prepares and proves the exact Linux network and PID namespace primitives before candidate issuance; inability to establish either boundary fails the job."
  - "The workflow has read-only contents permission and no production, credential, artifact, alternate-gate, mobile, or native authority."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 90: Backend Formal Workflow Caller Summary

**The backend no longer deploys from a main-branch push; it now exposes one manual, immutable-source, verification-only caller of the fixed formal aggregate.**

## Accomplishments

- Replaced the direct Lambda build/update workflow with one `workflow_dispatch` job requiring exact backend, frontend, and infra commit SHAs.
- Bound `backend_sha` to the workflow's own `github.sha`, validated all inputs before checkout, disabled checkout credential persistence, and revalidated each detached checkout HEAD.
- Pinned all three external Actions by reviewed full commit SHA, fixed Python `3.12.13` and uv `0.11.16`, and disabled uv caching and uv-managed Python downloads.
- Added exact fail-closed Ubuntu namespace preparation and live network/PID namespace probes matching the formal gate's isolation primitives.
- Created private evidence atomically below `$RUNNER_TEMP` with mode `0700`, then invoked exactly candidate followed by formal with the same three source roots.
- Added a duplicate-key-rejecting YAML contract that closes the trigger, inputs, permissions, complete ordered 11-step graph, action inputs, shell scripts, source identities, evidence privacy, gate arguments, and forbidden mutation vocabulary.

## Task Commits

1. `ec90aa5` RED — define the backend workflow contract against the unsafe push-to-Lambda implementation.
2. `9e11a69` GREEN — replace direct deployment with the exact-ref fixed-formal caller and close all adversarial bypasses.

Planning commit `8f3ec22` established the one-workflow, one-test atomic scope.

## Verification

- Focused backend workflow contract: `16 passed`, `0 failed`.
- Extended release regression across backend workflow, formal aggregate, release gate, and manifest: `203 passed`, `0 failed`.
- Ruff: passed.
- Bash syntax validation for every workflow `run` block: passed.
- `git diff --check`: passed.
- Independent adversarial review: final PASS with no remaining blocker or major finding after closing namespace readiness and extra-step/`if: false` bypasses.
- Provider-hosted workflow execution: exact `NOT RUN`; no source was pushed and no provider job was dispatched.
- Production infrastructure, deploy, smoke, and rollback: exact `NOT RUN`, with zero cloud or production calls.

## Deviations from Plan

- The first GREEN draft used `cache: false` with setup-python; official action metadata defines `cache` as a package-manager name, so the input was removed to retain its no-cache default.
- The first draft placed a runner-temp expression at workflow scope; evidence creation now uses the runner-provided shell environment and exports only the atomically created private path to later steps.
- Adversarial review required a closed ordered step graph and exact Linux namespace preparation/proof; both were added before the GREEN commit.
- No frontend, infra, source-handoff, provider, production, mobile, or native file was changed by this plan.

## Remaining Work

- Plan 91 must replace frontend CI/direct deploy paths with the same fixed exact-ref formal caller.
- Plan 92 must replace the infra direct CDK workflow with the same fixed exact-ref formal caller.
- Plan 93 must freeze the final three-repository source handoff without circular evidence identity.
- Plan 94 must run the fixed formal aggregate twice on the exact final source in a no-host-mount Linux environment and retain both V9QUAL-01/V9QUAL-02 receipts.
- V9QUAL-01 and V9QUAL-02 remain open until those steps complete.

## Self-Check: PASSED

- Both declared implementation files and both task commits exist.
- The complete contract and release regressions pass from the committed GREEN source.
- The repository is clean, and provider/production/mobile/native work was not claimed or executed.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
