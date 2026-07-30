---
phase: 474-deterministic-verification-and-gated-delivery
status: applied
date: 2026-07-30
plans_before: 94
summaries_before: 32
plans_removed: 47
plans_after: 47
summaries_after: 32
remaining_plans: 15
---

# Phase 474 Plan Cleanup

Phase 474 accumulated several generations of plans while later phases and the
474-85 through 474-94 formal-gate rebuild changed the implementation boundary.
This cleanup preserves every executed plan and removes only plans without a
SUMMARY.

## Current execution boundary

Phase 474 now owns:

1. one current full-repository Ruff/mypy-zero gate;
2. the minimum immutable backend/Web release topology and exact-ref workflows;
3. protected-environment and staging-only deployment/rollback evidence;
4. final source, failure-matrix, and evidence sealing.

Product-level Web contracts and real role journeys belong to Phases 477 and
478. Only retained-route runtime deltas and browser WebSocket integration belong
to Phase 479. Redaction, readiness, non-WebSocket pagination, alarms, and staged
probe evidence belong to Phase 480; that phase consumes rather than rebuilds
Phase 474 delivery and rollback.

## Removed obsolete mypy decomposition

Removed plans:

`474-11` through `474-21`, and `474-43` through `474-71`.

These 40 plans decomposed a historical 435-error snapshot by file family. The
exact command run on 2026-07-30 now stops at three structural entry blockers
before full checking:

- `scripts/source_handoff.py` cannot resolve the `release_gate` module;
- the locked environment lacks PyYAML type stubs;
- tests are discovered under duplicate module identities.

The old family ordering is therefore no longer a truthful current diagnostic
map. Plan `474-22` now owns one source-current zero-error repair and gate.

## Removed superseded or reassigned plans

| Removed plan | Disposition |
|---|---|
| `474-24` | Fresh Web verification is implemented by `474-87` through `474-89`; OpenAPI/product adapter convergence belongs to Phase 477. |
| `474-25` | Real non-intercepted student/parent browser journeys belong to Phases 477 and 478 after the release foundation exists. |
| `474-29`, `474-30`, `474-31` | Separate backend/frontend/infra source handoffs are superseded by the single owner-approved tuple in `474-93`. |
| `474-74` | Fresh Web result policy and candidate binding are implemented by `474-87` and `474-88`. |
| `474-75` | Product browser-baseline repair belongs to Phases 477 and 478. |

## Retained incomplete plans

| Plan | Remaining single responsibility |
|---|---|
| `474-22` | Current full-repository Ruff/mypy zero |
| `474-27` | Durable two-pointer delivery coordinator |
| `474-28` | Exact-ref infrastructure delivery caller |
| `474-76` | Exact-ref frontend delivery caller |
| `474-77` | Published Lambda versions and aliases |
| `474-78` | Immutable served Web release pointer |
| `474-32` | Backend environment/delivery controller |
| `474-33` | Read-only provider/CDK inventory |
| `474-34` | Staging-only immutable substrate |
| `474-79` | Protected GitHub environments |
| `474-80` | Owner staging-policy checkpoint |
| `474-35` | Staging delivery and controlled rollback |
| `474-36` | Intentional-failure evidence matrix for the candidate-bound release gate; real Playwright journey acceptance remains Phase 478 work |
| `474-37` | Final requirement/source coverage audit |
| `474-38` | Final evidence sealing and later-HEAD verification |

## Integrity rules

- All 32 existing PLAN/SUMMARY pairs remain unchanged and present.
- Removed plan IDs are not renumbered or reused.
- Every retained dependency points to an existing plan.
- Future Phase 477–480 work must not be reintroduced into Phase 474.
