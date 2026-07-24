---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 27
subsystem: testing
tags: [stripe, playwright, sandbox, security, redaction, e2e]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Durable checkout, signed webhook, entitlement, parent result, reminder, and admin recovery contracts from Plans 11, 19, 20, 24, 25, and 26
provides:
  - Fail-closed Playwright stripe-sandbox project with an explicit preflight dependency
  - Test-mode-only provider metadata, object, endpoint, origin, and artifact validation
  - Redacted sandbox receipt with only counts, modes, versions, and SHA-256 identities
  - Negative controls for mock fallback, browser interception, live mode, production mutation, and secret-bearing artifacts
affects: [476-28, 476-29, stripe-sandbox-acceptance, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Real-provider browser evidence runs in a separate dependency-gated Playwright project
    - Provider coordinates enter receipts only as fixed modes, bounded counts, or SHA-256 identities

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/scripts/stripe-sandbox-preflight.mjs
    - /Users/zhdeng/stoa-frontend/tests/e2e/stripe-sandbox-preflight.spec.ts
  modified:
    - /Users/zhdeng/stoa-frontend/playwright.config.ts
    - .planning/phases/476-billing-idempotency-and-paid-access-recovery/476-27-PLAN.md

key-decisions:
  - "The stripe-sandbox project never starts the local demo server; its dependency must validate explicit non-production Web/API origins and real test-mode readiness before acceptance tests run."
  - "The preflight binds the exact billing-paid-access acceptance source and rejects page/context route interception, HAR routing, route fulfillment, demo flags, and virtual-checkout source."
  - "Receipts contain no Stripe key, webhook secret, full provider object ID, or full endpoint/account identity."

patterns-established:
  - "Fail-closed sandbox dependency: missing configuration or provider evidence is a failing setup result, never a mock fallback."
  - "Source-bound no-interception proof: the exact acceptance spec digest is recorded only after static interception controls pass."

requirements-completed: [V9BILL-04]

duration: 14min
completed: 2026-07-24
---

# Phase 476 Plan 27: Stripe Sandbox Acceptance Preflight Summary

**A separate Playwright acceptance project now rejects mock, interception, live, production, unsigned, unverified, and secret-bearing payment evidence before any hosted Stripe journey can start.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-24T17:22:32Z
- **Completed:** 2026-07-24T17:36:33Z
- **Tasks:** 1
- **Files modified:** 3 frontend files plus plan metadata and this summary

## Accomplishments

- Added `stripe-sandbox-preflight` and dependent `stripe-sandbox` Playwright projects. Sandbox mode disables the local mock/demo Web server and trace, video, and screenshot capture.
- Added a bounded preflight that requires exact approved HTTPS non-production origins, Stripe-hosted Checkout, `sk_test_`, three unique test Prices, signed webhook configuration, a pinned event-destination API version, backend test readiness, and test-mode Price/Session/Invoice/Subscription/Event metadata.
- Bound preflight to the exact `billing-paid-access.spec.ts` source and reject route/HAR interception, response fulfillment, offline simulation, demo flags, and virtual checkout source.
- Publish the receipt atomically with mode `0600` inside one authorized evidence directory. The receipt includes only modes, counts, payment-method names, API version, and SHA-256 identities.
- Added 29 passing Chromium controls covering a positive redacted receipt and every planned mock/live/missing/interception/production/artifact failure boundary.

## Task Commits

TDD execution produced the required RED and GREEN commits in `/Users/zhdeng/stoa-frontend`:

1. **Task 476-27-01 RED: Add failing Stripe sandbox preflight controls** - `1a455f5` (test)
2. **Task 476-27-01 GREEN: Enforce Stripe sandbox acceptance preflight** - `70f2b46` (feat)

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/scripts/stripe-sandbox-preflight.mjs` - Fail-closed environment, origin, source, provider-metadata, livemode, artifact, and redacted-receipt guard.
- `/Users/zhdeng/stoa-frontend/tests/e2e/stripe-sandbox-preflight.spec.ts` - Positive redaction proof plus mock/live/missing/interception/production negative controls.
- `/Users/zhdeng/stoa-frontend/playwright.config.ts` - Separate preflight and sandbox projects, dependency link, external sandbox origin, no local demo server in sandbox mode, and capture-disabled policy.
- `.planning/phases/476-billing-idempotency-and-paid-access-recovery/476-27-PLAN.md` - Cross-repository key-link paths made verifier-resolvable.

## Decisions Made

- Existing Chromium tests retain their focused local mock Web server, but those tests cannot satisfy sandbox acceptance because `stripe-sandbox` has a separate name, dependency, environment switch, origin, metadata, and no-interception contract.
- The preflight consumes a bounded provider-readiness metadata file rather than querying or mutating Stripe. Plan 28 owns authorized real sandbox collection and the hosted Checkout journey.
- The acceptance spec itself is a trust-boundary input. Only the exact `billing-paid-access.spec.ts` file is accepted, and its digest is recorded after interception patterns are rejected.
- Receipt publication uses exclusive creation and refuses symlinked input/output boundaries or any output path outside the exact authorized evidence directory.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Kept preflight failures on the safe structured error path**
- **Found during:** Task 476-27-01 GREEN
- **Issue:** The initial top-level exception handler referenced its error class before class initialization, so an early validation failure produced a Node stack instead of one safe code.
- **Fix:** Initialized the closed error type before running preflight validation.
- **Files modified:** `/Users/zhdeng/stoa-frontend/scripts/stripe-sandbox-preflight.mjs`
- **Verification:** All 23 then 29 negative/positive controls returned only expected safe results; final exact gate passes.
- **Committed in:** `70f2b46`

**2. [Rule 1 - Bug] Canonicalized macOS temporary-directory aliases before output containment checks**
- **Found during:** Task 476-27-01 GREEN
- **Issue:** macOS resolves the temporary directory through `/private/...`, while the requested receipt retained the alias path; comparing one canonical and one aliased path falsely rejected an authorized output.
- **Fix:** Canonicalized the receipt parent and rebuilt the candidate path before the exact directory-boundary comparison.
- **Files modified:** `/Users/zhdeng/stoa-frontend/scripts/stripe-sandbox-preflight.mjs`
- **Verification:** Positive metadata publishes inside the temporary evidence directory while outside/symlink boundaries remain rejected.
- **Committed in:** `70f2b46`

**3. [Rule 3 - Blocking Verification] Made the cross-repository source link resolvable**
- **Found during:** Post-GREEN GSD key-link verification
- **Issue:** The GSD verifier reported `Source file not found` for the plan's absolute frontend paths although both artifacts existed.
- **Fix:** Changed only the Plan 476-27 key-link paths to established backend-relative `../stoa-frontend/...` forms.
- **Files modified:** `.planning/phases/476-billing-idempotency-and-paid-access-recovery/476-27-PLAN.md`
- **Verification:** GSD key-link verification reports `all_verified: true`, `1/1`.
- **Committed in:** Plan metadata commit

---

**Total deviations:** 3 auto-fixed (2 implementation bugs, 1 blocking verification-path issue).
**Impact on plan:** All fixes preserve the planned fail-closed boundary and evidence validity. No dependency, Stripe access, provider mutation, charge, deployment, production operation, or unrelated UI change was added.

## Security Verification

- The project rejects mock checkout, demo API, disabled payments, demo surfaces, evidence relabeling, browser route interception, HAR/fulfill/offline source, and virtual checkout.
- A live key or any Price, Checkout Session, Invoice, Subscription, or Event with `livemode=true` fails before receipt publication.
- Missing provider readiness, signed destination identity, webhook-secret availability, required Price, or pinned API-version agreement fails closed.
- Production mutation, production Web origin, localhost/demo API origin, and non-Stripe-hosted checkout origin fail closed.
- Trace, video, and screenshot capture must all be off; the sandbox project also sets all three off.
- Positive test metadata emits only test modes, object counts, API version, payment method name, and digests. Key, webhook secret, full Price/object IDs, account/destination IDs, and full Web/API origins are absent.
- The artifact canary scan found no credential/provider canaries in Playwright results.
- GSD verifies the `playwright.config.ts` → `stripe-sandbox-preflight.mjs` startup dependency link `1/1`.
- Every Plan 476-27 ASVS L1 High mitigation has a passing source-bound selector. The real provider journey and aggregate Phase 476 gate remain correctly deferred to Plans 28 and 29.

## Verification

- Exact plan gate passes: `npm run typecheck && npm run test:e2e -- stripe-sandbox-preflight.spec.ts --project=chromium`; Playwright reports `29 passed`, `0 skipped`.
- `npm run lint -- --quiet` passes.
- `git diff --check` passes in frontend and backend planning paths.
- Canary artifact, placeholder/stub, project isolation, source interception, livemode, provider-readiness, origin, mutation, signed-destination, version, and redaction selectors pass.
- GSD key-link verification passes `1/1`.

## Known Stubs

None. The test-only provider metadata is an intentional negative-control fixture; real sandbox evidence collection is explicitly owned by Plan 28 and cannot be replaced by this fixture.

## Issues Encountered

- The managed workspace roots required approved execution for frontend TypeScript caches, Playwright results, and git index writes. All normal hooks ran; no verification bypass was used.
- No Stripe credential, account, object, webhook, provider call, charge, deployment, or production mutation was attempted. This plan establishes the gate; it does not claim the Plan 28 real sandbox journey has run.

## User Setup Required

None for this plan. Plan 28 must supply authorized real Stripe sandbox coordinates and provider metadata through its explicit execution boundary.

## Next Phase Readiness

- Plan 28 can create `billing-paid-access.spec.ts`, collect real sandbox readiness metadata, and run the hosted Checkout journey through the dependency-gated `stripe-sandbox` project.
- Plan 29 can bind the two frontend commits, preflight receipt, real journey receipt, and 29 focused controls into the aggregate Phase 476 security gate.
- The frontend worktree is clean at `70f2b46`; unrelated backend user changes remain unstaged and untouched.

## TDD Gate Compliance

- RED: `1a455f5` produced the expected failures for the absent preflight script and absent sandbox project while the initial negative-exit assertions passed.
- GREEN: `70f2b46` passes typecheck, lint, all 29 Chromium controls, redaction scans, and the source-link gate.

## Self-Check: PASSED

- FOUND: all three frontend implementation/test artifacts and `476-27-SUMMARY.md`.
- FOUND: RED commit `1a455f5`.
- FOUND: GREEN commit `70f2b46`.
- PASS: typecheck, lint, 29/29 Chromium controls with zero skipped, artifact canary scan, and `git diff --check`.
- PASS: GSD key link verifies `1/1`.
- PASS: frontend worktree is clean; protected backend user files remain unstaged and untouched.

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
