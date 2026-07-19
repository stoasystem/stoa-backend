---
phase: 474-deterministic-verification-and-gated-delivery
plan: 72
subsystem: web-release-configuration
tags: [typescript, runtime-config, sha256, web, release, security]

requires:
  - phase: 474-23
    provides: locked Web dependency repair and real frontend repository baseline
provides:
  - closed dependency-free Web runtime configuration schema, template, and typed loader
  - canonical SHA-256 binding to exact release and manifest identities
  - bounded credential-free same-origin loading and immutable validated registry state
affects: [474-web-gate, 474-release-manifest, 477-web-foundation, 479-runtime-infrastructure]

tech-stack:
  added: []
  patterns: [closed runtime schema, canonical JSON digest, strict JSON parser, immutable configuration registry]

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/public/runtime-config.json.template
    - /Users/zhdeng/stoa-frontend/schemas/release/runtime-config-v1.schema.json
    - /Users/zhdeng/stoa-frontend/src/lib/runtimeConfig.ts
    - /Users/zhdeng/stoa-frontend/tests/release/runtime-config.test.mjs
  modified: []

key-decisions:
  - "Release runtime configuration permits only staging, staging-pilot, and production; local/development configuration cannot enter the release contract."
  - "The loader preserves backend-api authentication and excludes Amplify, Cognito, native/mobile, demo-only, credential, and private values."
  - "A validated registry value is install-once: failed or different later candidates cannot clear or replace it."

patterns-established:
  - "Runtime config: validate exact keys and release identities before comparing the canonical whole-document SHA-256."
  - "Runtime fetch: same-origin GET with credentials omit, no-store, redirect error, JSON-only response, exact final URL, and a 16 KiB limit."

requirements-completed: []

duration: 12 min
completed: 2026-07-20
---

# Phase 474 Plan 72: Closed Web Runtime Configuration Summary

**The real Web frontend now loads one release-bound, non-secret backend-api configuration through a strict 16 KiB same-origin boundary and publishes only immutable validated state.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-19T23:19:26Z
- **Completed:** 2026-07-19T23:31:23Z
- **Tasks:** 1 TDD task
- **Files modified:** 4 frontend files

## Accomplishments

- Added a closed JSON Schema and reviewed template for exact `environment`, `release`, `web`, `api`, `auth`, `realtime`, and `features` domains.
- Implemented dependency-free structural validation, strict duplicate-key JSON parsing, canonical JSON SHA-256, explicit release-identity binding, deep freezing, and an install-once runtime registry.
- Added Node 20 adversarial coverage for unknown and secret material, alternate auth, development/mobile/demo configuration, unsafe origins, release drift, realtime consistency, response tampering, redirects, media type, status, final URL, and byte bounds.

## Task Commits

The TDD task was committed atomically in the frontend repository:

1. **Task 1 RED: define adversarial runtime-config behavior** - `408ee8f` (test)
2. **Task 1 GREEN: implement the closed runtime-config contract** - `c94f7b6` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/public/runtime-config.json.template` - Reviewed staging example with no credential, provider-auth, demo, or native values.
- `/Users/zhdeng/stoa-frontend/schemas/release/runtime-config-v1.schema.json` - Closed release schema with conditional realtime endpoint semantics.
- `/Users/zhdeng/stoa-frontend/src/lib/runtimeConfig.ts` - Typed validator, canonical digest, strict loader, and immutable registry.
- `/Users/zhdeng/stoa-frontend/tests/release/runtime-config.test.mjs` - Node 20 transpileModule-based contract and tamper suite.

## Decisions Made

- Kept the current `backend-api` browser authentication mode as the only accepted value; this plan does not activate Amplify/Cognito or introduce a second browser auth path.
- Limited release environments to `staging`, `staging-pilot`, and `production`; local configuration remains outside the release schema.
- Bound all four release identities independently of the canonical document digest, so an incorrect manifest or artifact identity fails even if a caller supplies a matching config digest.
- Required `realtime.endpoint` to be `null` when disabled and exact `wss://<api-host>/realtime` when enabled.
- Preserved a previously installed configuration across later validation/fetch failures and rejected a different successfully validated replacement.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical security behavior] Tightened release-only state, secret-value, identity, realtime, and registry controls**

- **Found during:** Task 1 GREEN review
- **Issue:** The first minimal implementation allowed a development environment, checked only secret-shaped keys, relied only on the outer document digest, required an endpoint while realtime was disabled, and cleared installed state before a later initialization attempt.
- **Fix:** Added release-only environments, secret-like value detection without entropy heuristics, independent release identity expectations, conditional realtime endpoint validation, and install-once registry semantics.
- **Files modified:** schema, loader, and adversarial test targets declared by Plan 72
- **Verification:** The expanded suite first failed 4 of 9 tests, then passed 9 of 9 under Node 20; TypeScript and targeted ESLint also passed.
- **Committed in:** `c94f7b6`

---

**Total deviations:** 1 auto-fixed (1 Rule 2 missing critical security behavior).
**Impact on plan:** The correction stays inside the four declared files and makes the intended fail-closed release boundary complete without adding dependencies or another auth path.

## Issues Encountered

- The host PATH exposed Node 26 while the release workflow requires Node 20. Official Node 20.20.2 ARM64 bytes were used from `/tmp` after verifying the published SHA-256; no project dependency changed.
- TypeScript needed sandbox permission only to refresh `node_modules/.tmp` incremental build metadata.
- Two hand-authored `/tmp` patch hunks had stale counts/context and were rejected atomically by `git apply`; corrected mechanical patches were then applied without unrelated changes.

## Known Stubs

None. Template hashes are explicit reviewed placeholders for a later release-manifest substitution step; the loader accepts no missing or placeholder fields at runtime because every identity must be an exact lowercase SHA-256 and match caller expectations.

## Threat Flags

None. The new file-fetch boundary is exactly the plan-owned runtime-config path and is constrained to a credential-free same-origin JSON GET with redirect refusal, exact final URL, and a 16 KiB limit.

## User Setup Required

None - this plan performs no provider, infrastructure, deployment, or production mutation.

## Verification

- Node 20.20.2: `node --test tests/release/runtime-config.test.mjs` -> 9 passed, 0 failed.
- `npm exec -- tsc -b` -> passed.
- `npm exec -- eslint src/lib/runtimeConfig.ts tests/release/runtime-config.test.mjs` -> passed.
- `git diff --check` -> passed; frontend worktree clean after commits.
- Production infrastructure, deploy, smoke, and rollback remain exact `NOT RUN`.

## Next Phase Readiness

- The later Web gate and immutable manifest plans can provide expected release identities and the canonical config digest to this loader.
- Plan 72 contributes to V9QUAL-03 and V9QUAL-06 but does not complete either requirement, Phase 474, or V9QUAL-01 by itself.
- Plan 73 and all native/mobile work remain untouched and deferred.

## Self-Check: PASSED

- All four declared frontend files exist.
- Frontend commits `408ee8f` and `c94f7b6` exist in order and contain no tracked-file deletion.
- Node 20 tests, TypeScript, targeted ESLint, diff, scope, stub, and threat-surface checks passed.
- No requirement or phase completion was marked.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
