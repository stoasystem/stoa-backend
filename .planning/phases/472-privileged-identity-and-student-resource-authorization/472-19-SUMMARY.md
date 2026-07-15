---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 19
subsystem: auth
tags: [admin-authorization, body-targets, resource-ref, audit-evidence, route-inventory]
requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: central operator capability decisions and durable redacted authorization evidence
provides:
  - executable typed body-target providers for every registered affected admin route
  - bounded canonical scalar, collection, recovery-resolver, resume, handoff, and governance targets
  - all-of authorization and per-target evidence before every endpoint effect
affects: [admin-api, report-recovery, curriculum, parent-bindings, audit-governance]
tech-stack:
  added: []
  patterns:
    - route-local validated target providers attached to registered endpoints
    - length-prefixed canonical target coordinates with deterministic all-of evaluation
key-files:
  created: []
  modified:
    - src/stoa/security/admin_authorization.py
    - src/stoa/security/route_inventory.py
    - src/stoa/routers/admin.py
    - tests/test_admin_authorization.py
    - tests/test_authorization_audit.py
    - tests/test_route_authorization_inventory.py
    - docs/security/route-authorization-inventory.json
key-decisions:
  - "Validated route-specific providers, never arbitrary request JSON, are the only source of administrator body-target authority."
  - "Every concrete collection member receives an independent decision and durable redacted allow row before the endpoint may execute."
patterns-established:
  - "Typed target handoff: cardinality, tuple fields, bounds, exclusions, and resolver identity are executable inventory metadata."
  - "Whole-command release: decisions and all mandatory evidence complete for the sorted unique target set before the first business effect."
requirements-completed: [V9ACCESS-01, V9ACCESS-02, V9ACCESS-03]
duration: 5 min
completed: 2026-07-15
---

# Phase 472 Plan 19: Typed Admin Body-target Authorization and Audit Identity Summary

**All registered administrator body targets now become bounded collision-safe ResourceRefs, require all-of capability authority, and receive durable per-target evidence before any handler or service effect.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-15T16:09:42Z
- **Completed:** 2026-07-15T16:14:31Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Attached executable scalar, collection, resolver-collection, and reference-only metadata to all 20 registered admin routes whose validated bodies intersect policy targets.
- Replaced body-target global fallback with deterministic typed length-prefixed coordinates, duplicate rejection, mixed-student all-of decisions, and mandatory evidence-before-effect release.
- Added allowlisted read-only recovery, resume, and support-handoff resolvers that materialize exact bounded report/job/fixture target sets and validate preview tokens before create effects.
- Projected target paths, tuple fields, cardinality, maximums, required semantics, resolver identity, and evidence-only exclusions into byte-stable inventory and OpenAPI metadata.
- Proved exact parent-binding scope, mixed-student denial, duplicates, delimiter-shaped values, reordered collections, later audit failure, redaction, and zero mutation through registered endpoints.

## Task Commits

1. **Task 1: Make typed body-target coverage executable and fail closed** - `9c1ad60` (feat)
2. **Task 2: Authorize the canonical typed target before admin effects** - `fe6e438` (fix)
3. **Task 3: Prove target-specific durable evidence and outage behavior** - `81a15fc` (test)
4. **Task 2 closure: Resolve exact recovery, resume, and handoff targets** - `edb6bf6` (fix)

## Files Created/Modified

- `src/stoa/security/admin_authorization.py` - Defines typed providers, canonical ResourceRefs, read-only target resolvers, all-of decisions, and evidence-before-effect release.
- `src/stoa/security/route_inventory.py` - Validates exact body-policy-provider intersections and projects executable target metadata.
- `src/stoa/routers/admin.py` - Attaches route-specific providers to curriculum, parent binding, bulk report, recovery, handoff, and governance handlers.
- `tests/test_admin_authorization.py` - Exercises registered exact-scope, duplicate, mixed-student, denial, and outage behavior.
- `tests/test_authorization_audit.py` - Proves deterministic distinct redacted per-target fingerprints in either input order.
- `tests/test_route_authorization_inventory.py` - Proves provider mutation failures and OpenAPI/JSON projection identity.
- `docs/security/route-authorization-inventory.json` - Checked deterministic metadata for all 219 registered operations.

## Decisions Made

- Preview routes may return an empty result under a deliberately global read, but create/resume routes reject an empty resolved set before mutation.
- Resolver reads may identify targets only; job creation, queue invocation, provider send, and persistence remain behind the completed all-of decision/evidence gate.
- Descriptive dictionaries and fields such as reasons, notes, release evidence, break-glass material, fixture names, and expected versions never enter target extraction.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- Task 1 body/target/inventory/registered-admin gate: 138 passed.
- Task 2 body/parent-binding/curriculum/report/scope/target/effect gate: 83 passed.
- Complete Plan 19 suites: 171 passed.
- Registered inspection: 20/20 body-target admin routes have executable providers; inventory contains 219 operations.
- Inventory generation and `--check` pass; two renders are byte-identical.
- Static inspection finds no `request.json()` target inference in the authorization or inventory modules.
- No AWS, network, provider sandbox, or production mutation ran.

## Next Phase Readiness

- WR-01 is closed locally across route metadata, scope matching, per-target evidence, and registered endpoint effects.
- Phase 474 Settings fixtures and Phase 475 teacher takeover atomicity remain unchanged and deferred to their owning phases.
- Ready for Plan 472-20 and final gap-integration evidence in Plan 472-22.

## Self-Check: PASSED

- All seven modified source, test, and checked-in inventory files exist.
- All four Plan 472-19 implementation/test commits are present in git history.
- Every task acceptance family and the plan-level verification command pass.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
