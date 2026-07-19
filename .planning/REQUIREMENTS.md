# Requirements: v9.0 Web Product Reality, Authorization And Web Functionality Completion

- **Milestone:** v9.0
- **Status:** Planning
- **Created:** 2026-07-14
- **Replanned:** 2026-07-18 after the owner's Web-first product correction
- **Prior milestone:** v8.4 Strategic Scale Reliability And Next-Version Decision
- **Audit baseline:** `de3bf1e4133550e1c679bf611b026437336bd219`
- **Primary evidence:** `docs/audit/full-project-audit.md`, `docs/audit/findings.json`, and the actual Web application in `/Users/zhdeng/stoa-frontend`

## Purpose

Convert STOA from broad local contracts into a trustworthy Web product that can begin early real testing. v9.0 closes every known audit, test-discovered, and launch-blocking defect reachable through the backend or retained production Web route inventory; makes student, parent, teacher, admin/operator, learning, billing, notification, and delivery behavior converge under real failure conditions; and proves one immutable backend/Web release set in browsers. Native client work is explicitly deferred until the Web App has launched for testing and is stable.

## Milestone Outcomes

1. An unauthenticated user cannot provision privileged roles, and every student-specific read/write enforces an authoritative relationship or assignment.
2. Question, practice, teacher, relationship, rate-limit, and billing workflows converge correctly under retries, concurrency, and partial failures.
3. One formal cross-repository gate deterministically verifies backend and Web source, builds each artifact once, deploys the exact release set to staging, and proves protected exact-byte production-promotion plus automatic-rollback semantics through staging and a controlled non-production failure exercise; a real production mutation still requires later explicit operational approval.
4. Real student, parent, teacher, and admin/operator accounts can complete their retained production Web journeys without hidden demo data, placeholder/static success, or intercepted acceptance boundaries; every other production route is intentionally removed or disabled through an executable inventory.
5. Versioned infrastructure, full browser WebSocket delivery, observability, and final browser evidence establish an honest early-testing or hold decision.

## Requirements

### Identity And Authentication

- [x] **V9AUTH-01:** Public registration accepts only explicitly approved self-service roles and rejects `admin`, `teacher`, `tutor`, unknown, and case-variant privileged roles before any Cognito user/group mutation.
- [x] **V9AUTH-02:** A long-lived production admin can be created only through an authenticated operator workflow that records actor, target, timestamp, resulting group, and redacted evidence.
- [x] **V9AUTH-03:** A teacher can join only through an expiring, single-use invitation and explicit approval; teacher identity alone does not grant curriculum-edit capability.
- [x] **V9AUTH-04:** Cognito group, profile role, account status, and capabilities have one reconciliation policy, and token validation performs no best-effort privilege mutation.
- [x] **V9AUTH-05:** Access-token validation enforces issuer, token use, allowed app client, signing-key rotation, cache isolation, and stable redacted authentication errors.
- [ ] **V9AUTH-06:** A Web user can request and confirm a real login code through the authoritative custom-auth/provider flow, receive a real authenticated session, and use expiry, replay prevention, resend/attempt limits, anti-enumeration behavior, and provider-failure handling; no deferred or placeholder response remains, and password registration/sign-in/recovery/session flows continue to work.

### Resource Authorization

- [x] **V9ACCESS-01:** One central authorization policy decides whether an owner student, bound parent, assigned teacher, capability-authorized operator, or admin can access a student resource for a stated purpose.
- [x] **V9ACCESS-02:** Every student, question, practice, adaptive, report, teacher, parent, and admin route that accepts a student/question/resource identifier uses the central policy or documents a stricter policy.
- [x] **V9ACCESS-03:** An automated role-resource matrix proves unrelated parents, unassigned teachers, stale/disabled bindings, wrong capabilities, and cross-user identifiers are denied while legitimate actors remain functional.

### Content Privacy And Practice Integrity

