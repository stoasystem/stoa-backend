# Requirements: v9.0 Product Reality, Authorization And Core Journey Completion

- **Milestone:** v9.0
- **Status:** Planning
- **Created:** 2026-07-14
- **Prior milestone:** v8.4 Strategic Scale Reliability And Next-Version Decision
- **Audit baseline:** `de3bf1e4133550e1c679bf611b026437336bd219`
- **Primary evidence:** `docs/audit/full-project-audit.md` and `docs/audit/findings.json`

## Purpose

Convert STOA from broad local backend/readiness contracts into a trustworthy, installable internal product. v9.0 closes the reachable authorization, privacy, consistency, billing, verification, mobile, infrastructure, and operational gaps identified by the full-project audit. It deliberately prioritizes real student and parent journeys over new market, growth, enterprise, or AI-autonomy scope.

## Milestone Outcomes

1. An unauthenticated user cannot provision privileged roles, and every student-specific read/write enforces an authoritative relationship or assignment.
2. Question, practice, teacher, relationship, rate-limit, and billing workflows converge correctly under retries, concurrency, and partial failures.
3. Python 3.12 tests and delivery gates are deterministic, cloud-isolated, dependency-audited, and required before deployment.
4. The Expo app installs from a lockfile, builds, authenticates through the authoritative backend contract, and provides functional student and parent core journeys rather than placeholder routes.
5. Versioned infrastructure, full WebSocket delivery, observability, staging/rollback, and final evidence establish an honest release decision.

## Requirements

### Identity And Authentication

- [x] **V9AUTH-01:** Public registration accepts only explicitly approved self-service roles and rejects `admin`, `teacher`, `tutor`, unknown, and case-variant privileged roles before any Cognito user/group mutation.
- [x] **V9AUTH-02:** A long-lived production admin can be created only through an authenticated operator workflow that records actor, target, timestamp, resulting group, and redacted evidence.
- [x] **V9AUTH-03:** A teacher can join only through an expiring, single-use invitation and explicit approval; teacher identity alone does not grant curriculum-edit capability.
- [x] **V9AUTH-04:** Cognito group, profile role, account status, and capabilities have one reconciliation policy, and token validation performs no best-effort privilege mutation.
- [x] **V9AUTH-05:** Access-token validation enforces issuer, token use, allowed app client, signing-key rotation, cache isolation, and stable redacted authentication errors.
- [ ] **V9AUTH-06:** A user can request and confirm a real login code with expiry, replay prevention, attempt limits, anti-enumeration behavior, and provider-failure handling; no deferred placeholder response remains.

### Resource Authorization

- [ ] **V9ACCESS-01:** One central authorization policy decides whether an owner student, bound parent, assigned teacher, capability-authorized operator, or admin can access a student resource for a stated purpose.
- [ ] **V9ACCESS-02:** Every student, question, practice, adaptive, report, teacher, parent, and admin route that accepts a student/question/resource identifier uses the central policy or documents a stricter policy.
- [ ] **V9ACCESS-03:** An automated role-resource matrix proves unrelated parents, unassigned teachers, stale/disabled bindings, wrong capabilities, and cross-user identifiers are denied while legitimate actors remain functional.

### Content Privacy And Practice Integrity

- [x] **V9PRIV-01:** Question OCR accepts only an existing, unconsumed upload owned by the authenticated student and atomically associates it with the created question.
- [x] **V9PRIV-02:** Uploads enforce supported extension/MIME/magic-byte rules, bounded size, lifecycle expiry, post-upload validation, stable errors, and safe failure cleanup.
- [x] **V9PRIV-03:** Student practice preview, overview, path, and lesson responses never expose correct answers or answer-derived explanations before a recorded submission.
- [ ] **V9PRIV-04:** Application logs omit student/model content, tokens, object keys, provider payloads, and secrets while retaining request IDs, event IDs, sizes, categories, and exception classes.

### Verification And Delivery Baseline

- [ ] **V9QUAL-01:** A clean checkout creates the documented Python 3.12 environment from `uv.lock`, and local/CI commands use the same target runtime.
- [ ] **V9QUAL-02:** Tests deny ambient AWS/network access by default and use injectable/frozen time for date-sensitive learning, quota, billing, and token behavior.
- [ ] **V9QUAL-03:** The complete Python suite passes twice from a clean target-runtime environment without skipped or weakened assertions.
- [ ] **V9QUAL-04:** Ruff has zero errors and mypy has an explicit non-increasing baseline that separates missing stubs from real contract errors and expands strict coverage on touched modules.
- [ ] **V9QUAL-05:** Locked Python and mobile dependencies have no unaccepted release-blocking advisory; every temporary exception records reachability, owner, expiry, and upgrade target.
- [ ] **V9QUAL-06:** CI runs tests, lint, typing baseline, dependency/security checks, package provenance, and focused contract checks before one immutable artifact can enter any deploy job.

### Data Consistency And Concurrency

