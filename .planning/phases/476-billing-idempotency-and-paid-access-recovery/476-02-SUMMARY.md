---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 02
subsystem: payments
tags: [stripe, urllib, pydantic, open-redirect, exact-origin]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Canonical opaque checkout reference and non-authoritative browser outcome contracts from Plan 01
provides:
  - Structurally parsed current-environment checkout Web origin policy
  - Fixed-path success and cancel URL construction with opaque checkout references
  - Route and service rejection of browser-supplied callback authority
affects: [476-03, 476-05, 476-06, 476-23, 476-24, billing, stripe-checkout]

tech-stack:
  added: []
  patterns:
    - Parse trusted URL configuration structurally and canonicalize before equality
    - Build provider callback URLs solely from validated server settings
    - Reject browser callback fields at the Pydantic route boundary

key-files:
  created:
    - src/stoa/services/billing_callback_service.py
    - tests/test_billing_callback_urls.py
  modified:
    - src/stoa/config.py
    - src/stoa/services/subscription_service.py
    - src/stoa/routers/parents.py
    - tests/test_subscription_operations.py
    - .env.example

key-decisions:
  - "Production and staging accept only canonical HTTPS DNS origins with the default HTTPS port; development accepts only explicitly configured localhost, 127.0.0.1, or [::1] origins with explicit ports."
  - "The only approved callback path is /billing/checkout/result, and callback query data is limited to checkoutRef plus flow=return|cancel."
  - "Browser successUrl and cancelUrl fields are forbidden at the route boundary and absent from the checkout service signature."

patterns-established:
  - "Exact-origin configuration: reject userinfo, paths, queries, fragments, wildcards, encoded delimiters, backslashes, lookalikes, and ambiguous ports before URL construction."
  - "Server callback authority: Settings plus a backend-generated opaque reference are the complete callback-builder input."

requirements-completed: [V9BILL-03]

duration: 8min
completed: 2026-07-24
---

# Phase 476 Plan 02: Exact Checkout Callback Origins Summary

**Stripe checkout return URLs now come only from startup-validated exact environment origins and one fixed result path, with browser callback authority removed from the active route and service.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-24T07:35:48Z
- **Completed:** 2026-07-24T07:44:05Z
- **Tasks:** 1
- **Files modified:** 7

## Accomplishments

- Added structural origin parsing for exact production, staging, and explicit development loopback origin-port tuples.
- Added startup validation that rejects missing, duplicate, wrong-environment, ambiguous, or non-fixed callback configuration.
- Added fixed success/cancel URL construction carrying only an opaque `checkoutRef` and non-authoritative `flow` hint.
- Removed legacy full success/cancel URL settings and the permissive prefix-based `_safe_url` implementation.
- Removed browser callback fields from the parent checkout model and service signature, with forbidden-extra validation at the API boundary.
- Proved the SEC-008 positive/negative matrix with 56 focused tests and preserved all 35 adjacent subscription-operation tests.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-02-01 RED: Add failing callback origin security matrix** - `8dd3ca5` (test)
2. **Task 476-02-01 GREEN: Enforce exact checkout callback origins** - `7df150c` (feat)

## Files Created/Modified

- `src/stoa/services/billing_callback_service.py` - Exact-origin policy, parser, and fixed-path return URL builder.
- `tests/test_billing_callback_urls.py` - Production/staging/local positive controls and every D-12 bypass class.
- `src/stoa/config.py` - Current-environment origin list, fixed result path, and startup policy validation.
- `src/stoa/services/subscription_service.py` - Server-built callbacks and new readiness configuration projection.
- `src/stoa/routers/parents.py` - Checkout request model without browser callback fields.
- `tests/test_subscription_operations.py` - Explicit exact production origin in the legacy billing test fixture.
- `.env.example` - Explicit production, staging, and loopback development callback examples.

## Decisions Made

