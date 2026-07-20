---
phase: 474-deterministic-verification-and-gated-delivery
plan: 81
subsystem: web-runtime-environment
tags: [typescript, runtime-config, environment, feature-flags, realtime, fail-closed]

requires:
  - phase: 474-72
    provides: validated install-once Web runtime configuration registry
  - phase: 474-73
    provides: caller-origin-bound release expectations for loading that registry
provides:
  - compatibility-preserving env.ts projection over getRuntimeConfig only
  - exact API, environment, feature, and realtime mappings for three release environments
  - fail-closed false values for every retained mock, demo, MSW, debug, preview, and fallback export
affects: [474-82, 474-83, 477-web-foundation, web-runtime-consumers]

tech-stack:
  added: []
  patterns: [installed-registry projection, static import barrier, compatibility-preserving fail-closed flags]

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/tests/release/runtime-env-projection.test.mjs
  modified:
    - /Users/zhdeng/stoa-frontend/src/lib/env.ts

key-decisions:
  - "env.ts reads getRuntimeConfig exactly once at module evaluation, so importing it before registry installation fails with runtime_config_uninitialized."
  - "The existing ApiMode contract maps staging and staging-pilot to staging and production to production; mock and demo remain type-compatible but are never selected."
  - "All mock, demo, MSW, internal-debug, checkout-preview, and fallback exports remain present for consumers but are fixed fail-closed false."

patterns-established:
  - "Environment projection: preserve consumer-facing names and primitive types while sourcing every release-varying value from the validated registry."
  - "Legacy surface containment: retained compatibility flags cannot silently reopen local or demo behavior in a release build."

requirements-completed: []

duration: 4 min
completed: 2026-07-20
---

# Phase 474 Plan 81: Runtime Environment Projection Summary

**Every existing Web environment consumer now receives exact installed runtime configuration values, while legacy demo, mock, debug, and fallback switches remain present but permanently fail closed.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-20T00:10:11Z
- **Completed:** 2026-07-20T00:13:44Z
- **Tasks:** 1 TDD task
- **Files modified:** 2 frontend files

## Accomplishments

- Replaced every `import.meta.env`/`VITE_*` and localhost/default release branch in `env.ts` with one module-evaluation read from the validated runtime registry.
- Preserved all existing runtime export names and primitive types while mapping staging, staging-pilot, production, API origin, closed feature flags, and realtime endpoint/enabled state exactly.
- Added Node 20 tests that prove uninitialized import failure, all three environment projections, no forbidden provider/native/contact tokens, and fixed-false legacy surfaces.

## Task Commits

The TDD task was committed atomically in the frontend repository:

1. **Task 1 RED: define runtime environment projection behavior** - `42ba796` (test)
2. **Task 1 GREEN: project existing environment exports from runtime config** - `3f49286` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/src/lib/env.ts` - Compatibility projection over `getRuntimeConfig()` with no compile-time release truth.
- `/Users/zhdeng/stoa-frontend/tests/release/runtime-env-projection.test.mjs` - Node 20 import barrier, three-environment, feature, realtime, compatibility, and no-VITE contract.

## Decisions Made

- Kept module exports as constants because existing consumers import them directly; this deliberately makes the current static application graph fail before installation until Plan 82 introduces the required dynamic startup barrier.
- Preserved `ApiMode` and `AppEnv` unions for source compatibility, while selecting only `staging` or `production` API modes and only the three validated release environments at runtime.
- Mapped analytics, feedback, payments, registration, teacher help, parent reports, referrals, support tickets, and realtime directly from the closed config; monitoring policy remains outside this plan.
- Kept `websocketBaseUrl` a string for existing consumers, projecting the validated endpoint or the compatibility-safe empty string when realtime is disabled.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The host default remained Node 26; release checks used the previously verified Node 20.20.2 runtime.
- TypeScript incremental metadata required the approved sibling-repository write permission; the full build passed without source changes outside the two declared files.

## Known Stubs

None. Fixed-false legacy exports are intentional fail-closed compatibility boundaries, not pending implementations; later Web cleanup may remove their consumers only through separately planned work.

## Threat Flags

None. This plan adds no network, auth, monitoring, contact, startup, or provider surface; it only projects an already validated in-memory registry.

## User Setup Required

None - no deployment, infrastructure, provider, or production mutation was performed.

## Verification

- Node 20.20.2: `node --test tests/release/runtime-env-projection.test.mjs` -> 4 passed, 0 failed.
- `npm exec -- tsc -b` -> passed across all existing consumers.
- `npm exec -- eslint src/lib/env.ts tests/release/runtime-env-projection.test.mjs` -> passed.
- `git diff --check` -> passed; frontend worktree clean after commits.
- Production operations remain exact `NOT RUN`.

## Next Phase Readiness

- Plan 82 can install descriptor-bound runtime config before dynamically importing the application graph; imports before that barrier now fail deterministically.
- Plan 83 can consume `features.errorMonitoring` directly without relying on an environment fallback.
- Plan 81 contributes to V9QUAL-03 and V9QUAL-06 but does not complete either requirement or Phase 474.

## Self-Check: PASSED

- Both declared frontend files exist.
- Frontend commits `42ba796` and `3f49286` exist in RED-to-GREEN order and contain no tracked-file deletion.
- Node 20 tests, full TypeScript, targeted ESLint, diff, compatibility, scope, stub, and threat-surface checks passed.
- No requirement or phase completion was marked.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
