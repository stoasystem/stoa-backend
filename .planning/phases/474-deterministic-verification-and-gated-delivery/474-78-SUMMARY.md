---
phase: 474-deterministic-verification-and-gated-delivery
plan: 78
subsystem: release-infrastructure
tags: [aws-cdk, cloudfront, s3-versioning, served-release, immutable-web, rollback]

requires:
  - phase: 474-73
    provides: closed same-origin served-release descriptor contract with exact object identities
  - phase: 474-77
    provides: immutable Lambda versions and staging/production aliases
provides:
  - CloudFront-served, versioned `/served-release.json` descriptor path
  - retained Web bucket and immutable `releases/sha256/` release-object authority
  - release roles bounded to descriptor/object readback, pointer writes, and distribution invalidation
affects: [474-27, 474-28, 474-32, 474-34, 474-35, 474-rollback]

tech-stack:
  added: []
  patterns: [stable-served-descriptor, versioned-web-release-objects, resource-passing-without-name-discovery]

key-files:
  created: []
  modified:
    - /Users/zhdeng/stoa-infra/app.py
    - /Users/zhdeng/stoa-infra/stacks/frontend_stack.py
    - /Users/zhdeng/stoa-infra/stacks/release_delivery_stack.py
    - /Users/zhdeng/stoa-infra/tests/test_release_topology.py

key-decisions:
  - "The stable same-origin descriptor is `/served-release.json`; its S3 object is versioned and is deliberately cache-disabled at CloudFront."
  - "Web release-object authority is limited to the content-addressed `releases/sha256/*` namespace and the stable descriptor, with no delete permission."
  - "ReleaseDeliveryStack receives the FrontendStack bucket and distribution directly, never through mutable live-name discovery."

patterns-established:
  - "Served pointer: CloudFront exposes a stable descriptor path while S3 versioning preserves each descriptor generation for exact readback and restore."
  - "Web transition authority: staging, production, and rollback identities have only object-version reads, bounded writes, and CloudFront invalidation for the declared distribution."

requirements-completed: []

coverage:
  - id: D1
    description: "The stable same-origin served-release descriptor path is versioned in S3, retained, and actually routed through the SPA CloudFront origin without caching."
    requirement: V9QUAL-06
    verification:
      - kind: unit
        ref: tests/test_release_topology.py#test_frontend_serves_a_versioned_descriptor_and_immutable_release_prefixes
        status: pass
    human_judgment: false
  - id: D2
    description: "Staging, production, and rollback roles can read exact release object versions and move only the bounded served pointer; they cannot delete objects or discover resources by name."
    requirement: V9QUAL-06
    verification:
      - kind: unit
        ref: tests/test_release_topology.py#test_release_roles_can_write_only_immutable_web_prefixes_and_the_served_pointer
        status: pass
      - kind: unit
        ref: tests/test_release_topology.py#test_app_passes_owned_web_resources_to_release_delivery_without_name_lookup
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-07-31
status: complete
---

# Phase 474 Plan 78: Immutable Served Web Release Pointer Summary

**CloudFront now serves a cache-disabled, versioned `/served-release.json` descriptor while release roles are constrained to immutable Web-object readback, the bounded pointer write, and this distribution's invalidation.**

## Performance

- **Duration:** 10 min across the RED/GREEN implementation and continuation verification.
- **Completed:** 2026-07-31
- **Tasks:** 1 TDD task
- **Files modified:** 4 infra files

## Accomplishments

- Added a retained, versioned SPA bucket plus an actual cache-disabled CloudFront behavior for `/served-release.json`, sharing the SPA origin with the Web entry path.
- Added the `releases/sha256/` Web-object namespace and least-privilege readback/pointer/invalidation authority for staging, production, and rollback identities.
- Instantiated the release-delivery stack with the owned bucket and distribution objects; no resource-name lookup, deployment, provider request, or production mutation occurred.

## Task Commits

1. **Task 1 RED: specify served Web release pointer** — `7a851f8` (test, stoa-infra)
2. **Task 1 GREEN: serve immutable Web release pointer** — `d9b4047` (feat, stoa-infra)

## Files Created/Modified

- `/Users/zhdeng/stoa-infra/stacks/frontend_stack.py` — versioned retained SPA storage and a cache-disabled served-release CloudFront behavior.
- `/Users/zhdeng/stoa-infra/stacks/release_delivery_stack.py` — bounded immutable Web-object/pointer/invalidation IAM authority.
- `/Users/zhdeng/stoa-infra/app.py` — direct owned Web-resource wiring into release delivery.
- `/Users/zhdeng/stoa-infra/tests/test_release_topology.py` — topology, permission, and no-name-discovery assertions.

## Decisions Made

- Kept `/served-release.json` as the one stable browser descriptor key established by Plan 73; S3 VersionId and SHA-256 remain the exact descriptor-selected identity coordinates for the later durable promotion transaction.
- Kept object deletion outside release authority. Later delivery coordination must prove every descriptor and selected-object readback before success or rollback evidence is recorded.
- Did not generate a backend distribution merely to make CDK synthesis green: its absent provenance manifest correctly blocks full synthesis.

## Deviations from Plan

None - the source implementation followed the planned RED/GREEN topology and authority boundaries.

## Verification

- `uv run pytest -q tests/test_release_topology.py -k "web or pointer or cloudfront or prefix"` — passed: 4 passed, 8 deselected.
- `uv run pytest -q tests/test_release_topology.py` — passed: 12 passed.
- `uv run ruff check app.py stacks/frontend_stack.py stacks/release_delivery_stack.py tests/test_release_topology.py` — passed.
- `uv run cdk synth` — exact `NOT RUN`: the deliberately unbypassed backend Lambda distribution guard rejected missing `/Users/zhdeng/stoa-backend/dist/.stoa-build-manifest.json`. No stale override, build, AWS call, deployment, smoke, or rollback was attempted.

## Known Stubs

None. The descriptor's exact body construction, post-write/readback validation, durable two-pointer transaction, and restore execution belong to Plan 474-27; this plan supplies the infrastructure topology and bounded authority they require.

## User Setup Required

None. A future full application synthesis needs a valid backend distribution manifest produced by its canonical verified release path; this source-only plan did not create one.

## Next Phase Readiness

- Plan 474-27 can bind the exact previous/target descriptor VersionId, selected Web/runtime-config identities, alias coordinates, and bounded invalidation to one durable compensating transaction.
- Production remains exact `NOT RUN` without later explicit operational authority.

## Self-Check: PASSED

- Both infra TDD commits exist in RED-to-GREEN order and modify only the four Plan 78 files.
- Focused and complete topology tests, targeted Ruff, and diff whitespace checks passed.
- `/Users/zhdeng/stoa-infra/.DS_Store` remains the sole untracked infra path and was not touched.
- No infrastructure, provider, deployment, smoke, or production action was performed.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-31*