- [x] **V9PRIV-01:** Question OCR accepts only an existing, unconsumed upload owned by the authenticated student and atomically associates it with the created question.
- [x] **V9PRIV-02:** Uploads enforce supported extension/MIME/magic-byte rules, bounded size, lifecycle expiry, post-upload validation, stable errors, and safe failure cleanup.
- [x] **V9PRIV-03:** Student practice preview, overview, path, and lesson responses never expose correct answers or answer-derived explanations before a recorded submission.
- [ ] **V9PRIV-04:** Backend and Web logs omit student/model content, tokens, object keys, provider payloads, and secrets while retaining request IDs, event IDs, sizes, categories, and exception classes.

### Deterministic Cross-Repository Verification And Delivery

- [ ] **V9QUAL-01:** Local formal verification and CI invoke one authoritative cross-repository entry point that creates a fresh Python 3.12 environment from committed `uv.lock` in frozen mode and a clean Web install from committed `package-lock.json`; neither CI nor a developer environment may substitute a weaker gate.
- [ ] **V9QUAL-02:** The complete Python suite passes twice in separate fresh environments, once at a fixed standard time and once at an explicit future fixed time, with deterministic seed/collection identity, ambient AWS credentials denied, non-allowlisted network denied, and exactly zero skip, xfail, or xpass outcomes; unavailable external checks are separate exact `NOT RUN` obligations and never count as passing.
- [ ] **V9QUAL-03:** The actual Web repository passes locked install, ESLint, TypeScript production build, dependency checks, focused backend/OpenAPI contract checks, and Playwright browser suites through the same formal gate; production-critical acceptance is not satisfied by demo login or route-intercepted APIs alone.
- [ ] **V9QUAL-04:** Ruff has zero errors and a full-repository mypy-zero repair attempt is completed before any temporary baseline is proposed; only an explicit owner decision may accept documented irreducible errors, and broad `Any`, exclusions, ignores, or global missing-import suppression are forbidden shortcuts.
- [ ] **V9QUAL-05:** Backend and Web lockfiles have no unaccepted release-blocking advisory: Critical/High block by default and production-reachable Medium also blocks; every temporary exception records exact package/advisory/version, reachability evidence, owner, expiry, and upgrade/removal target.
- [ ] **V9QUAL-06:** Phase 474 implements the minimum versioned cross-repository release infrastructure—staging/production release roles, immutable artifact/evidence storage, Lambda versions and aliases, Web release prefixes/pointers or an equivalent atomic mechanism, protected environments, and rollback authority—then one manifest binds exact backend/Web/infra commits, lock/source identities, runtimes, verification runs, and artifact digests. Artifacts build once, differ only through reviewed runtime configuration, and deploy unchanged to staging; the gate permits unchanged production promotion only after protected owner approval and staging smoke, prohibits bypass, and automatically restores the previously verified set after failed production smoke. Phase 474 proves promotion and rollback semantics through staging plus a controlled non-production failure exercise; the owner's policy selection does not authorize a real production mutation. Actual production promotion/smoke occurs only under later explicit operational approval, otherwise its evidence is exact `NOT RUN` and Phase 474 remains fully enforceable. Emergencies may only restore a previously verified set and hotfixes follow the normal gate. Production evidence, when generated, is retained long term; failed/staging candidates are retained at least 90 days and current/known-good rollback sets indefinitely; every gate change runs intentional-failure/tamper tests.
- [ ] **V9QUAL-07:** Phase 473 evidence publication can be reverified from a later clean metadata HEAD by selecting the explicit candidate and its single direct publication commit, reading the four publication artifacts from immutable Git blobs, and proving the current HEAD descends from that publication without changing those blobs.

### Data Consistency And Concurrency

