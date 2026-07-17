# Roadmap: v9.0 Product Reality, Authorization And Core Journey Completion

- **Status:** Planned
- **Created:** 2026-07-14
- **Prior milestone:** v8.4 Strategic Scale Reliability And Next-Version Decision
- **Audit baseline:** `de3bf1e4133550e1c679bf611b026437336bd219`
- **Requirements:** 44 across 10 phases
- **Phase range:** 472-481

## Goal

Turn STOA's broad local contracts into a trustworthy, installable internal product. v9.0 first closes reachable privilege escalation and cross-student access, then restores deterministic verification and data consistency, completes paid access and mobile core journeys, integrates versioned infrastructure/WebSocket operations, and finishes with traceable release evidence.

## Why This Milestone Exists

The full-project audit found that implementation breadth and planning volume overstate real product maturity. The backend contains meaningful functionality, but two P0 authorization failures, nine P1 blockers, twelve failing tests, non-atomic business writes, a direct-to-production deployment workflow, and a non-buildable placeholder mobile client prevent an honest beta or production expansion claim.

v9.0 is therefore a product-completion milestone, not another readiness-contract milestone. It does not add broad new business scope. It makes the existing account, learning, teacher, billing, notification, and mobile promises work together under real contracts and failure conditions.

## Release Boundary

- P0 and P1 findings are mandatory closure items. They cannot be accepted as normal residual risk.
- Release-blocking P2 findings must be fixed or receive explicit, time-bounded owner acceptance supported by reachability evidence.
- Curriculum editing remains capability-authorized; the milestone must not grant all teachers mutation rights.
- Production writes, real charging, bulk notification, and user expansion require separate approved operational execution even after code completion.
- Public launch, paid marketing, new markets, enterprise automation, and expanded AI autonomy remain out of scope.

## Execution Order

| Phase | Name | Primary outcome | Depends on |
| --- | --- | --- | --- |
| 472 | Privileged Identity And Student Resource Authorization | Complete — 22/22 plans, independently verified 2026-07-15 | Audit baseline |
| 473 | 18/35 | In Progress|  |
| 474 | Deterministic Verification And Gated Delivery | Green Python 3.12 baseline and pre-deploy gates | Phase 472; can overlap 473 |
| 475 | Transactional Usage Assignment And Relationship Consistency | Correct multi-write, retry, and concurrency behavior | Phase 474 |
| 476 | Billing Idempotency And Paid Access Recovery | One checkout/entitlement outcome under failures and retries | Phase 474; can overlap 475 |
| 477 | Installable Mobile Foundation And Contract Convergence | Clean Expo build with authoritative auth/API contracts | Phases 472 and 474 |
| 478 | Student Parent Core Mobile Journey Completion | Functional account, learning, practice, and paid-access journeys | Phases 473, 475, 476, 477 |
| 479 | Versioned Infrastructure And Full WebSocket Integration | Reproducible cloud resources and realtime delivery | Phases 474 and 477 |
| 480 | Operational Observability Pagination And Release Resilience | Detectable, complete, staged, rollback-capable operations | Phases 474 and 479 |
| 481 | Product Reality Gate And Milestone Audit | Reconcile evidence and make an honest release decision | Phases 478 and 480 |

## Phases

- [x] **Phase 472: Privileged Identity And Student Resource Authorization** (completed 2026-07-15)
- [ ] **Phase 473: Student Content Privacy And Practice Integrity** (17/35 plans executed; Plans 18-35 planned and checker-verified 2026-07-17)
- [ ] **Phase 474: Deterministic Verification And Gated Delivery**
- [ ] **Phase 475: Transactional Usage Assignment And Relationship Consistency**
- [ ] **Phase 476: Billing Idempotency And Paid Access Recovery**
- [ ] **Phase 477: Installable Mobile Foundation And Contract Convergence**
- [ ] **Phase 478: Student Parent Core Mobile Journey Completion**
- [ ] **Phase 479: Versioned Infrastructure And Full WebSocket Integration**
- [ ] **Phase 480: Operational Observability Pagination And Release Resilience**
- [ ] **Phase 481: Product Reality Gate And Milestone Audit**

## Phase Details

### Phase 472: Privileged Identity And Student Resource Authorization