- [ ] **V9DATA-01:** Question quota, idempotency, usage ledger, upload consumption, and initial question persistence commit atomically or converge through an explicitly tested recovery state.
- [ ] **V9DATA-02:** Concurrent teacher takeover has exactly one winner, one session, and one notification through a conditional/transactional claim.
- [ ] **V9DATA-03:** Parent/student forward and reverse bindings and required profile changes commit transactionally, and a reconciliation tool repairs historical asymmetry idempotently.
- [ ] **V9DATA-04:** Chat, hint, and related rate-limit counters do not increase after rejection; provider failures and retries follow documented consumption/idempotency semantics.
- [ ] **V9DATA-05:** Incorrect practice attempts persist a bounded, display-safe student answer and return it accurately in mistake review while handling legacy rows as unknown.

### Billing And Paid Access

- [ ] **V9BILL-01:** Each checkout business request has a required idempotency key that is reused for Stripe and local command state, producing at most one active provider session.
- [ ] **V9BILL-02:** Provider success with local failure, local success with response timeout, duplicate retry, and delayed webhook all reconcile to one support-visible billing state.
- [ ] **V9BILL-03:** Checkout success/cancel URLs are parsed structurally and restricted to configured exact origins and approved paths for the current environment.
- [ ] **V9BILL-04:** A Stripe test-mode journey proves signed webhook processing changes parent/student effective entitlement and quota exactly once and remains explainable in parent/admin views.

### Installable Mobile Foundation

- [ ] **V9MOB-01:** The Expo dependency matrix is valid and committed with a lockfile; clean install, `expo-doctor`, TypeScript, iOS build, and Android build use documented commands.
- [ ] **V9MOB-02:** Mobile registration, verification, sign-in, session restore, sign-out, and role navigation use the authoritative backend/Cognito contract without orphan identities or role-name drift.
- [ ] **V9MOB-03:** Mobile request/response types are generated from or automatically checked against OpenAPI, use one casing policy, and fail on unexpected write fields instead of silently ignoring them.
- [ ] **V9MOB-04:** A student can sign in, see a real dashboard, upload/submit a question idempotently, view the AI result, request teacher help, complete practice, and review mistakes on iOS and Android.
- [ ] **V9MOB-05:** A parent can sign in, see only bound children, inspect learning/usage/entitlement state, start checkout, and see signed billing-state changes on iOS and Android.
- [ ] **V9MOB-06:** Verification, resend, password reset, login code, loading, empty, offline, retry, expired-session, and denied-access states are functional UI states rather than explanatory placeholder text.
- [ ] **V9MOB-07:** Component, navigation, API-contract, native-build, and device end-to-end tests cover the student and parent critical paths and run in the release gate.

### Infrastructure And Realtime Delivery

- [ ] **V9INFRA-01:** Authoritative versioned infrastructure defines or imports Lambda, API Gateway, Cognito clients/groups, DynamoDB table/index contracts, S3 policies/lifecycle, queues, WebSocket routes, alarms, and backup/restore configuration required by v9.0.
- [ ] **V9INFRA-02:** Authenticated API Gateway `$connect`, `$disconnect`, subscribe/refresh, and notification fanout handlers are deployed with owner/channel authorization, stale cleanup, complete pagination, and redacted delivery evidence.
- [ ] **V9INFRA-03:** Mobile reconnects after foreground/network changes, resumes subscriptions, deduplicates/out-of-order events, falls back safely, and proves one real notification path end to end.

### Operations And Reliability

- [ ] **V9OPS-01:** Liveness, dependency readiness, request/trace correlation, structured redacted logs, latency/error/business metrics, and actionable alarms cover critical auth, question, billing, notification, and mobile API paths.
- [ ] **V9OPS-02:** Audited practice, WebSocket, teacher, and admin access paths use exact keys/indexes and complete pagination so first-page or hard-limit truncation cannot silently omit records.
- [ ] **V9OPS-03:** A tested artifact deploys to staging/versioned Lambda aliases, passes API/provider/mobile smoke, and can be rolled back without rebuilding or changing the artifact digest.

### Closeout And Truth Reconciliation

- [ ] **V9CLOSE-01:** README, `.env.example`, architecture maps, mobile release documentation, and milestone vocabulary match clean-checkout commands and distinguish contract, integrated, live-verified, and product-complete states.
- [ ] **V9CLOSE-02:** Critical auth, authorization, usage, billing, and realtime changes introduced in v9.0 use testable policy/use-case/repository boundaries; unrelated full-file rewrites remain deferred with a prioritized debt register.
- [ ] **V9CLOSE-03:** Final audit records source/deploy SHAs, artifact digests, test/build/dependency results, request IDs, redacted API/browser/device evidence, finding disposition, rollback evidence, and an explicit internal-only/beta/production decision.

## Definition Of Done