- [ ] **V9DATA-01:** Question quota, idempotency, usage ledger, upload consumption, and initial question persistence commit atomically or converge through an explicitly tested recovery state.
- [ ] **V9DATA-02:** Concurrent teacher takeover has exactly one winner, one session, and one notification through a conditional/transactional claim.
- [ ] **V9DATA-03:** Parent/student forward and reverse bindings and required profile changes commit transactionally, and a reconciliation tool repairs historical asymmetry idempotently.
- [ ] **V9DATA-04:** Chat, hint, and related rate-limit counters do not increase after rejection; provider failures and retries follow documented consumption/idempotency semantics.
- [ ] **V9DATA-05:** Incorrect practice attempts persist a bounded, display-safe student answer and return it accurately in mistake review while handling legacy rows as unknown.
- [ ] **V9DATA-06:** Every shared parent-profile writer participates in one version/CAS-and-increment contract, or deletion uses a genuinely narrow non-overwriting update, so a stale child scrub cannot lose a concurrent locale, availability, verification, parent-link, or other unrelated profile change.
- [ ] **V9DATA-07:** Notification delivery-begin distinguishes typed conditional/fence loss from transient DynamoDB/provider dependency failure; only proven account-deletion loss may terminalize as `canceled_account_deletion`, while transient failure remains recoverable and a healthy retry can deliver once.
- [ ] **V9DATA-08:** An identical account-deletion retry after a lost successful response returns the stored completed `deleted` receipt through the real endpoint without reopening cleanup, requiring minimized-away branch proof, or producing a replay conflict.

### Billing And Paid Access

- [ ] **V9BILL-01:** Each Web checkout business request carries a required idempotency key that is reused by the backend, Stripe, and durable local command state, producing at most one active provider session.
- [ ] **V9BILL-02:** Provider success with local failure, local success with response timeout, duplicate browser retry, and delayed webhook all reconcile to one support-visible billing state.
- [ ] **V9BILL-03:** Checkout success/cancel URLs are parsed structurally and restricted to configured exact Web origins and approved paths for the current environment.
- [ ] **V9BILL-04:** A Stripe test-mode browser journey proves signed webhook processing changes parent/student effective entitlement and quota exactly once and remains explainable in parent/admin Web views.

### Web Foundation And Contract Convergence

- [ ] **V9WEB-01:** Backend OpenAPI and the Web request/response adapters have one automatically checked casing, enum, required-field, error, and idempotency contract; unexpected write fields fail instead of being silently discarded.
- [ ] **V9WEB-02:** The Web auth and role surface matches the authoritative backend policy: only approved public roles are offered, teacher onboarding is absent from public self-service and any Web entry uses the approved invitation path, tokens restore the correct user/profile, and protected navigation denies role drift without fabricating a demo session.
- [ ] **V9WEB-03:** Staging/production Web configuration fails closed and every retained student, parent, teacher, admin/operator, organization, and public release-path page uses authoritative services for any product, account, learning, billing, or operational truth it presents, with explicit loading, empty, denied, expired-session, dependency-failure, and retry states where applicable; static truth, virtual success, placeholder success, and demo fallback cannot satisfy or mask a release-path result.
- [ ] **V9WEB-04:** A student can use real Web data to sign in, view a meaningful dashboard, upload and submit one question idempotently, receive the AI result, and request teacher help without placeholder or mock-backed success.
- [ ] **V9WEB-05:** A student can navigate a real practice path, submit answers, see result-only feedback, complete a lesson, and review the exact stored mistake answer without any pre-submission answer disclosure.
- [ ] **V9WEB-06:** A parent can sign in, see only bound children, inspect learning/usage/report/entitlement state, start an idempotent Stripe test-mode checkout, and observe the signed billing-state and quota change in the Web App.
- [ ] **V9WEB-07:** Component, adapter-contract, accessibility/responsive-browser, and browser end-to-end tests cover the student and parent critical paths and their failure/retry/session states; final acceptance uses a deployed or local integrated backend and approved provider sandbox rather than replacing those boundaries with Playwright route interception.
- [ ] **V9WEB-08:** An approved teacher can use the real Web queue, assignment/dispatch, takeover, conversation/help context, reply/resolve, and authorized practice-answer paths; assignment/capability boundaries, concurrent-claim loss, stale work, and denied student/resource states remain correct and visible.
- [ ] **V9WEB-09:** An authorized admin/operator can use the retained identity review, account/support, curriculum, report/recovery, billing, moderation/notification, and operational surfaces against real services with capability checks, stable errors, audit evidence, and no placeholder success.
- [ ] **V9WEB-10:** A bounded executable inventory derived from the production router and route groups classifies every public/protected student, parent, teacher, admin/operator, and organization Web route by owner, backend dependency, authorization, state coverage, and evidence; every enabled route is functional against real services and every unready placeholder/demo/static route is intentionally removed or disabled before early testing.

