---
phase: 474-deterministic-verification-and-gated-delivery
plan: 27
subsystem: release-delivery
tags: [release-gate, lambda-alias, served-release, compensating-transaction, staging]

requires:
  - phase: 474-77
    provides: immutable Lambda versions and bounded staging alias authority
  - phase: 474-78
    provides: versioned served-release descriptor and immutable Web object topology
provides:
  - durable fail-closed staging transaction state machine for Lambda and Web pointers
  - exact pointer identity validation and idempotent compensation evidence
  - canonical non-mutating transaction validation gate command
affects: [474-28, 474-32, 474-34, 474-35, staging-promotion, rollback]

tech-stack:
  added: []
  patterns: [preconditioned-two-pointer-compensation, exact-readback-validation, staging-only-gate-command]

key-files:
  created:
    - schemas/release/promotion-transaction-v1.schema.json
    - scripts/release_delivery.py
    - tests/test_release_delivery.py
  modified:
    - scripts/release_gate.py
    - tests/test_release_manifest.py

key-decisions:
  - "The coordinator is a durable compensation transaction, not a false cross-service atomicity claim."
  - "All pointer coordinates include exact Lambda version/code/revision and descriptor/config/Web key, VersionId, and SHA-256; mutable names and body-only identity are rejected."
  - "The canonical gate exposes validation only at this stage; it cannot create a provider client or mutate staging or production."

patterns-established:
  - "Persist PREPARED before any provider action, transition with a state compare-and-swap, then retain COMMITTED, ROLLED_BACK, or PARTIAL_FAILURE evidence."
  - "Read back every target pointer before smoke and reapply known previous coordinates during compensation under current-coordinate preconditions."

requirements-completed: [V9QUAL-06]

coverage:
  - id: D1
    description: "A staging promotion binds exact previous and target Lambda alias, descriptor, runtime-config, and Web object identities, then commits only after both pointer readbacks and smoke pass."
    requirement: V9QUAL-06
    verification:
      - kind: unit
        ref: tests/test_release_delivery.py#test_staging_promotion_commits_only_after_two_pointers_and_smoke
        status: pass
    human_judgment: false
  - id: D2
    description: "Pointer failure, substitution, stale precondition, and failed smoke retain durable failure evidence and restore both pointers when exact compensation succeeds."
    requirement: V9QUAL-06
    verification:
      - kind: unit
        ref: tests/test_release_delivery.py#test_partial_pointer_failure_compensates_both_previous_identities
        status: pass
      - kind: unit
        ref: tests/test_release_delivery.py#test_descriptor_selected_config_or_web_substitution_is_retained_partial_failure
        status: pass
      - kind: unit
        ref: tests/test_release_delivery.py#test_smoke_failure_retains_failed_coordinates_and_restores_both_pointers
        status: pass
    human_judgment: false
  - id: D3
    description: "The canonical gate validates only staging transaction evidence and emits exact production NOT RUN obligations without a provider mutation path."
    requirement: V9QUAL-06
    verification:
      - kind: integration
        ref: tests/test_release_delivery.py#test_canonical_gate_registers_only_non_mutating_staging_delivery_validation
        status: pass
      - kind: unit
        ref: tests/test_release_manifest.py#test_manifest_and_promotion_contracts_bind_exact_staging_identities
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-07-31
status: complete
---

# Phase 474 Plan 27: Durable Two-Pointer Delivery Coordinator Summary

**A fail-closed staging coordinator now treats Lambda alias and served Web-release movement as one durable, idempotent compensating transaction with exact immutable identities.**

## Performance

- **Duration:** 6 min.
- **Started:** 2026-07-31T08:55:06Z.
- **Completed:** 2026-07-31T09:01:04Z.
- **Tasks:** 2 TDD tasks.
- **Files modified:** 5 source/test/schema files.

## Accomplishments