- Canonical HTTPS default port `443` is normalized away; non-default production/staging ports are rejected.
- Production/staging origins must be DNS names rather than IP literals or loopback addresses.
- Development origins must be exact loopback hosts with explicit ports; LAN addresses, `0.0.0.0`, lookalikes, and missing ports are rejected.
- Configured origin ordering selects the primary callback origin deterministically; every configured entry must independently validate and canonical duplicates are forbidden.
- Opaque checkout references use a bounded ASCII token alphabet and cannot inject URL authority, path, query, or fragment data.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Removed browser callback authority from the active checkout boundary**
- **Found during:** Task 476-02-01 GREEN adjacent verification
- **Issue:** Replacing Settings alone left the existing parent route and subscription service accepting `successUrl`/`cancelUrl`, which would preserve the SEC-008 bypass and caused legacy setting lookups to fail.
- **Fix:** Removed callback fields from the route model and service signature, forbade extra request fields, routed checkout creation through the server-owned builder, removed `_safe_url`, and updated readiness fields.
- **Files modified:** `src/stoa/routers/parents.py`, `src/stoa/services/subscription_service.py`, `tests/test_billing_callback_urls.py`
- **Verification:** Callback-field model validation fails; the service signature has no callback inputs; 56 focused and 35 adjacent tests pass.
- **Committed in:** `7df150c`

**2. [Rule 1 - Bug] Rejected port zero explicitly**
- **Found during:** Task 476-02-01 GREEN focused verification
- **Issue:** The first port-range expression treated integer port `0` as an absent port because of Python truthiness.
- **Fix:** Distinguished `None` from integer ports before applying the inclusive 1..65535 bound.
- **Files modified:** `src/stoa/services/billing_callback_service.py`
- **Verification:** The complete unsafe-origin matrix, including ports `0` and `65536`, passes.
- **Committed in:** `7df150c`

**3. [Rule 1 - Bug] Migrated the production billing fixture to explicit origin configuration**
- **Found during:** Task 476-02-01 GREEN adjacent verification
- **Issue:** Strict startup validation correctly refused legacy production test Settings that omitted the new required exact origin.
- **Fix:** Added the exact production Web origin to the shared subscription-operation Settings fixture.
- **Files modified:** `tests/test_subscription_operations.py`
- **Verification:** `tests/test_subscription_operations.py` passes 35/35.
- **Committed in:** `7df150c`

---

**Total deviations:** 3 auto-fixed (1 missing critical security boundary, 2 directly caused regressions).
**Impact on plan:** The fixes complete the planned SEC-008 boundary and preserve adjacent billing behavior without expanding provider access or production authority.

## Security Verification

- Production and staging reject HTTP, loopback, IP literals, non-default ports, userinfo, paths, trailing slash, query, fragment, wildcard, scheme-relative, encoded delimiter, backslash, and malformed authority inputs.
- Development accepts only explicitly configured `localhost`, `127.0.0.1`, and `[::1]` origin-port tuples.
- Exact policy comparison rejects arbitrary HTTPS, lookalike hosts, missing/extra ports, and unconfigured candidates.
- Callback construction accepts only `checkout_ref` and Settings; no request, header, forwarded authority, or browser URL parameter exists.
- The fixed path and query projection are asserted structurally for both return and cancel flows.
- All T-476-02-H mitigations have passing local selectors; no High threat remains unresolved in this plan’s source boundary.
- The aggregate `scripts/verify_phase476_security_gate.py` does not exist yet and remains owned by a later Phase 476 plan; no aggregate phase-gate claim is made here.

## Known Stubs

None introduced. The current legacy checkout path generates a backend-owned opaque navigation reference; later durable-command plans bind that reference to persistent reconciliation state.

## Issues Encountered

- Removing the legacy full URL settings exposed their remaining active callers. They were migrated to the exact-origin builder before the GREEN commit.
- The aggregate Phase 476 security-gate script is not yet present, so this plan records only its focused source-bound evidence.

## User Setup Required

- Configure `STRIPE_CHECKOUT_WEB_ORIGINS` to the exact current-environment Web origin list before staging or production startup.
- Keep `STRIPE_CHECKOUT_RESULT_PATH=/billing/checkout/result`.
- No credentials, provider calls, real charges, deployment, or production mutation were required.

## Next Phase Readiness

- Durable checkout commands can pass their persisted opaque reference directly to `build_checkout_return_urls()`.
- Plan identity/config convergence can reuse the new environment-specific startup policy.
- Web checkout requests must continue omitting callback URLs; later Web plans can use the fixed result route only.

## Self-Check: PASSED

- FOUND: `src/stoa/services/billing_callback_service.py`
- FOUND: `tests/test_billing_callback_urls.py`
- FOUND: `8dd3ca5`
- FOUND: `7df150c`
- PASS: focused and adjacent verification (`91 passed`)
- PASS: Ruff on all implementation and test files changed by the task

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