### Infrastructure And Realtime Delivery

- [ ] **V9INFRA-01:** Building on and preserving Phase 474's already-working minimum release topology, authoritative versioned infrastructure audits, defines, imports, or extends the broader staging/production API/Web hosting surfaces, Cognito clients/groups, DynamoDB table/index contracts, S3 policies/lifecycle, queues, WebSocket routes, alarms, and backup/restore configuration required by every retained v9.0 Web route; it does not defer a Phase 474 promotion or rollback prerequisite.
- [ ] **V9INFRA-02:** Authenticated API Gateway `$connect`, `$disconnect`, subscribe/refresh, and notification fanout handlers are deployed with owner/channel authorization, stale cleanup, complete pagination, and redacted delivery evidence.
- [ ] **V9INFRA-03:** The Web client reconnects after browser visibility/network changes, resumes authorized subscriptions, deduplicates and orders events, falls back to bounded polling, and proves one real notification path end to end.

### Operations And Reliability

- [ ] **V9OPS-01:** Liveness, dependency readiness, request/trace correlation, structured redacted logs, latency/error/business metrics, and actionable alarms cover critical auth, question, billing, notification, and Web request paths.
- [ ] **V9OPS-02:** Audited practice, WebSocket, teacher, and admin access paths use exact keys/indexes and complete pagination so first-page or hard-limit truncation cannot silently omit records.
- [ ] **V9OPS-03:** Synthetic and staging browser/API probes exercise the critical Web release set, distinguish dependency degradation from process liveness, retain correlation and alarm evidence, and use a controlled non-production promotion failure to demonstrate the exact automatic rollback action that a failed production smoke would trigger without rebuilding either artifact.

### Closeout And Truth Reconciliation

- [ ] **V9CLOSE-01:** README, `.env.example`, architecture maps, Web release documentation, and milestone vocabulary match clean-checkout commands and distinguish contract, integrated, staging-verified, live-verified, and product-complete states.
- [ ] **V9CLOSE-02:** Critical auth, authorization, usage, billing, realtime, and Web contract changes introduced in v9.0 use testable policy/use-case/repository/adapter boundaries; unrelated full-file rewrites remain deferred with a prioritized debt register.
- [ ] **V9CLOSE-03:** Final audit records backend/Web/infra source SHAs, release-manifest and artifact digests, test/build/dependency results, the complete executable route inventory, all-role request/run IDs and redacted API/provider/browser evidence, finding disposition, staging and controlled non-production promotion/rollback evidence, and an explicit early-testing, internal-only, beta, or production hold decision. If a later explicit operational approval authorizes production promotion/smoke, its approval and results are included; otherwise production promotion/smoke/rollback are exact `NOT RUN` and are not fabricated or treated as Phase 474 failure.

## Definition Of Done