**Goal:** Close unauthenticated privileged provisioning and cross-student authorization defects before any additional product integration.

**Why now:** `SEC-001` and `SEC-002` are reachable P0 issues. Continuing feature work while these paths remain open would expand the blast radius and invalidate later browser/mobile evidence.

**Depends on:** Full-project audit at `de3bf1e`.

**Requirements:** V9AUTH-01, V9AUTH-02, V9AUTH-03, V9AUTH-04, V9AUTH-05, V9ACCESS-01, V9ACCESS-02, V9ACCESS-03.

**Audit findings:** SEC-001, SEC-002, SEC-004.

**Plans:** 22/22 plans complete

**Wave 0**

1. `472-01` — Security contracts, safe client actions, and Wave 0 test surfaces.

**Wave 1** *(blocked on Wave 0 completion)*

2. `472-02` — Token verification and explicit identity resolution.
3. `472-03` — Public privilege barrier and canonical `teacher` terminology.

**Wave 2** *(blocked on Wave 1 completion)*

4. `472-04` — Versioned capabilities and privileged identity lifecycles.

**Wave 3** *(blocked on Waves 1–2 completion)*

5. `472-05` — Central actor-resource-action-purpose authorization policy.

**Wave 4** *(blocked on Wave 3 completion)*

6. `472-06` — Student, question, and conversation route migration.
7. `472-07` — Practice, adaptive, and parent route migration.
8. `472-08` — Teacher, assistance, conversation, and AI-tool route migration.
9. `472-09` — Admin capability and notification-resource route migration.

**Wave 5** *(blocked on Wave 4 completion)*

10. `472-10` — Executable route inventory, dry-run reconciliation, and P0 evidence.

**Wave 6** *(gap closure; blocked on Wave 5 completion)*

11. `472-11` — Canonical public identity registration and token-bound login.
12. `472-12` — Conflict-wide capability quarantine and non-revival proof.
14. `472-14` — Durable authorization decisions and bounded probe evidence.

**Wave 7** *(blocked on Plan 472-11)*

13. `472-13` — Recursive dependency identifier inventory and explicit public route declarations.

**Wave 8** *(blocked on Plans 472-11 and 472-13)*

15. `472-15` — Safe structured public Cognito error boundary.

**Wave 9** *(blocked on Plans 472-11 through 472-15)*

16. `472-16` — Gap-closure integration, regression, and evidence gate.

**Wave 10** *(second gap closure; blocked on Plan 472-16)*

17. `472-17` — Proof-bound existing-account registration resume and immutable-command verification resend.
18. `472-18` — Full grant-coordinate reconciliation and collision-safe non-revival evidence.
19. `472-19` — Typed scalar and collection admin body-target authorization with all-of audit evidence.
21. `472-21` — Strong, unique production authorization-audit HMAC keyring validation.

**Wave 11** *(blocked on Plan 472-17)*

20. `472-20` — Account-state-indistinguishable password recovery and reset responses.

**Wave 12** *(blocked on Plans 472-17 through 472-21)*

22. `472-22` — Six-finding integration, deterministic regression, and source-bound evidence gate.

**Success criteria:**

1. Public registration and confirmation cannot create or promote admin or teacher accounts, including rejected historical role aliases and case variants.
2. The existing formal production-admin workflow remains functional, audited, and outside public registration.
3. Teacher onboarding requires an expiring one-time approval and does not imply curriculum-edit permission.
4. Unrelated parents and unassigned teachers receive indistinguishable `404 resource_not_found` responses when they are not allowed to know a resource exists; `403 action_not_allowed` is used only when resource existence is knowable but the requested action is forbidden.
5. Owner students, active bound parents, assigned teachers, capability-authorized operators, and admins retain only their intended access.
6. Wrong-client, wrong-pool, ID-token, unknown-key rotation, and Cognito/JWKS outage tests produce stable fail-closed behavior.

**Required evidence:** Focused pytest, generated OpenAPI route authorization inventory, local TestClient reproductions showing the old P0 payloads now denied, redacted Cognito sandbox group/profile evidence, and no production mutation.

**Exit gate:** Both P0 findings are closed. Phase 473/474 may not be marked complete while either remains open.

### Phase 473: Student Content Privacy And Practice Integrity

