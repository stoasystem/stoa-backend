---
phase: 474-deterministic-verification-and-gated-delivery
plan: 26
subsystem: release-infrastructure
tags: [aws-cdk, s3-object-lock, github-oidc, least-privilege, immutable-storage]

requires:
  - phase: 474-01
    provides: exact candidate repository identity and the narrow infra-root .DS_Store exception
  - phase: 474-06
    provides: content-addressed artifact and evidence identities consumed by release storage
provides:
  - retained private versioned Object Lock stores for release artifacts and evidence
  - exact-subject GitHub OIDC roles with separated upload, staging, production, and rollback storage authority
  - verification identity with no AWS resource or deployment authority
affects: [474-release-delivery, 474-staging, 474-promotion, 474-rollback, 479-infrastructure]

tech-stack:
  added: [pytest-9.0.3-test-only]
  patterns: [content-addressed S3 prefixes, retained WORM evidence, exact OIDC subjects, resource-scoped IAM]

key-files:
  created:
    - /Users/zhdeng/stoa-infra/stacks/release_delivery_stack.py
    - /Users/zhdeng/stoa-infra/tests/test_release_topology.py
  modified:
    - /Users/zhdeng/stoa-infra/pyproject.toml
    - /Users/zhdeng/stoa-infra/uv.lock
    - /Users/zhdeng/stoa-infra/stacks/storage_stack.py

key-decisions:
  - "Release artifacts retain versions under a 90-day governance Object Lock minimum; release evidence uses a seven-year governance retention and neither store has lifecycle expiry."
  - "The verify role intentionally has no AWS resource policy, while upload, staging, production, and rollback roles receive only exact S3 object actions under owned prefixes."
  - "This plan creates neither Lambda alias/version resources nor Web release pointers and grants no deployment authority."

patterns-established:
  - "Immutable release state: private encrypted versioned buckets, Object Lock, retained deletion policies, access logging, and content-addressed object prefixes."
  - "Authority separation: exact GitHub OIDC audience/subject conditions plus role-specific, non-wildcard S3 object resources."

requirements-completed: []

duration: multi-session
completed: 2026-07-20
---

# Phase 474 Plan 26: Immutable Release Storage and Scoped Roles Summary

**Release artifacts and evidence now have retained Object Lock storage, while every GitHub OIDC role is constrained to an exact subject and the minimum plan-owned S3 prefix actions.**

## Performance

- **Duration:** Multi-session (RED contract committed 2026-07-19; GREEN completion verified 2026-07-20)
- **Completed:** 2026-07-20T03:06:59Z
- **Tasks:** 1 TDD task
- **Files modified:** 5 infra files across RED and GREEN commits

## Accomplishments

- Added private, encrypted, versioned release-artifact and release-evidence buckets with Object Lock, retained deletion/update policies, SSL enforcement, and access logging.
- Set artifact retention to 90 days and evidence retention to 2,555 days, with no lifecycle expiry that could remove current or known-good rollback material.
- Added exact GitHub OIDC identities for verification, upload, staging, production, and rollback; branch and environment subjects are closed to the reviewed backend repository.
- Gave the verification role no AWS resource authority and separated the other roles into exact content-addressed artifact and evidence prefixes without wildcard resources, delete actions, or deploy actions.
- Preserved the plan boundary: no Lambda alias/version, Web pointer, CloudFront distribution, deployment, smoke, or rollback operation was introduced or run.

## Task Commits

The TDD task was committed atomically in the infra repository:

1. **Task 1 RED: specify immutable release topology** - `2841b00` (test)
2. **Task 1 GREEN: define immutable release storage and roles** - `37a2a9b9c40b38fcfa6f62f36f6347234f0a69f4` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-infra/pyproject.toml` - Declares the locked test dependency used by the CDK topology contract.
- `/Users/zhdeng/stoa-infra/uv.lock` - Locks the exact test dependency graph.
- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` - Defines retained release artifact and evidence Object Lock buckets.
- `/Users/zhdeng/stoa-infra/stacks/release_delivery_stack.py` - Defines exact-subject GitHub OIDC roles and prefix-scoped S3 object permissions.
- `/Users/zhdeng/stoa-infra/tests/test_release_topology.py` - Proves storage controls, retention, trust subjects, authority separation, forbidden actions, and resource exclusions.

