---
phase: 474-deterministic-verification-and-gated-delivery
plan: 73
subsystem: web-release-trust
tags: [typescript, served-release, s3-versioning, sha256, same-origin, security]

requires:
  - phase: 474-72
    provides: closed Web runtime-configuration loader and exact validation expectations
provides:
  - closed non-circular served-release schema and reviewed template
  - bounded duplicate-aware same-origin descriptor loader
  - exact mapping from caller-origin-validated descriptor identities into the Plan 72 loader
affects: [474-78, 474-81, 474-82, 474-release-manifest, 474-promotion-rollback]

tech-stack:
  added: []
  patterns: [caller-owned origin trust, stable served keys with immutable object versions, strict JSON parsing]

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/public/served-release.json.template
    - /Users/zhdeng/stoa-frontend/schemas/release/served-release-v1.schema.json
    - /Users/zhdeng/stoa-frontend/src/lib/servedRelease.ts
    - /Users/zhdeng/stoa-frontend/tests/release/served-release.test.mjs
  modified: []

key-decisions:
  - "The descriptor selects the actually served runtime-config.json and index.html keys; immutable S3 VersionId and SHA-256 values provide exact object identity."
  - "The descriptor does not contain its own VersionId or digest, avoiding a circular self-identity contract."
  - "Runtime-config projection requires a caller-supplied expected Web origin and revalidates the descriptor instead of deriving trust from descriptor-controlled URLs."

patterns-established:
  - "Served release: stable same-origin service keys are bound to exact immutable object VersionIds and digests."
  - "Trust projection: current-origin authority enters from the caller and is never inferred from the untrusted descriptor."

requirements-completed: []

duration: 14 min
completed: 2026-07-20
---

# Phase 474 Plan 73: Served Release Descriptor Trust Summary

**The Web client now resolves one closed, non-circular same-origin descriptor that binds exact release identities and immutable served-object versions before runtime configuration can be loaded.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-19T23:51:26Z
- **Completed:** 2026-07-20T00:05:43Z
- **Tasks:** 1 TDD task
- **Files modified:** 4 frontend files

## Accomplishments

- Added a closed `stoa.web.served-release.v1` template and JSON Schema with exact release, runtime-config, and Web-entry coordinates and no descriptor self-digest/self-VersionId.
- Implemented dependency-free validation, canonicalization, deep freezing, duplicate-aware parsing, secret/provider/native/demo rejection, and a strict 16 KiB `/served-release.json` fetch boundary.
- Bound stable `runtime-config.json` and `index.html` service keys to exact S3 VersionIds and SHA-256 values, then projected only caller-origin-revalidated expectations into Plan 72.

## Task Commits

The TDD task was committed atomically in the frontend repository:

1. **Task 1 RED: define the served-release trust boundary** - `5254787` (test)
2. **Task 1 GREEN: implement the served-release descriptor contract** - `d568661` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/public/served-release.json.template` - Reviewed staging descriptor with exact candidate and served-object identities.
- `/Users/zhdeng/stoa-frontend/schemas/release/served-release-v1.schema.json` - Closed non-circular descriptor schema.
- `/Users/zhdeng/stoa-frontend/src/lib/servedRelease.ts` - Typed validator, strict loader, canonicalizer, and Plan 72 expectation projection.
- `/Users/zhdeng/stoa-frontend/tests/release/served-release.test.mjs` - Node 20 trust-boundary and adversarial contract tests.

## Decisions Made

- Kept the real served coordinates stable as `/runtime-config.json` and `/index.html`; release immutability comes from exact VersionId and SHA-256 evidence, while release/manifest/artifact digests independently identify the candidate.
- Excluded descriptor self-VersionId and self-digest fields so descriptor identity does not require a circular value.
- Required `toRuntimeConfigLoadOptions` to receive the caller's expected Web origin and revalidate all descriptor coordinates; a forged cross-origin plain object cannot nominate its own trust origin.
- Preserved Plan 72's `backend-api` runtime-config boundary without importing or starting React, API, auth, monitoring, contact, Amplify, or Cognito services.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The host default was Node 26; all release checks used the previously verified `/private/tmp/node-v20.20.2-darwin-arm64/bin` runtime.
- TypeScript incremental metadata under `node_modules/.tmp` required the approved sibling-repository sandbox write permission; the escalated run completed successfully.

## Known Stubs

None. The template's example hashes and VersionIds are explicit substitution inputs for the later release transaction; runtime validation accepts no missing field, mutable label, malformed digest, unsafe URL, or descriptor-controlled origin.

## Threat Flags

None. The only new network surface is the plan-owned exact same-origin `/served-release.json` GET with omitted credentials, no cache reuse, redirect refusal, exact final URL/media/status checks, and a 16 KiB bound.

## User Setup Required

None - no provider, deployment, infrastructure, or production mutation was performed.

## Verification

- Node 20.20.2: `node --test tests/release/served-release.test.mjs` -> 7 passed, 0 failed.
- `npm exec -- tsc -b` -> passed.
- `npm exec -- eslint src/lib/servedRelease.ts tests/release/served-release.test.mjs` -> passed.
- `git diff --check` -> passed; frontend worktree clean after commits.
- Production infrastructure, deployment, smoke, and rollback remain exact `NOT RUN`.

## Next Phase Readiness

- Plan 78 can serve and restore the exact descriptor VersionId and its selected stable object versions.
- Plans 81 and 82 can consume caller-origin-validated release expectations without reading build-time release truth or starting services early.
- Plan 73 contributes to V9QUAL-03 and V9QUAL-06 but does not complete either requirement or Phase 474.

## Self-Check: PASSED

- All four declared frontend files exist.
- Frontend commits `5254787` and `d568661` exist in RED-to-GREEN order and contain no tracked-file deletion.
- Node 20 tests, TypeScript, targeted ESLint, diff, scope, stub, and threat-surface checks passed.
- No requirement or phase completion was marked.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