**Goal:** Ensure student uploads and exercise previews cannot expose another user's content or answers.

**Why now:** Mobile question upload and practice work cannot be completed safely while server-side ownership and response boundaries are missing.

**Depends on:** Phase 472 actor identity and resource-authorization policy.

**Requirements:** V9PRIV-01, V9PRIV-02, V9PRIV-03.

**Audit findings:** SEC-003, SEC-005, BUG-001.

**Likely plan slices:**

1. Upload intent/owner/status records, constrained presign policy, post-upload validation, expiry, and consumption rules.
2. Atomic upload-to-question association with foreign/reused/missing object refusal.
3. Separate practice preview/result schemas and update all student-facing curriculum routes/clients.

**Execution plans:**

**Wave 1**

- [x] `473-01` — Define closed upload/attachment/error and answer preview/result contracts with Wave 0 fixtures.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `473-02` — Implement constrained upload intents, authoritative validation, quota accounting, and lifecycle rules.
- [x] `473-05` — Remove answers from every student preview and persist attempts before answer-bearing results.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] `473-03` — Persist conversation attachments, enable owner reuse, bounded extraction, and reference-aware retention.
- [x] `473-04` — Replace raw question object keys with atomic owner-validated attachment/OCR association.
- [x] `473-06` — Add assignment-scoped teacher and global admin answer-read contracts without mutation authority.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] `473-07` — Add expired-upload cleanup and run the combined privacy/practice security evidence gate.

**Wave 5** *(gap closure; blocked on Wave 4 completion)*

- [x] `473-08` — Replace direct S3 POST disclosure with an authenticated chunk gateway and promote exact validated bytes to server-only immutable storage.

**Wave 6** *(complete)*

- [x] `473-09` — Map transaction cancellation operations to stable quota, dependency, and concealed-resource outcomes with zero-effect races.

**Wave 7** *(complete)*

- [x] `473-10` — Add replayable conversation commands, atomic chat quota idempotency, and private-safe AI/conversation telemetry.

**Wave 8** *(execution complete; independent verification found new gaps)*

- [x] `473-11` — Re-run all privacy and authorization gates and regenerate final source-bound evidence and validation artifacts.

**Wave 9** *(gap closure; blocked on Wave 8 completion)*

- [x] `473-12` — Make upload provider mutations crash-recoverable and delete every exact unreferenced staging and immutable target before cleanup completion.

**Wave 10** *(gap closure; blocked on Wave 9 completion)*

- [x] `473-13` — Close deterministic attachment identity, structured gateway dependency error, and provider-body lifetime gaps with adversarial tests.

**Wave 11** *(final evidence; blocked on Wave 10 completion)*

- [x] `473-14` — Lock the remediated source, run all retained gates, and publish complete redacted evidence bound to one immutable tested SHA.

**Wave 12** *(gap closure; blocked on Wave 11 completion)*

- [x] `473-15` — Reject malformed provider success coordinates, preserve recovery fences, and isolate cleanup candidates.

**Wave 13** *(gap closure; blocked on Wave 12 completion)*

- [x] `473-16` — Close every provider response body and normalize conversation repository transport failures.

**Wave 14** *(final evidence; blocked on Wave 13 completion)*

- [x] `473-17` — Lock the remediated source and regenerate exhaustive redacted evidence for the remaining gaps.

**Wave 15** *(final gap closure; blocked on Wave 14 completion)*

- [ ] `473-18` — Enforce exact multipart acknowledgements, ledger-bound recovery, and create-only checksum-verified promotion.
- [ ] `473-25` — Bind results to immutable attempt snapshots and replace free-form hints with a closed non-derivable template policy.

**Wave 16** *(blocked on Wave 15 completion)*

- [ ] `473-19` — Prove exact multipart/object absence across retries, pagination, intent TTL, cleanup debt, and PART lifecycle.
- [ ] `473-26` — Require an exact current teacher course/class assignment for answer reads while keeping admin access read-only.

**Wave 17** *(blocked on Wave 16 completion)*

- [ ] `473-20` — Replace ambiguous conversation outcomes with one typed durable command, quota, usage, retry, and transport contract.
- [ ] `473-24` — Add semantic passive-document validation and resource-isolated bounded extraction for every supported type.