- All 51 requirements are completed with repository evidence and mapped to exactly one phase.
- Completed Phase 472 and 473 requirements remain complete; their evidence is rechecked through the common release candidate rather than reopened or relabeled.
- Every P0/P1 and release-blocking P2 finding reachable in the backend/Web release is closed; each native-only finding is explicitly deferred as native-only and is not represented as fixed.
- The formal Python 3.12 gate passes twice at fixed/future time with zero skip/xfail/xpass and ambient AWS/network denial; Ruff is zero, the full mypy-zero attempt is documented, and backend/Web dependency policy passes.
- One cross-repository manifest proves locked Web verification, integrated student, parent, teacher, and admin/operator browser journeys plus the complete route inventory, versioned infrastructure, staging smoke, protected byte-identical promotion controls, and controlled non-production automatic rollback for the same build-once release set; real production evidence is included only when separately authorized, otherwise recorded exactly as `NOT RUN`.
- The executable Web route inventory proves every retained production route for student, parent, teacher, admin/operator, organization, and public surfaces is real-service functional, or records its intentional removal/disablement; no enabled placeholder/demo/static-success route remains.
- The four Phase 473 follow-up defects have focused regression evidence while Phase 473 itself remains completed.
- No milestone completion is based only on source-string checks, mocks that replace the integration under test, route-intercepted acceptance evidence, local decision-contract output, or a demo fallback.
- Production mutation remains separately approved, scoped, reversible, and evidenced; the owner's approval-policy selection and v9.0 planning do not themselves authorize production promotion/smoke, real charging, bulk notification, or broader rollout.

## Future Requirements

- Native client implementation, dependency repair, native builds, device end-to-end tests, push/offline client behavior, and distribution are deferred until the Web App has launched for testing and demonstrated stable operation; native-only findings `FEATURE-001`, `BUG-003`, `BUG-005`, and `TEST-002` move with that future milestone.
- Broad decomposition of `production_pilot_service.py`, `admin.py`, `subscription_service.py`, and `adaptive_learning_service.py` beyond the v9.0 critical paths.
- Optimization of low-risk scans/access patterns not implicated in correctness, release evidence, or measured load.
- Paid marketing, public launch, additional markets/languages, enterprise sales automation, and school partnership automation.
- Broader AI autonomy, unreviewed assignment generation, and autonomous teacher replacement.
- Additional support/CRM providers, warehouse expansion, and advanced growth analytics not required by the core Web journeys.

## Out Of Scope

- Native client implementation or distribution before the Web App has launched for testing and is stable; the v9.0 release gate covers the backend and actual Web repository only.
- Granting curriculum-edit permission to every teacher; editing remains a separately authorized capability.
- Replacing FastAPI, DynamoDB, Cognito, the Web stack, or the AWS deployment model as a wholesale rewrite.
- Adding microservices, Step Functions, or SQS solely for architectural preference without a demonstrated v9.0 failure mode.
- Hiding failed tests, weakening assertions, ignoring dependency findings, accepting route-intercepted browser evidence as integrated proof, or marking demo/static UI as complete.
- Production writes, customer charging, mass notification, or external rollout without explicit operational approval.

## Requirement Traceability

