---
phase: 474-deterministic-verification-and-gated-delivery
plan: 82
subsystem: web-startup
tags: [typescript, bootstrap, dynamic-import, runtime-config, startup-barrier, fail-closed]

requires:
  - phase: 474-73
    provides: caller-origin-validated served-release descriptor and runtime-config expectations
  - phase: 474-81
    provides: application environment imports that fail until runtime config is installed
provides:
  - descriptor-to-runtime-config startup coordinator with bounded timeout and duplicate-attempt denial
  - barrier-first main entry point with no static App, API, auth, React, or i18n graph import
  - fixed actionable credential-free failure rendering without React root creation
affects: [474-24, 474-83, 474-84, 477-web-foundation, web-application-entry]

tech-stack:
  added: []
  patterns: [barrier-first entry point, dynamic application graph, single-attempt startup state machine]

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/src/bootstrap.ts
    - /Users/zhdeng/stoa-frontend/tests/release/runtime-startup-barrier.test.mjs
  modified:
    - /Users/zhdeng/stoa-frontend/src/main.tsx

key-decisions:
  - "The browser entry statically imports only bootstrap; React, ReactDOM, CSS, i18n, App, routes, API, and auth modules enter through the post-install dynamic graph."
  - "Timeout or concurrent/repeated startup permanently fails that page attempt and cannot begin a second descriptor/config/App sequence."
  - "Startup errors are never rendered or logged; the root receives one fixed Chinese refresh/contact-support message and alert semantics."

patterns-established:
  - "Startup order: load served release, derive expectations from caller origin, install exact runtime config, dynamically import App, then create/render the React root."
  - "Failure containment: descriptor/config errors, timeout, and duplicate attempts resolve false with one fixed failure renderer and no App/root startup."

requirements-completed: []

duration: 12 min
completed: 2026-07-20
---

# Phase 474 Plan 82: Web Startup Barrier Summary

**The Web entry now validates and installs the exact served release configuration before any application, route, API, auth, monitoring, i18n, or React root graph can initialize.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-20T00:14:00Z
- **Completed:** 2026-07-20T00:25:38Z
- **Tasks:** 1 TDD task
- **Files modified:** 3 frontend files

## Accomplishments

- Added a single-attempt startup state machine with exact descriptor → expectation projection → runtime-config installation → dynamic App import → render ordering.
- Removed every static application/React/i18n import and eager `createRoot` call from `main.tsx`; the production build emits the App graph as a separate dynamic chunk.
- Added safe handling for descriptor/config mismatch, internal failure, bounded timeout, concurrent/repeated initialization, and attempted installed-config replacement without exposing errors or starting App/root.

## Task Commits

The TDD task was committed atomically in the frontend repository:

1. **Task 1 RED: define startup ordering and failure containment** - `597a950` (test)
2. **Task 1 GREEN: install the descriptor/config startup barrier** - `a8eaf17` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/src/bootstrap.ts` - Descriptor/config coordinator, timeout/duplicate state machine, and fixed safe failure renderer.
- `/Users/zhdeng/stoa-frontend/src/main.tsx` - Barrier-only static entry with post-install dynamic React/App/i18n/CSS loading.
- `/Users/zhdeng/stoa-frontend/tests/release/runtime-startup-barrier.test.mjs` - Source-graph, ordering, failure, timeout, concurrency, replacement, and message tests.

## Decisions Made

- Used module-global single-page startup state because the browser entry has one authoritative attempt; a concurrent or later call fails without another descriptor/config/App sequence.
- Checked the state after every asynchronous boundary, so a timeout or duplicate call that occurs while a fetch is pending prevents all later config installation and App import.
- Kept the failure renderer as direct bounded text/ARIA mutation, avoiding React, API, auth, monitoring, or provider initialization on the failure path.
- Added no development bypass. Therefore there is no local/release default to leak into production; if a future bypass is explicitly needed it remains constrained to Vite's built-in `import.meta.env.DEV`, never a release-varying `VITE_*` value.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The production build retains a pre-existing warning that the dynamically emitted App chunk exceeds 500 kB; build completion and barrier correctness are unaffected, and chunk optimization is outside this plan's three-file startup scope.
- The host default remained Node 26; release checks used the previously verified Node 20.20.2 runtime with approved sibling-repository build permissions.

## Known Stubs

None. The fixed failure message is the complete intended failure UI for this barrier; it tells the user to refresh and contact support without exposing internal coordinates.

## Threat Flags

None. The coordinator consumes only the existing plan-owned descriptor/config fetch boundaries; no new endpoint, auth path, monitoring policy, contact path, or provider integration was introduced.

## User Setup Required

None - no deployment, infrastructure, provider, or production mutation was performed.

## Verification

- Node 20.20.2: `node --test tests/release/runtime-startup-barrier.test.mjs` -> 6 passed, 0 failed.
- `npm exec -- tsc -b` -> passed.
- `npm exec -- eslint src/bootstrap.ts src/main.tsx tests/release/runtime-startup-barrier.test.mjs` -> passed.
- `npm run build` -> passed; Vite transformed 2,663 modules and emitted a separate `App-*.js` dynamic chunk.
- Production `dist/` release-VITE scan -> zero matches.
- `git diff --check` -> passed; frontend worktree clean after commits.
- Production operations remain exact `NOT RUN`.

## Next Phase Readiness

- Plan 83 can decide monitoring activation from the installed `features.errorMonitoring` flag after the barrier.
- Plan 84 can remove contact fallback without creating an early-import escape path.
- Plan 82 contributes to V9QUAL-03 and V9QUAL-06 but does not complete either requirement or Phase 474.

## Self-Check: PASSED

- All three declared frontend files exist.
- Frontend commits `597a950` and `a8eaf17` exist in RED-to-GREEN order and contain no tracked-file deletion.
- Node 20 tests, TypeScript, targeted ESLint, production build, dist scan, diff, scope, stub, and threat-surface checks passed.
- No requirement or phase completion was marked.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