**Wave 18** *(blocked on Wave 17 completion)*

- [ ] `473-21` — Reconstruct exact replay attachments/history, fence AI leases, and keep extraction/provider failures retryable.

**Wave 19** *(blocked on Wave 18 completion)*

- [ ] `473-22` — Make resource release and deletion exhaustive, fenced, paginated, reconciled, and crash-resumable.

**Wave 20** *(blocked on Wave 19 completion)*

- [ ] `473-23` — Deliver owner list/view/download/delete APIs and a durable exact attachment-purge branch.

**Wave 21** *(blocked on Wave 20 completion)*

- [ ] `473-29` — Add the permanent self-delete fence, replay-only post-fence authorization, and profile/question/OCR/upload closure.

**Wave 22** *(blocked on Wave 21 completion)*

- [ ] `473-30` — Fence and scrub every moderation summary, history, event, note, and derived private-content writer.

**Wave 23** *(blocked on Wave 22 completion)*

- [ ] `473-31` — Reconcile all report/recovery/support rows, exact S3 versions, SES sends, and lawful-retention exceptions.

**Wave 24** *(blocked on Wave 23 completion)*

- [ ] `473-32` — Purge and fence conversations, messages, command results, teacher notes, help state, AI completion, and attachment links.

**Wave 25** *(blocked on Wave 24 completion)*

- [ ] `473-33` — Purge and fence practice answers/progress/mistakes, adaptive assignments/memory, and student analytics signals.

**Wave 26** *(blocked on Wave 25 completion)*

- [ ] `473-34` — Purge notification/assistance/draft copies, revoke device/realtime credentials, and stop pending external deliveries.

**Wave 27** *(blocked on Wave 26 completion)*

- [ ] `473-35` — Source-discover and seal all 17 private-store branches, retained-evidence policy, zero debt, and two zero epochs.

**Wave 28** *(blocked on Wave 27 completion)*

- [ ] `473-27` — Fail closed on unregistered private writes and unstrict provider/repository/parser response consumption.

**Wave 29** *(final evidence; blocked on Wave 28 completion)*

- [ ] `473-28` — Test one immutable candidate with strict receipts and publish independently revalidated source-bound evidence.

**Cross-cutting constraints:**

- Public responses, logs, and errors expose opaque IDs and safe categories only—never object keys, provider coordinates, raw OCR, extracted text, or parser/provider exceptions.
- Upload consumption, attachment association, reference changes, quota accounting, and attempt recording are conditional, atomic, and retry-idempotent.
- Student preview contracts stay answer-free; answer-bearing results require a successfully recorded attempt, while teacher/admin answer reads use a separate scoped contract.
- Client upload responses expose only opaque application identifiers; provider multipart coordinates and ETags remain server-only, and all downstream reads/deletes bind to the immutable validated version.
- Exact conversation retries converge before attachment resolution, while new foreign or missing references create zero command, quota, association, provider, or AI effects.
- One permanent canonical account fence precedes every student-private write; provider-accepted copies and lawful retained evidence remain explicit policy states and never count as physically purged.
- Every private mutation belongs to the source-sealed 17-branch registry, a narrow retained-evidence policy, or a reviewed non-student exclusion; deletion completes only after zero debt and two authoritative zero epochs.
- Every untrusted provider/repository/parser field crosses a named strict parser; new raw coercions, unchecked fields, and unmapped private sinks fail deterministic inventories.
- Final evidence is generated only after source and tests are committed, and every local gate runs against that unchanged candidate SHA.

**Success criteria:**

1. A student can upload a supported bounded file and use it once in their own question.
2. Foreign, malformed, missing, expired, oversized, mismatched, and reused uploads are denied with stable redacted errors.
3. No student preview/overview/path/lesson response contains `correctAnswer` or answer-derived explanation before submission.
4. Authorized teacher/admin tooling retains an explicit answer-bearing contract separate from the student contract.
5. Existing question responses continue to hide object keys and raw OCR text.

**Required evidence:** Upload/object ownership matrix, content validation fixtures, S3 error redaction test, OpenAPI response checks, and student preview snapshots.

**Exit gate:** Question upload and practice preview contracts are safe enough for mobile implementation.

### Phase 474: Deterministic Verification And Gated Delivery

