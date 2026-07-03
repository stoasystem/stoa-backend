# Roadmap: v5.8 Email Verification And Login Code Policy

**Status:** Complete
**Created:** 2026-07-03
**Prior milestone:** v5.7 Usage Ledger And Quota Reconciliation

## Goal

Make email verification and login-code behavior explicit, enforceable, and compatible with the existing Cognito-backed account lifecycle.

## Why This Is Its Own Milestone

Account verification affects every role and can easily break onboarding if it is mixed into broader operations-console work. v5.8 isolates the account lifecycle contract first: what verification states exist, what unverified users can do, how resends/expiry behave, and whether login-code behavior is actually production authentication or a deferred placeholder.

## Current Reality

- Registration already stores user profiles and parent/student binding metadata.
- Existing account lifecycle tests mention email verification policy and parent binding behavior.
- Standard Cognito login and forgot-password flows exist.
- Login-code/passwordless behavior needs a clear provider-compatible policy before clients can rely on it.

## Implementation Strategy

- Define the verification state contract before changing auth behavior.
- Preserve current role onboarding and parent/student binding compatibility.
- Enforce email verification only where policy says it is required.
- Add resend/expiry/support visibility after state semantics are clear.
- Decide login-code policy explicitly: implement a safe Cognito-compatible flow or gate/defer it with clear responses.

## Phases

- [x] **Phase 212: Email Verification Contract And Account State Policy** - Define account verification states, route policy, binding implications, and test matrix.
- [x] **Phase 213: Registration Verification Enforcement** - Persist and enforce verification policy through registration/login-compatible account lifecycle paths.
- [x] **Phase 214: Verification Resend And Expiry Operations** - Add resend/expiry behavior and bounded support visibility for verification state.
- [x] **Phase 215: Login Code Policy And Auth Lifecycle Tests** - Implement or explicitly gate login-code/passwordless behavior and protect existing auth lifecycle flows.
- [x] **Phase 216: v5.8 Verification Release Gate** - Close v5.8 with evidence, docs, audit, and v5.9 handoff.

## Phase Details

### Phase 212: Email Verification Contract And Account State Policy

**Goal**: Define verification state semantics before implementation.
**Depends on**: Existing Cognito-backed auth and v5.6/v5.7 account/payment/usage correctness.
**Requirements**: EMAIL-01
**Success Criteria**:

1. Verification states cover registered, unverified, pending verification, verified, expired, resend-limited, and blocked states.
2. Registration/profile response shape for verification status is defined without provider internals.
3. Parent/student binding behavior is explicit for unverified parties.
4. Route-level policy identifies what unverified users can and cannot do.
5. Test matrix is documented for role onboarding, parent binding, and blocked/allowed states.

### Phase 213: Registration Verification Enforcement

**Goal**: Make registration and login-compatible account lifecycle paths follow the verification policy.
**Depends on**: Phase 212.
**Requirements**: EMAIL-02
**Success Criteria**:

1. New registrations record verification policy metadata and initial verification state.
2. Post-registration token/login behavior follows the chosen verification policy.
3. Student, parent, teacher, admin, and tutor-role alias onboarding remain compatible.
4. Parent-student binding creation respects verification-gated access semantics.
5. Focused auth lifecycle tests cover unverified and verified registration states.

### Phase 214: Verification Resend And Expiry Operations

**Goal**: Make verification recovery safe and support-visible.
**Depends on**: Phase 213.
**Requirements**: EMAIL-03
**Success Criteria**:

1. Resend verification is exposed or documented through a Cognito-compatible backend operation.
2. Repeated resend attempts are rate-limited or idempotency-safe.
3. Expired/stale verification state responses are actionable and provider-redacted.
4. Admin/support can inspect bounded verification status.
5. Focused tests cover resend, throttling/idempotency, expiry, and support visibility.

### Phase 215: Login Code Policy And Auth Lifecycle Tests

**Goal**: Resolve login-code/passwordless behavior without breaking standard Cognito flows.
**Depends on**: Phase 214.
**Requirements**: LOGIN-01
**Success Criteria**:

1. Login-code policy is classified as supported, provider-gated, or deferred.
2. Supported login-code flow returns real Cognito-compatible authenticated sessions with expiry/replay/rate-limit protection, or deferred behavior returns clear non-production responses.
3. Existing forgot-password and standard login flows remain backward compatible.
4. Tests prove unsupported/deferred behavior cannot be mistaken for production auth.
5. Auth lifecycle tests cover registration, verification, forgot-password, and login-code policy together.

### Phase 216: v5.8 Verification Release Gate

**Goal**: Close v5.8 as a complete backend account lifecycle milestone.
**Depends on**: Phase 215.
**Requirements**: VERIFY-41
**Success Criteria**:

1. Verification contract, enforcement, resend/expiry operations, login-code policy, and focused tests are complete.
2. Requirements, roadmap, state, and milestone history reflect v5.8 completion.
3. Release evidence identifies commit SHAs, focused tests, lint checks, and residual full-suite status.
4. Final audit records rollout state: `verification-ready`, `policy-deferred`, `blocked`, or `deferred`.
5. v5.9 parent/admin operations visibility handoff is updated.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 212 Email Verification Contract And Account State Policy | v5.8 | 1/1 | Complete | 2026-07-03 |
| 213 Registration Verification Enforcement | v5.8 | 1/1 | Complete | 2026-07-03 |
| 214 Verification Resend And Expiry Operations | v5.8 | 1/1 | Complete | 2026-07-03 |
| 215 Login Code Policy And Auth Lifecycle Tests | v5.8 | 1/1 | Complete | 2026-07-03 |
| 216 v5.8 Verification Release Gate | v5.8 | 1/1 | Complete | 2026-07-03 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EMAIL-01 | Phase 212 | Complete |
| EMAIL-02 | Phase 213 | Complete |
| EMAIL-03 | Phase 214 | Complete |
| LOGIN-01 | Phase 215 | Complete |
| VERIFY-41 | Phase 216 | Complete |

---
*Last updated: 2026-07-03 after v5.8 verification release gate.*
