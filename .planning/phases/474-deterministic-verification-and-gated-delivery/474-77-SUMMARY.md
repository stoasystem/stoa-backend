---
phase: 474-deterministic-verification-and-gated-delivery
plan: 77
subsystem: release-infrastructure
tags: [aws-cdk, lambda, lambda-alias, immutable-version, rollback, pytest]

requires:
  - phase: 474-26
    provides: immutable release artifact/evidence storage and separated GitHub OIDC release roles
provides:
  - immutable Python 3.12 arm64 Lambda versions with staging and production aliases
  - alias-qualified API, scheduled-report, and internal report-invocation targets
  - release IAM authority restricted to alias reads and transitions
affects: [474-release-delivery, 474-staging, 474-promotion, 474-rollback, 479-infrastructure]

tech-stack:
  added: []
  patterns: [published-version-alias-routing, alias-only-release-authority, fail-closed-dist-provenance]

key-files:
  created: []
  modified:
    - /Users/zhdeng/stoa-infra/stacks/api_stack.py
    - /Users/zhdeng/stoa-infra/stacks/release_delivery_stack.py
    - /Users/zhdeng/stoa-infra/stacks/lambda_dist_guard.py
    - /Users/zhdeng/stoa-infra/tests/test_release_topology.py

key-decisions:
  - "HTTP API, Scheduler, and API-to-weekly-report invocation use production aliases, while staging and production aliases independently target immutable published versions."
  - "Release roles can read aliases/functions and update aliases only; CodeSha256 and RevisionId remain exact runtime API preconditions rather than invented IAM condition keys."
  - "The stale Lambda dist override was removed; an unavailable verified dist blocks synth instead of weakening provenance."

patterns-established:
  - "Alias routing: traffic and invoke grants name an alias-qualified ARN, never a mutable unqualified function ARN."
  - "Release authority: promotion, staging, and rollback principals receive Lambda alias transition actions only."

requirements-completed: []

coverage:
  - id: D1
    description: "Both Lambda functions publish immutable versions and expose independently controlled staging and production aliases."
    requirement: V9QUAL-06
    verification:
      - kind: unit
        ref: tests/test_release_topology.py#test_lambda_versions_and_aliases_bind_api_and_scheduler
        status: pass
    human_judgment: false
  - id: D2
    description: "Release-capable IAM paths can transition aliases but cannot update mutable function code or bypass distribution provenance."
    requirement: V9QUAL-06
    verification:
      - kind: unit
        ref: tests/test_release_topology.py#test_release_roles_can_only_move_aliases_and_stale_dist_bypass_is_absent
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-07-30
status: complete
---

# Phase 474 Plan 77: Immutable Lambda Alias Delivery Summary

**API and weekly-report delivery now route through published Lambda versions and independently controlled staging/production aliases, with no stale-dist bypass.**

## Performance

- **Duration:** 45 min
- **Completed:** 2026-07-30
- **Tasks:** 1 TDD task
- **Files modified:** 4 infra files

## Accomplishments

- Published immutable Python 3.12 arm64 versions for `stoa-api` and `stoa-weekly-report`, each with `staging` and `production` aliases.
- Bound HTTP API traffic, EventBridge Scheduler traffic, API-to-weekly-report invocation, and the legacy GitHub release policy to alias-qualified targets.
- Restricted staging, production, and rollback roles to `lambda:GetAlias`, `lambda:GetFunction`, and `lambda:UpdateAlias` on declared aliases; mutable function code updates are absent.
- Removed `ALLOW_STALE_LAMBDA_DIST`, preserving fail-closed Lambda distribution provenance.

## Task Commits

1. **Task 1 RED: Define Lambda versions aliases and stale-build denial** — `def3beb` (test)
2. **Task 1 GREEN: Define Lambda versions aliases and stale-build denial** — `f8b94a8` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-infra/stacks/api_stack.py` — creates versions/aliases and sends API, scheduler, permissions, and internal invoke targets through aliases.
- `/Users/zhdeng/stoa-infra/stacks/release_delivery_stack.py` — grants staging, production, and rollback roles alias-only transition authority.
- `/Users/zhdeng/stoa-infra/stacks/lambda_dist_guard.py` — removes the stale-build override and retains verified-manifest failure behavior.
- `/Users/zhdeng/stoa-infra/tests/test_release_topology.py` — asserts the alias/version topology, traffic bindings, IAM boundaries, and stale-bypass absence.

## Decisions Made

- Used Lambda's alias-qualified `function_arn` for traffic and IAM resources because it is the deployable invocation identity exposed by CDK's `Alias` construct.
- Kept `CodeSha256` and `RevisionId` as required runtime promotion/rollback API checks: IAM can narrowly authorize `UpdateAlias`, but cannot truthfully enforce request parameters through unsupported condition keys.
- Did not add Web release pointers or mutate AWS; those remain separate Phase 474 delivery work and explicit operational authorization.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Used CDK's alias-qualified function ARN instead of a nonexistent alias ARN property**
- **Found during:** Task 1 GREEN verification.
- **Issue:** `aws_cdk.aws_lambda.Alias` exposes the qualified invocation ARN as `function_arn`; the attempted `alias_arn` property does not exist.
- **Fix:** Replaced the invalid property with `function_arn` for IAM and release-role resources.
- **Files modified:** `stacks/api_stack.py`, `stacks/release_delivery_stack.py`.
- **Verification:** `uv run pytest -q tests/test_release_topology.py` passed (9 tests).
- **Committed in:** `f8b94a8`.

**2. [Rule 1 - Bug] Corrected topology assertions for CDK alias names and one-synthesis construct ordering**
- **Found during:** Task 1 GREEN verification.
- **Issue:** Lambda aliases share `staging`/`production` names per function, and CDK forbids adding a delivery stack after the app was already synthesized.
- **Fix:** Identified aliases by both function and alias name, and constructed dependent stacks before template synthesis.
- **Files modified:** `tests/test_release_topology.py`.
- **Verification:** `uv run pytest -q tests/test_release_topology.py` passed (9 tests).
- **Committed in:** `f8b94a8`.

**Total deviations:** 2 auto-fixed Rule 1 issues. Both were implementation/test-correctness fixes with no scope expansion.

## Verification

- `uv run pytest -q tests/test_release_topology.py` — passed: 9 tests.
- `uv run ruff check stacks/api_stack.py stacks/release_delivery_stack.py stacks/lambda_dist_guard.py tests/test_release_topology.py` — passed.
- Full `uv run cdk synth` — exact `NOT RUN`: the unbypassed backend distribution guard rejected missing `/Users/zhdeng/stoa-backend/dist/.stoa-build-manifest.json`. No stale override, rebuild, AWS call, deployment, smoke, or rollback operation was attempted.

## Known Stubs

None. This plan intentionally leaves Web pointers, deployment execution, and production smoke to their separately authorized Phase 474 work.

## User Setup Required

None. A verified backend Lambda distribution is required before a future full application synth can succeed; generating it was outside this plan's source-only scope.

## Next Phase Readiness

- Later release-delivery work can move only the staged/production aliases after its exact `CodeSha256` and `RevisionId` checks.
- Full integration synthesis remains blocked until the backend provides a valid, provenance-verified Lambda dist manifest.

## Self-Check: PASSED

- Both TDD commits exist in `stoa-infra` in RED then GREEN order.
- All four plan-owned infra files exist and are covered by the passing topology suite.
- No AWS or production mutation was performed; `stoa-infra/.DS_Store` remains untracked and untouched.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-30*