- All 44 requirements are completed with repository evidence and mapped to exactly one phase.
- `SEC-001` and `SEC-002` are fixed and independently regression-tested before any broader rollout work.
- Every P0/P1 finding is closed; every release-blocking P2 is closed or explicitly accepted by an owner with evidence and expiry.
- Python 3.12 verification, clean mobile install/build, native critical-path E2E, infrastructure diff/deploy, staging smoke, and rollback all pass on one traceable release candidate.
- No milestone completion is based only on source-string checks, mocks that replace the integration under test, or local decision-contract output.
- Production mutation remains separately approved, scoped, reversible, and evidenced; v9.0 planning does not itself authorize it.

## Future Requirements

- Broad decomposition of `production_pilot_service.py`, `admin.py`, `subscription_service.py`, and `adaptive_learning_service.py` beyond the v9.0 critical paths.
- Optimization of low-risk scans/access patterns not implicated in correctness, release evidence, or measured load.
- Paid marketing, public launch, additional markets/languages, enterprise sales automation, and school partnership automation.
- Broader AI autonomy, unreviewed assignment generation, and autonomous teacher replacement.
- Additional support/CRM providers, warehouse expansion, and advanced growth analytics not required by the core journeys.

## Out Of Scope

- Granting curriculum-edit permission to every teacher; editing remains a separately authorized capability.
- Replacing FastAPI, DynamoDB, Cognito, Expo, or the AWS deployment model as a wholesale rewrite.
- Adding microservices, Step Functions, or SQS solely for architectural preference without a demonstrated v9.0 failure mode.
- Hiding failed tests, weakening assertions, ignoring dependency findings, or marking placeholder UI as complete.
- Production writes, customer charging, mass notification, or external rollout without explicit operational approval.

## Requirement Traceability

| Requirement | Phase | Status |
| --- | --- | --- |
| V9AUTH-01 | Phase 472 | Complete |
| V9AUTH-02 | Phase 472 | Complete |
| V9AUTH-03 | Phase 472 | Complete |
| V9AUTH-04 | Phase 472 | Complete |
| V9AUTH-05 | Phase 472 | Complete |
| V9AUTH-06 | Phase 478 | Pending |
| V9ACCESS-01 | Phase 472 | Complete |
| V9ACCESS-02 | Phase 472 | Complete |
| V9ACCESS-03 | Phase 472 | Complete |
| V9PRIV-01 | Phase 473 | Complete |
| V9PRIV-02 | Phase 473 | Complete |
| V9PRIV-03 | Phase 473 | Complete |
| V9PRIV-04 | Phase 480 | Pending |
| V9QUAL-01 | Phase 474 | Pending |
| V9QUAL-02 | Phase 474 | Pending |
| V9QUAL-03 | Phase 474 | Pending |
| V9QUAL-04 | Phase 474 | Pending |
| V9QUAL-05 | Phase 474 | Pending |
| V9QUAL-06 | Phase 474 | Pending |
| V9DATA-01 | Phase 475 | Pending |
| V9DATA-02 | Phase 475 | Pending |
| V9DATA-03 | Phase 475 | Pending |
| V9DATA-04 | Phase 475 | Pending |
| V9DATA-05 | Phase 475 | Pending |
| V9BILL-01 | Phase 476 | Pending |
| V9BILL-02 | Phase 476 | Pending |
| V9BILL-03 | Phase 476 | Pending |
| V9BILL-04 | Phase 476 | Pending |
| V9MOB-01 | Phase 477 | Pending |
| V9MOB-02 | Phase 477 | Pending |
| V9MOB-03 | Phase 477 | Pending |
| V9MOB-04 | Phase 478 | Pending |
| V9MOB-05 | Phase 478 | Pending |
| V9MOB-06 | Phase 478 | Pending |
| V9MOB-07 | Phase 478 | Pending |
| V9INFRA-01 | Phase 479 | Pending |
| V9INFRA-02 | Phase 479 | Pending |
| V9INFRA-03 | Phase 479 | Pending |
| V9OPS-01 | Phase 480 | Pending |
| V9OPS-02 | Phase 480 | Pending |
| V9OPS-03 | Phase 480 | Pending |
| V9CLOSE-01 | Phase 481 | Pending |
| V9CLOSE-02 | Phase 481 | Pending |
| V9CLOSE-03 | Phase 481 | Pending |

## Audit Finding Coverage

Each audit finding has one primary implementation/disposition phase. Cross-phase dependencies remain documented in the roadmap.

| Phase | Audit findings |
| --- | --- |
| Phase 472 | SEC-001, SEC-002, SEC-004 |
| Phase 473 | SEC-003, SEC-005, BUG-001 |
| Phase 474 | TEST-001, OPS-001, OPS-002, SEC-007, QUALITY-001 |
| Phase 475 | DATA-001, BUG-002, DATA-003, BUG-006, BUG-004 |
| Phase 476 | DATA-002, SEC-008 |
| Phase 477 | FEATURE-001, BUG-003, BUG-005, TEST-002 |
| Phase 478 | FEATURE-003 |
| Phase 479 | FEATURE-002, OPS-003 |
| Phase 480 | SEC-006, PERF-001, OPS-004 |
| Phase 481 | ARCH-001, ARCH-002, DOC-001 |