**Goal:** Replace the red, environment-dependent baseline with repeatable Python 3.12 verification and a CI path that cannot deploy unverified source.

**Why now:** Data, billing, and mobile changes cannot be trusted while twelve tests fail and the current workflow deploys every main push without quality gates.

**Depends on:** Phase 472 security behavior and focused regressions; may proceed in parallel with Phase 473 after P0 fixes land.

**Requirements:** V9QUAL-01, V9QUAL-02, V9QUAL-03, V9QUAL-04, V9QUAL-05, V9QUAL-06.

**Audit findings:** TEST-001, OPS-001, OPS-002, SEC-007, QUALITY-001.

**Likely plan slices:**

1. Python 3.12 pin, clean `uv` bootstrap, deny-network/AWS fixture, injected clock, and repair of the twelve failing tests.
2. Ruff zero, classified mypy baseline, vulnerable dependency upgrades/removals, and Linux-arm64 package import validation.
3. Verify/build separation, immutable artifact manifest/digest, protected deploy prerequisites, and intentional-failure CI tests.

**Success criteria:**

1. A clean checkout creates the target environment with one documented command.
2. The full Python suite passes twice with no AWS credentials/network and with a future frozen date.
3. Ruff is clean; mypy records a non-increasing baseline and touched critical modules pass their configured strict level.
4. Dependency scans have no unaccepted release blocker and every exception has reachability evidence and expiry.
5. A stale source hash, failed test, failed lint/type baseline, or failed dependency check prevents deploy jobs from receiving an artifact.
6. The fresh Linux-arm64 Lambda package imports/boots in a compatible runtime and its digest is tied to source SHA.

**Required evidence:** Exact commands/results, repeated test logs, dependency report, Linux artifact smoke, CI run IDs, artifact digest, and a deliberately failed gate.

**Exit gate:** All subsequent implementation uses this baseline; direct unverified main-to-production deployment is disabled.

### Phase 475: Transactional Usage Assignment And Relationship Consistency

**Goal:** Make the core learning and relationship writes converge under partial failure, retry, and concurrency.

**Why now:** Incorrect quota/ledger state, duplicate teacher sessions, asymmetric parent binding, and inflated rate counters damage product behavior even when requests return normal-looking responses.

**Depends on:** Phase 474 deterministic failure-injection baseline.

**Requirements:** V9DATA-01, V9DATA-02, V9DATA-03, V9DATA-04, V9DATA-05.

**Audit findings:** DATA-001, BUG-002, DATA-003, BUG-006, BUG-004.

**Likely plan slices:**

1. Transactional question quota/idempotency/ledger/upload/question state plus reconciliation of historical partial records.
2. Conditional teacher claim/session/notification and transactional parent-child binding with repair tooling.
3. Capped/idempotent rate-limit semantics and complete practice-attempt answer persistence.

**Success criteria:**

1. Identical question retries create one question, consume one quota unit, and emit one ledger event after any tested timeout/failure point.
2. Two concurrent teacher takeovers produce one successful owner, one session, one notification, and a deterministic 409 loser.
3. Parent/student forward and reverse bindings cannot commit one-sided; historical repair is dry-run capable and idempotent.
4. Repeated 429 responses do not increase counters beyond the configured limit and provider failure behavior is explicit.
5. Mistake review returns the submitted wrong answer and safely represents historical unknown answers.

**Required evidence:** DynamoDB transaction/failure-injection tests, barrier concurrency tests, reconciliation dry-run/apply fixtures, quota boundary tests, and mistake round trips.

**Exit gate:** Usage and relationship state are trustworthy enough for paid access and mobile UI.

### Phase 476: Billing Idempotency And Paid Access Recovery

**Goal:** Ensure one parent checkout request produces one recoverable provider/local billing and entitlement outcome.

**Why now:** Paid access is a core business journey and cannot rely on optimistic provider success followed by unrelated local writes.

**Depends on:** Phase 474 verification; uses Phase 475 idempotency/transaction conventions. May be implemented in parallel with Phase 475 after conventions are fixed.

**Requirements:** V9BILL-01, V9BILL-02, V9BILL-03, V9BILL-04.

**Audit findings:** DATA-002, SEC-008.

**Likely plan slices:**