- Defined a closed `PREPARED` → `APPLYING` → `SMOKING` → `COMMITTED` transaction lifecycle with explicit `COMPENSATING`, `ROLLED_BACK`, and retained `PARTIAL_FAILURE` outcomes.
- Bound every previous/target pointer to the release/manifest, actor/run/request/idempotency identities; Lambda version/code/revision and descriptor-selected runtime-config/Web key, VersionId, and SHA-256 are all validated before use.
- Added preconditioned mutation, exact readback, smoke handling, two-pointer restore, retry replay, stale-read rejection, and cross-release/config substitution tests.
- Registered a canonical `delivery-validate` command that produces only a source-bound staging validation receipt and four exact production `NOT RUN` obligations; it performs no AWS/provider operation.

## Task Commits

1. **Task 1 RED: specify promotion transaction behavior** — `5825b8e` (test)
2. **Task 1 GREEN: implement durable staging transaction** — `fc5b9d0` (feat)
3. **Task 2: register canonical non-mutating validation command** — `2e34139` (feat)

## Files Created/Modified

- `schemas/release/promotion-transaction-v1.schema.json` — closed persisted transaction and exact pointer-coordinate schema.
- `scripts/release_delivery.py` — provider-agnostic, preconditioned staging coordinator and compensation state machine.
- `scripts/release_gate.py` — canonical staging-only transaction validation command.
- `tests/test_release_delivery.py` — TDD coverage for success, failures, compensation, retry, substitution, stale reads, and gate integration.
- `tests/test_release_manifest.py` — cross-contract assertions for manifest production `NOT RUN` and staging pointer identity binding.

## Decisions Made

- Production is structurally rejected by this transaction schema and by the registered gate command. The later protected environment/controller plans alone can add separately authorized provider-backed staging operations.
- A pointer write failure is never assumed to be absent: the coordinator rereads exact coordinates, compensates only from validated current values, and records `PARTIAL_FAILURE` if restore cannot be proven.
- An idempotency key may replay only an immutable-identical transaction; a reused key with changed release, actor, pointer, or manifest identity is rejected.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added the coordinator implementation during Task 1**
- **Found during:** Task 1 verification.
- **Issue:** The plan's Task 1 verification executes `tests/test_release_delivery.py`, whose required transaction behaviors cannot pass against a schema-only artifact.
- **Fix:** Added the narrowly scoped provider-agnostic coordinator needed to exercise the persisted schema without adding provider access or external mutation.
- **Files modified:** `scripts/release_delivery.py`, `tests/test_release_delivery.py`.
- **Verification:** 10 delivery tests, 38 combined delivery/manifest tests, targeted Ruff, and targeted mypy passed.
- **Committed in:** `fc5b9d0`.

**Total deviations:** 1 auto-fixed (Rule 3).
**Impact on plan:** The implementation is necessary for the planned Task 1 test command and remains within the plan's declared output and fail-closed authority boundary.

## Issues Encountered

- The initial test simulation reapplied its intentional Web substitution during rollback, which modeled a permanently malicious provider rather than the planned one-time substitution. The test fixture was corrected so compensation can prove the explicit restore path.

## Known Stubs

None. The provider interface is deliberately injected rather than stubbed: later Plan 474-32 owns the external-state controller and protected staging authority.

## User Setup Required

None. No AWS, provider, deployment, smoke, or production operation was attempted.

## Next Phase Readiness

- Plans 474-28 and 474-76 can make the sibling workflows thin consumers of this canonical staging transaction contract.
- Plan 474-32 can supply the separately authorized external-state adapter, environment controls, and workflow DAG without weakening exact transaction identities.
- Production infrastructure, deploy, smoke, and rollback remain exact `NOT RUN` unless later explicit operational approval exists.

## Self-Check: PASSED

- `5825b8e`, `fc5b9d0`, and `2e34139` exist in RED-to-GREEN/task order.
- `schemas/release/promotion-transaction-v1.schema.json`, `scripts/release_delivery.py`, and `tests/test_release_delivery.py` exist and are exercised by the passing targeted tests.
- No AWS SDK/client, deployment, provider request, production mutation, or untracked generated file was introduced.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-31*