| Requirement | Phase | Status |
| --- | --- | --- |
| V9AUTH-01 | Phase 472 | Complete |
| V9AUTH-02 | Phase 472 | Complete |
| V9AUTH-03 | Phase 472 | Complete |
| V9AUTH-04 | Phase 472 | Complete |
| V9AUTH-05 | Phase 472 | Complete |
| V9AUTH-06 | Phase 477 | Pending |
| V9ACCESS-01 | Phase 472 | Complete |
| V9ACCESS-02 | Phase 472 | Complete |
| V9ACCESS-03 | Phase 472 | Complete |
| V9PRIV-01 | Phase 473 | Complete |
| V9PRIV-02 | Phase 473 | Complete |
| V9PRIV-03 | Phase 473 | Complete |
| V9PRIV-04 | Phase 480 | Pending |
| V9QUAL-01 | Phase 474 | Complete |
| V9QUAL-02 | Phase 474 | Complete |
| V9QUAL-03 | Phase 474 | Complete |
| V9QUAL-04 | Phase 474 | Complete |
| V9QUAL-05 | Phase 474 | Complete |
| V9QUAL-06 | Phase 474 | Complete |
| V9QUAL-07 | Phase 474 | Complete |
| V9DATA-01 | Phase 475 | Pending |
| V9DATA-02 | Phase 475 | Pending |
| V9DATA-03 | Phase 475 | Pending |
| V9DATA-04 | Phase 475 | Pending |
| V9DATA-05 | Phase 475 | Pending |
| V9DATA-06 | Phase 475 | Pending |
| V9DATA-07 | Phase 475 | Pending |
| V9DATA-08 | Phase 475 | Pending |
| V9BILL-01 | Phase 476 | Pending |
| V9BILL-02 | Phase 476 | Pending |
| V9BILL-03 | Phase 476 | Pending |
| V9BILL-04 | Phase 476 | Pending |
| V9WEB-01 | Phase 477 | Pending |
| V9WEB-02 | Phase 477 | Pending |
| V9WEB-03 | Phase 477 | Pending |
| V9WEB-04 | Phase 478 | Pending |
| V9WEB-05 | Phase 478 | Pending |
| V9WEB-06 | Phase 478 | Pending |
| V9WEB-07 | Phase 478 | Pending |
| V9WEB-08 | Phase 478 | Pending |
| V9WEB-09 | Phase 478 | Pending |
| V9WEB-10 | Phase 478 | Pending |
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

Each of the 31 audit findings has one primary implementation or disposition phase. The audit's native findings retain their original meaning and are explicitly deferred; they are not relabeled as Web defects.

| Phase | Audit findings | Disposition |
| --- | --- | --- |
| Phase 472 | SEC-001, SEC-002, SEC-004 | Complete |
| Phase 473 | SEC-003, SEC-005, BUG-001 | Complete |
| Phase 474 | TEST-001, OPS-001, OPS-002, SEC-007, QUALITY-001 | Implement and verify common backend/Web gate |
| Phase 475 | DATA-001, BUG-002, DATA-003, BUG-006, BUG-004 | Implement and verify data/concurrency closure |
| Phase 476 | DATA-002, SEC-008 | Implement and verify billing closure |
| Phase 477 | FEATURE-003 | Implement the real Web login-code/custom-auth session flow and converge the full supported account lifecycle |
| Phase 478 | None from the original audit | Close the actual Web journey gaps found by current repository inspection |
| Phase 479 | FEATURE-002, OPS-003 | Implement browser realtime and versioned infrastructure |
| Phase 480 | SEC-006, PERF-001, OPS-004 | Implement operational closure |
| Phase 481 | ARCH-001, ARCH-002, DOC-001; native-only FEATURE-001, BUG-003, BUG-005, TEST-002 | Verify truth/debt disposition; native-only findings remain deferred until post-Web stability |

## Known Follow-Up Defect Coverage

Phase 473 remains complete. Its final independent verification documented four genuine non-blocking defects that the owner's all-known-bugs rule now assigns to remaining phases:

| Defect | Requirement | Phase | Required closure evidence |
| --- | --- | --- | --- |
| `profile-version-cas` | V9DATA-06 | Phase 475 | Race the real shared profile writer against deletion scrub and preserve concurrent unrelated bytes through CAS/increment or a narrow update. |
| `delivery-begin-dependency-classification` | V9DATA-07 | Phase 475 | Inject nonconditional dependency failure below `transact_write_items`, retain recoverable state, then prove one healthy retry and correct terminal reason. |
| `completed-deletion-replay` | V9DATA-08 | Phase 475 | Finalize through the real terminal projection, lose the response, replay identical `DELETE /auth/me`, and return the stored receipt with zero new cleanup effects. |
| `final-head-publication-reverification` | V9QUAL-07 | Phase 474 | Verify explicit candidate/publication Git blobs from a later metadata HEAD and reject changed artifacts, non-direct publication, or unrelated ancestry. |