1. Durable checkout command/idempotency key and deterministic Stripe idempotency propagation.
2. Ambiguous provider/local failure reconciliation, delayed/duplicate event behavior, and support-visible state.
3. Exact callback origin allowlist and Stripe test-mode entitlement/quota end-to-end verification.

**Success criteria:**

1. Concurrent or retried identical checkout requests return/recover one provider session.
2. Provider success followed by local failure is discoverable and reconciles without a second customer charge/session.
3. Delayed, duplicate, and out-of-order signed webhooks cannot regress active entitlement.
4. Lookalike, encoded, credential-bearing, wrong-port, and arbitrary HTTPS callback URLs are refused.
5. A Stripe test-mode checkout and signed webhook changes parent/student effective entitlement and quota exactly once and appears in bounded support views.

**Required evidence:** Stripe sandbox request/event IDs, failure-injection results, local/provider reconciliation rows, parent/admin API result, and no live charge.

**Exit gate:** Paid access has an end-to-end sandbox proof suitable for the real mobile parent journey.

### Phase 477: Installable Mobile Foundation And Contract Convergence

**Goal:** Establish a reproducible Expo application that uses the same identity and API contracts as the backend.

**Why now:** The current mobile client cannot install, typecheck, or provision a backend-compatible account; screen work on that foundation would be throwaway.

**Depends on:** Phases 472 and 474.

**Requirements:** V9MOB-01, V9MOB-02, V9MOB-03.

**Audit findings:** FEATURE-001, BUG-003, BUG-005, TEST-002.

**Likely plan slices:**

1. Supported Expo SDK/version matrix, missing assets, lockfile, clean install, doctor, TypeScript, and native build baseline.
2. Backend-authoritative registration/verification/sign-in/restore/sign-out and normalized role/client behavior.
3. Generated/OpenAPI-validated client types, casing convergence, strict write models, and runtime adapter tests.

**Success criteria:**

1. Clean locked install and `expo-doctor` pass on documented Node/npm versions.
2. TypeScript, iOS, and Android internal builds pass without generated files or undeclared local dependencies.
3. A sandbox student and parent register/verify/sign in and restore the correct role/profile through the backend contract.
4. Mobile question idempotency and push-device fields arrive under the exact server model names.
5. Contract tests import and execute adapters; source-string checks are retained only as a cheap supplementary layer.

**Required evidence:** Lockfile, environment matrix, build IDs, auth request IDs, `/auth/me` results, OpenAPI compatibility report, and redacted internal build artifacts.

**Exit gate:** Mobile is installable and contract-correct before functional journey work starts.

### Phase 478: Student Parent Core Mobile Journey Completion

**Goal:** Replace placeholder routes with complete student and parent account, learning, practice, and paid-access workflows.

**Why now:** This is the main product-value phase. Previous milestones produced adapters and readiness contracts, but users still cannot complete the real journeys in the native client.

**Depends on:** Phases 473, 475, 476, and 477.

**Requirements:** V9AUTH-06, V9MOB-04, V9MOB-05, V9MOB-06, V9MOB-07.

**Audit findings:** FEATURE-003 and the functional completion portion of FEATURE-001.

**Likely plan slices:**

1. Real login-code backend/provider flow plus registration, verification, resend, reset, session, and recovery UI.
2. Student dashboard, upload/question/AI/teacher-help, practice/answer/mistake, and retry/offline states.
3. Parent bound-child, learning/usage/entitlement, checkout/billing-state, and denied-access states.
4. Component/navigation/API/device E2E matrix on iOS and Android.

**Success criteria:**

1. Login code produces a real authenticated session with expiry, anti-replay, attempt-limit, anti-enumeration, and provider-failure tests.
2. A student completes the question and practice journeys on both platforms without placeholder cards or demo fallback.
3. A parent sees only bound children and completes the Stripe test-mode paid-access journey with updated entitlement/quota.
4. Loading, empty, offline, retry, expired-session, permission-denied, provider-blocked, and partial-failure states are actionable and do not hide errors.
5. Device E2E proves state across app restart, network interruption, duplicate submit, and session refresh.

**Required evidence:** iOS/Android build IDs, device screenshots/video where useful, API/provider request IDs, redacted account IDs, component results, and end-to-end run logs.