## Decisions Made

- Used S3-managed encryption and governance-mode Object Lock because the plan owns immutable retention and least privilege, not a new KMS administration surface.
- Kept artifact keys under `candidates/sha256/*`; upload may write candidates and verification evidence, while staging/production/rollback may read candidates and write only their own evidence namespaces.
- Created a verification role solely to make the trust boundary auditable. It has no inline resource policy and therefore cannot upload, deploy, promote, or roll back.
- Reused the existing GitHub OIDC provider by ARN and required both the exact `sts.amazonaws.com` audience and exact branch/environment subject for every role.

## Deviations from Plan

### Verification Boundary

**1. Full application synth remained `NOT RUN`**
- **Found during:** Final plan verification
- **Issue:** The full infra application imports the backend Lambda distribution and its cross-architecture guard rejects the available host-built artifact.
- **Disposition:** Did not bypass the guard and did not set `ALLOW_STALE`; synthesized the two plan-owned stacks independently instead.
- **Verification:** Independent `StorageStack` plus `ReleaseDeliveryStack` synthesis passed, alongside the complete seven-test topology contract.
- **Impact:** The plan-owned CDK resources are synthesized and asserted; full-application integration remains an explicit later verification item and is not claimed here.

No production or provider operation was substituted for the blocked full-application synth.

## Issues Encountered

- The backend Lambda distribution is architecture-sensitive, so a macOS-hosted full application synth could not honestly satisfy the Linux arm64 artifact guard. The guard remained intact.
- `/Users/zhdeng/stoa-infra/.DS_Store` remains the previously approved exact root-level exception; it was not modified or committed by this plan.

## Known Stubs

None in the two plan-owned stacks. Lambda alias/version resources, Web pointers, deployment policies, live smoke, and rollback mutation belong to later plans and were intentionally not added.

## Threat Flags

None. Tests prove exact OIDC subjects, no verify authority, no wildcard resources, no delete/deploy actions, and no alias or Web-pointer resources.

## User Setup Required

None for this source-level completion. AWS access, deployment, and production operations were not requested and remain exact `NOT RUN`.

## Verification

- `uv lock --check` -> passed.
- Focused topology selection -> 6 passed, 1 deselected.
- Complete `tests/test_release_topology.py` -> 7 passed.
- Independent `cdk.App` synthesis of `Plan47426Storage` and `Plan47426Delivery` -> passed.
- Full infra application synth -> exact `NOT RUN` because the backend cross-architecture Lambda distribution guard could not be satisfied on this host; no stale-build override was used.
- AWS access, infrastructure deployment, smoke, and rollback -> exact `NOT RUN`.
- Infra worktree after the GREEN commit contained only the previously approved untracked root `.DS_Store`.

## Next Phase Readiness

- Later release-delivery plans can bind content-addressed artifacts and receipts to the exact bucket prefixes and separated identities defined here.
- A Linux arm64-compatible backend distribution is still required before full-application synth can be claimed.
- V9QUAL-06 is advanced but intentionally not marked complete by this plan summary.

## Self-Check: PASSED

- All five declared infra files exist.
- RED commit `2841b00` and GREEN commit `37a2a9b9c40b38fcfa6f62f36f6347234f0a69f4` exist in order.
- Lock verification, focused and complete topology tests, and independent synthesis of both plan-owned stacks passed.
- Full application synth, AWS access, deployment, smoke, and rollback are recorded as `NOT RUN`; no bypass or production overclaim was introduced.
- `requirements-completed` remains empty.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