**Exit gate:** Core mobile product can be used internally by real sandbox accounts without hidden fallback behavior.

### Phase 479: Versioned Infrastructure And Full WebSocket Integration

**Goal:** Make the cloud resources and realtime delivery path reproducible from versioned definitions and functional end to end.

**Why now:** Backend WebSocket services cannot become a product feature without API Gateway route handlers, authorization, scalable connection access patterns, and a reconnecting client.

**Depends on:** Phases 474 and 477; coordinates with the mobile notification surface from Phase 478.

**Requirements:** V9INFRA-01, V9INFRA-02, V9INFRA-03.

**Audit findings:** FEATURE-002, OPS-003.

**Likely plan slices:**

1. Import/define authoritative AWS resources, DynamoDB access patterns, Cognito clients/groups, S3 lifecycle, queues, alarms, and backup configuration in IaC.
2. Authenticated WebSocket connect/disconnect/subscribe/refresh handlers, indexed/paginated fanout, stale cleanup, and delivery evidence.
3. Mobile reconnect/resubscribe/dedupe/out-of-order/fallback behavior and deployed notification smoke.

**Success criteria:**

1. A clean staging environment can be synthesized/diffed and all v9.0 runtime resource assumptions are represented or explicitly imported.
2. Unauthorized connection/channel access is denied; owner subscriptions survive token refresh/reconnect without broad fanout.
3. More than 500 connections and multiple pages are handled without silent omission.
4. A durable notification event reaches the intended mobile account once after reconnect and duplicate/out-of-order delivery attempts.
5. Unused uploads, stale connections, backup configuration, and restore ownership are visible in versioned infrastructure/runbooks.

**Required evidence:** IaC synth/diff/deploy IDs, resource contract tests, WebSocket connection/request IDs, multi-page load fixture, mobile reconnect smoke, and rollback plan.

**Exit gate:** Full WebSocket is either demonstrably integrated or the milestone remains incomplete; a local service contract is not sufficient.

### Phase 480: Operational Observability Pagination And Release Resilience

**Goal:** Make critical failures detectable and critical reads complete, then prove staged promotion and rollback of the tested artifact.

**Why now:** Final product evidence is not credible if health is static, logs leak content, reads truncate at page limits, or deployment cannot promote/rollback the exact tested artifact.

**Depends on:** Phases 474 and 479.

**Requirements:** V9PRIV-04, V9OPS-01, V9OPS-02, V9OPS-03.

**Audit findings:** SEC-006, PERF-001, OPS-004.

**Likely plan slices:**

1. Liveness/readiness, request/trace correlation, structured redacted logging, metrics, provider timeouts, and alarms.
2. Exact-key/index and pagination correction for audited practice, WebSocket, teacher, and admin paths with load/cost evidence.
3. Staging/versioned Lambda deployment, API/provider/mobile smoke, alias promotion, and rollback using one immutable digest.

**Success criteria:**

1. Student/model text, tokens, object keys, and provider payloads do not appear in captured logs; request/event correlation remains sufficient for support.
2. Readiness fails appropriately during dependency degradation while liveness remains semantically correct.
3. Multi-page fixtures return complete stable results and no audited path silently truncates at DynamoDB's first page or a hard fanout limit.
4. Synthetic auth/question/billing/notification failures produce actionable metrics/alarms and link to a runbook.
5. The exact tested artifact moves through staging smoke and alias promotion and can be rolled back without rebuild.

**Required evidence:** Log-redaction captures, correlation IDs, metrics/alarm synthetic IDs, pagination/load results, deploy run IDs, artifact digest, smoke request IDs, and rollback run.

**Exit gate:** Operational evidence supports the final product-reality audit.

### Phase 481: Product Reality Gate And Milestone Audit

**Goal:** Reconcile source, tests, builds, infrastructure, API, browser/device, provider, and finding evidence into one honest v9.0 release decision.

**Why now:** The prior completion illusion came from equating local contracts with live product behavior. v9.0 closes only when the integrated journeys and release mechanics are proven.

**Depends on:** Phases 478 and 480; all earlier phase verifications must be current for the same release candidate.

**Requirements:** V9CLOSE-01, V9CLOSE-02, V9CLOSE-03.

**Audit findings:** ARCH-001, ARCH-002, DOC-001; disposition verification for all 31 audit findings.

**Likely plan slices:**

1. Documentation/configuration/architecture truth reconciliation and clean-checkout proof.
2. Bounded critical-path boundary cleanup, residual debt register, and cross-module regression review.
3. Final audit, release checklist, read-only production smoke where approved, rollback evidence, and milestone archive/decision.

**Success criteria:**

1. README, environment template, architecture maps, mobile docs, requirements, roadmap, and state match the executable system and use honest completion vocabulary.
2. Critical v9.0 policy/use-case/repository boundaries are testable without a broad unrelated rewrite; remaining oversized-module work has owner, trigger, and priority.
3. Every one of the 31 audit findings is closed, explicitly accepted with evidence/expiry, or deferred to a named future milestone; no P0/P1 remains open.
4. One evidence index ties source/deploy SHA, artifact digest, test/build/dependency results, infrastructure deploy IDs, API/provider request IDs, and redacted browser/device results.
5. Final decision is explicit: internal-only continuation, limited beta, production hold, or production-ready. Missing evidence produces hold, not a completion claim.

**Required evidence:** `481-VERIFICATION.md`, v9.0 milestone audit, release checklist, clean-checkout log, evidence index, current `findings.json` disposition, and updated project/roadmap/state/milestone archive.

**Exit gate:** v9.0 is archived only after the final audit and decision are complete.

## Requirement Coverage

| Phase | Requirements | Count |
| --- | --- | ---: |
| 472 | V9AUTH-01..05, V9ACCESS-01..03 | 8 |
| 473 | V9PRIV-01..03 | 3 |
| 474 | V9QUAL-01..06 | 6 |
| 475 | V9DATA-01..05 | 5 |
| 476 | V9BILL-01..04 | 4 |
| 477 | V9MOB-01..03 | 3 |
| 478 | V9AUTH-06, V9MOB-04..07 | 5 |
| 479 | V9INFRA-01..03 | 3 |
| 480 | V9PRIV-04, V9OPS-01..03 | 4 |
| 481 | V9CLOSE-01..03 | 3 |
| **Total** | **All milestone requirements mapped exactly once** | **44** |

## Audit Finding Coverage

| Phase | Findings | Count |
| --- | --- | ---: |
| 472 | SEC-001, SEC-002, SEC-004 | 3 |
| 473 | SEC-003, SEC-005, BUG-001 | 3 |
| 474 | TEST-001, OPS-001, OPS-002, SEC-007, QUALITY-001 | 5 |
| 475 | DATA-001, BUG-002, DATA-003, BUG-006, BUG-004 | 5 |
| 476 | DATA-002, SEC-008 | 2 |
| 477 | FEATURE-001, BUG-003, BUG-005, TEST-002 | 4 |
| 478 | FEATURE-003 | 1 |
| 479 | FEATURE-002, OPS-003 | 2 |
| 480 | SEC-006, PERF-001, OPS-004 | 3 |
| 481 | ARCH-001, ARCH-002, DOC-001 | 3 |
| **Total** | **All audit findings assigned one primary phase** | **31** |

## Milestone Risks

| Risk | Response |
| --- | --- |
| Scope is large | P0/P1 closure and real core journeys are mandatory; unrelated features and broad refactors are explicitly excluded. |
| Existing tests reveal more defects | Treat newly confirmed correctness/security defects as milestone inputs; do not weaken tests to preserve schedule. |
| Mobile Expo versions require migration | Lock one supported matrix in Phase 477 before implementing screens; do not code against an unbuildable manifest. |
| IaC lives outside this repository | Import or link the authoritative source and record cross-repository SHAs; do not claim reproducibility from prose. |
| Provider approvals block live proof | Use approved sandbox/test-mode evidence and produce an explicit production hold; never fabricate live evidence. |
| P0 fixes affect existing accounts | Inventory and reconcile existing Cognito groups/profiles with reversible scripts and dry-run evidence. |
| Full WebSocket scope expands operations | Keep it in one bounded phase with a hard end-to-end gate; local service tests alone do not close it. |

## Next Command

Start with Phase 472 context and planning:

`$gsd-discuss-phase 472`

Then create executable plans:

`$gsd-plan-phase 472`
