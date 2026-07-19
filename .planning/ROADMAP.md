# Roadmap: v9.0 Web Product Reality, Authorization And Web Functionality Completion

- **Status:** Planned
- **Created:** 2026-07-14
- **Replanned:** 2026-07-18 after the owner's Web-first product correction
- **Prior milestone:** v8.4 Strategic Scale Reliability And Next-Version Decision
- **Audit baseline:** `de3bf1e4133550e1c679bf611b026437336bd219`
- **Requirements:** 51 across 10 phases
- **Phase range:** 472-481

## Goal

Turn STOA's broad local contracts into a trustworthy Web product that can begin early real testing. v9.0 closes reachable privilege escalation and cross-student access, restores deterministic cross-repository verification, fixes every known audit/test/follow-up consistency and billing defect, completes the actual student, parent, teacher, and admin/operator Web journeys, closes or intentionally removes every production route, integrates versioned infrastructure and browser realtime delivery, and finishes with one traceable release decision.

## Why This Milestone Exists

The full-project audit found that implementation breadth and planning volume overstate real product maturity. The backend contains meaningful functionality, but two P0 authorization failures, nine P1 blockers, twelve failing tests, non-atomic business writes, and direct-to-production backend/frontend workflows prevent an honest beta or production expansion claim. The audit also found a non-buildable placeholder native client; the owner has explicitly deferred that separate product surface until the Web App has launched for testing and is stable.

v9.0 is therefore a Web product-completion milestone, not another readiness-contract milestone. It does not add broad new business scope. It makes the existing account, learning, teacher, admin/operator, billing, and notification behavior work together through the real Vite/React Web application and backend under real contracts and failure conditions, and it disables any route that cannot honestly meet that boundary.

## Release Boundary

- Backend/Web-reachable P0 and P1 findings are mandatory closure items. Native-only findings are explicitly deferred under the owner-approved product correction and cannot be presented as fixed.
- Release-blocking P2 findings must be fixed or receive explicit, time-bounded owner acceptance supported by reachability evidence.
- Every known audit, test-discovered, Phase 473 follow-up, or launch-blocking defect reachable through the backend or retained production Web route inventory is milestone scope; undiscovered theoretical defects are not implied by this bounded commitment.
- Curriculum editing remains capability-authorized; the milestone must not grant all teachers mutation rights.
- Production writes, real charging, bulk notification, and user expansion require separate approved operational execution even after code completion.
- One formal gate owns both repositories: build once, deploy the exact set automatically to staging, implement protected owner approval for unchanged production promotion, prohibit bypass, retain evidence, and implement automatic rollback for failed production smoke. Phase 474 proves these semantics through staging and a controlled non-production failure; actual production mutation requires later explicit operational approval or remains exact `NOT RUN`.
- Public launch, paid marketing, new markets, enterprise automation, and expanded AI autonomy remain out of scope.

## Execution Order

| Phase | Name | Primary outcome | Depends on |
| --- | --- | --- | --- |
| 472 | Privileged Identity And Student Resource Authorization | Complete — 22/22 plans, independently verified 2026-07-15 | Audit baseline |
| 473 | Student Content Privacy And Practice Integrity | Complete — 40/40 plans, independently verified 2026-07-18 | Phase 472 |
| 474 | Deterministic Verification And Gated Delivery | In Progress — 2/80 plans executed | Phases 472 and 473 |
| 475 | Transactional Usage Assignment And Relationship Consistency | Correct multi-write, retry, and concurrency behavior | Phase 474 |
| 476 | Billing Idempotency And Paid Access Recovery | One checkout/entitlement outcome under failures and retries | Phase 474; can overlap 475 |
| 477 | Web Foundation And Contract Convergence | Authoritative Web auth/API/config behavior without hidden demo truth | Phases 472, 473, and 474 |
| 478 | Complete Web Role Journeys And Route Closure | Functional student, parent, teacher, admin/operator, organization, and public browser routes | Phases 475, 476, and 477 |
| 479 | Broader Versioned Infrastructure And Browser WebSocket Integration | Audit/extend cloud resources and deliver browser realtime without deferring Phase 474 prerequisites | Phases 474 and 477 |
| 480 | Operational Observability Pagination And Release Resilience | Detectable, complete operations exercised through the common release set | Phases 475, 476, and 479 |
| 481 | Web Product Reality Gate And Milestone Audit | Reconcile backend/Web/infra evidence and make an honest early-testing decision | Phases 478 and 480 |

## Phases

- [x] **Phase 472: Privileged Identity And Student Resource Authorization** (completed 2026-07-15) - Privileged identity and student-resource access fail closed.
- [x] **Phase 473: Student Content Privacy And Practice Integrity** (completed 2026-07-18 — 40/40 plans, independently verified) - Uploads, private content, and practice answers respect the completed safety boundary.
- [ ] **Phase 474: Deterministic Verification And Gated Delivery** - One formal backend/Web gate and its minimum CDK release topology control one immutable staged release set.
- [ ] **Phase 475: Transactional Usage Assignment And Relationship Consistency** - Core learning and relationship state converges under failure and concurrency.
- [ ] **Phase 476: Billing Idempotency And Paid Access Recovery** - One Web checkout produces one recoverable provider and entitlement outcome.
- [ ] **Phase 477: Web Foundation And Contract Convergence** - Web identity, API, and release configuration match authoritative backend contracts.
- [ ] **Phase 478: Complete Web Role Journeys And Route Closure** - Every retained route works for real student, parent, teacher, and admin/operator accounts or is intentionally disabled.
- [ ] **Phase 479: Broader Versioned Infrastructure And Browser WebSocket Integration** - Broader versioned cloud resources deliver authorized realtime browser notifications without owning Phase 474 prerequisites.
- [ ] **Phase 480: Operational Observability Pagination And Release Resilience** - Critical failures are detectable, reads are complete, and rollback behavior is exercised.
- [ ] **Phase 481: Web Product Reality Gate And Milestone Audit** - One evidence index produces an honest early-testing or hold decision.

## Phase Details

### Phase 472: Privileged Identity And Student Resource Authorization

**Goal:** Close unauthenticated privileged provisioning and cross-student authorization defects before any additional product integration.

**Why now:** `SEC-001` and `SEC-002` are reachable P0 issues. Continuing feature work while these paths remain open would expand the blast radius and invalidate later browser evidence.

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

**Why now:** Web question upload and practice work cannot be completed safely while server-side ownership and response boundaries are missing.

**Depends on:** Phase 472 actor identity and resource-authorization policy.

**Requirements:** V9PRIV-01, V9PRIV-02, V9PRIV-03.

**Audit findings:** SEC-003, SEC-005, BUG-001.

**Plans:** 40/40 plans complete

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

- [x] `473-33` — Purge and fence practice answers/progress/mistakes, adaptive assignments/memory, and student analytics signals.

**Wave 26** *(blocked on Wave 25 completion)*

- [x] `473-34` — Purge notification/assistance/draft copies, revoke device/realtime credentials, and stop pending external deliveries.

**Wave 27** *(blocked on Wave 26 completion)*

- [x] `473-35` — Source-discover and seal all 17 private-store branches, retained-evidence policy, zero debt, and two zero epochs.

**Wave 28** *(blocked on Wave 27 completion)*

- [ ] `473-27` — Fail closed on unregistered private writes and unstrict provider/repository/parser response consumption.

**Wave 29** *(final evidence; blocked on Wave 28 completion)*

- [ ] `473-28` — Test one immutable candidate with strict receipts and publish independently revalidated source-bound evidence.

**Wave 30** *(gap closure; blocked on Wave 29 completion)*

- [x] `473-36` — Fence account-deletion claims, branch evidence, finalization, lifecycle timestamps, and parent-profile scrubbing with exact CAS.
- [x] `473-37` — Add a crash-safe delivery-intent state machine that separates recoverable pre-effect claims from ambiguous provider acceptance.

**Wave 31** *(blocked on Wave 30 completion)*

- [x] `473-38` — Resolve private delivery ownership authoritatively, fail closed on missing metadata, and fence digest, push, and WebSocket effects.

**Wave 32** *(blocked on Wave 31 completion)*

- [x] `473-39` — Refresh source-sealed inventories and lower-bound selectors for deletion leases, delivery ownership, timestamps, parent CAS, and intent recovery.

**Wave 33** *(final evidence; blocked on Wave 32 completion)*

- [x] `473-40` — Capture one immutable candidate and publish clean, source-bound evidence that independently closes all remaining verification findings.

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

**Exit gate:** Question upload and practice preview contracts are safe enough for Web journey implementation.

### Phase 474: Deterministic Verification And Gated Delivery

**Goal:** Make it impossible for unverified backend or Web source to reach staging or production, while preserving one reproducible release identity and the minimum versioned release infrastructure from clean verification through rollback.

**Why now:** The audit found a red test/type/dependency baseline and direct-to-production backend/Web workflows. Phase 474 establishes the common trustworthy delivery boundary before later Web functionality phases consume it.

**Depends on:** Completed Phases 472 and 473.

**Requirements:** V9QUAL-01, V9QUAL-02, V9QUAL-03, V9QUAL-04, V9QUAL-05, V9QUAL-06, V9QUAL-07.

**Audit findings:** TEST-001, OPS-001, OPS-002, SEC-007, QUALITY-001.

**Plans:** 2/80 plans executed

Plans:

**Wave 1**

- [ ] `474-01` — Automated execution-time clean candidate preflight.

**Wave 2**

- [ ] `474-02` — Canonical gate and receipt contract.
- [ ] `474-04` — Later-HEAD Phase 473 publication reverification.

**Wave 3**

- [ ] `474-03` — Fresh hermetic Python verification.
- [ ] `474-06` — Cross-repository manifest and reproducible backend artifact.

**Wave 4**

- [ ] `474-05` — Dependency policy and measured advisory repair.
- [ ] `474-26` — Immutable release storage and scoped roles.

**Wave 5**

- [ ] `474-07` — Mypy-zero closure for identity, JWKS, token, and public-auth boundaries.
- [ ] `474-23` — Web dependency remediation.
- [ ] `474-39` — Mypy-zero closure for authorization metadata, route inventory, and reconciliation.
- [ ] `474-77` — Published Lambda versions and environment aliases.

**Wave 6**

- [ ] `474-08` — Mypy-zero closure for identity, capability, and user repositories.
- [ ] `474-09` — Mypy-zero closure for DynamoDB attachment question and usage repositories.
- [ ] `474-10` — Mypy-zero closure for curriculum and AI-operations repositories.
- [ ] `474-40` — Mypy-zero closure for privileged activation and security-audit repositories.
- [ ] `474-41` — Mypy-zero closure for report persistence.
- [ ] `474-42` — Mypy-zero closure for notification and realtime repositories.
- [ ] `474-43` — Mypy-zero closure for account-deletion repository.
- [ ] `474-44` — Mypy-zero closure for adaptive-learning and practice repositories.
- [ ] `474-45` — Mypy-zero closure for moderation repository.
- [ ] `474-72` — Closed Web runtime-configuration contract.
- [ ] `474-78` — Actually served immutable Web release pointer.

**Wave 7**

- [ ] `474-11` — Mypy-zero closure for report lifecycle artifact and recovery services.
- [ ] `474-12` — Mypy-zero closure for AI provider and operations services.
- [ ] `474-13` — Mypy-zero closure for curriculum adaptive-learning and profile services.
- [ ] `474-14` — Mypy-zero closure for WebSocket and notification delivery services.
- [ ] `474-15` — Mypy-zero closure for auth router.
- [ ] `474-19` — Mypy-zero closure for security fixtures.
- [ ] `474-46` — Mypy-zero closure for attachment validation extraction and OCR services.
- [ ] `474-47` — Mypy-zero closure for subscription service.
- [ ] `474-48` — Mypy-zero closure for support routing and SLA services.
- [ ] `474-49` — Mypy-zero closure for production-pilot and moderation services.
- [ ] `474-50` — Mypy-zero closure for AI-teacher and teacher-assistance services.
- [ ] `474-51` — Mypy-zero closure for account-deletion orchestration service.
- [ ] `474-52` — Mypy-zero closure for teacher-application router.
- [ ] `474-59` — Mypy-zero closure for identity authorization and privileged-reconciliation tests.
- [ ] `474-73` — Web runtime configuration bootstrap.

**Wave 8**

- [ ] `474-16` — Mypy-zero closure for practice and student routers.
- [ ] `474-17` — Mypy-zero closure for parent and conversation routers.
- [ ] `474-18` — Mypy-zero closure for weekly-report upload-cleanup and deletion jobs.
- [ ] `474-21` — Mypy-zero closure for Phase 473 account and notification deletion fixtures.
- [ ] `474-53` — Mypy-zero closure for admin and teacher routers.
- [ ] `474-54` — Mypy-zero closure for question and file routers.
- [ ] `474-55` — Mypy-zero closure for notification router.
- [ ] `474-60` — Mypy-zero closure for attachment-security tests.
- [ ] `474-61` — Mypy-zero closure for public identity and auth-boundary tests.
- [ ] `474-62` — Mypy-zero closure for auth account-lifecycle tests.
- [ ] `474-63` — Mypy-zero closure for usage-ledger and subscription tests.
- [ ] `474-68` — Mypy-zero closure for Phase 473 delivery recovery and provider-state fixtures.
- [ ] `474-69` — Mypy-zero closure for Phase 473 document and saved-attachment fixtures.
- [ ] `474-71` — Mypy-zero closure for Phase 473 report-deletion fixture.

**Wave 9**

- [ ] `474-20` — Mypy-zero closure for conversation and parent route tests.
- [ ] `474-56` — Mypy-zero closure for operator and practice-seed scripts.
- [ ] `474-57` — Mypy-zero closure for Phase 473 inventory generators.
- [ ] `474-58` — Mypy-zero closure for authorization audit and route-inventory tests.
- [ ] `474-64` — Mypy-zero closure for file route tests.
- [ ] `474-65` — Mypy-zero closure for report and question tests.
- [ ] `474-66` — Mypy-zero closure for adaptive-learning and practice tests.
- [ ] `474-67` — Mypy-zero closure for Phase 473 practice authorization and snapshot fixtures.
- [ ] `474-70` — Mypy-zero closure for Phase 473 conversation and message-command fixtures.

**Wave 10**

- [ ] `474-22` — Automated repository-wide mypy-zero gate and report.

**Wave 11**

- [ ] `474-24` — Subordinate Web and OpenAPI verifier.

**Wave 12**

- [ ] `474-74` — Strict release Playwright result policy.

**Wave 13**

- [ ] `474-75` — Measured Web browser-baseline repair.

**Wave 14**

- [ ] `474-25` — Non-intercepted real-staging Web acceptance.
- [ ] `474-27` — Durable two-pointer delivery coordinator.

**Wave 15**

- [ ] `474-28` — Thin exact-ref infrastructure workflow.
- [ ] `474-76` — Thin exact-ref frontend workflows.

**Wave 16**

- [ ] `474-29` — Frontend repository source handoff.
- [ ] `474-30` — Infrastructure repository source handoff.

**Wave 17**

- [ ] `474-32` — Backend delivery workflow and environment controller.

**Wave 18**

- [ ] `474-31` — Backend source identity handoff.

**Wave 19**

- [ ] `474-33` — Read-only live environment and CDK inventory.

**Wave 20**

- [ ] `474-34` — Staging-only immutable CDK substrate.
- [ ] `474-79` — GitHub protected environments only.

**Wave 21**

- [ ] `474-80` — Owner verification of GitHub and staging evidence. *(blocking checkpoint)*

**Wave 22**

- [ ] `474-35` — Live staging delivery smoke and controlled rollback.

**Wave 23**

- [ ] `474-36` — Integrated intentional-failure matrix.

**Wave 24**

- [ ] `474-37` — Final multi-source coverage audit.

**Wave 25**

- [ ] `474-38` — Final evidence sealing and later-HEAD reverification.

**Success criteria:**

1. One authoritative command verifies exact clean backend/Web/infra identities; Python runs twice in fresh 3.12 frozen environments with zero skip/xfail/xpass and ambient AWS/network denial.
2. Ruff is zero, the complete 435-error mypy-zero attempt is executed across every preserved file family, and dependency policy covers backend/Web locks without broad suppression or mobile substitution.
3. Backend and Web artifacts build once; one manifest binds execution-derived source/tree/lock/gate/artifact/config identities and byte-identical staging use.
4. Protected environments implement sole-owner/self-approval semantics; a verified staging-only immutable substrate is applied before live staging delivery and smoke.
5. A controlled nonproduction failure automatically restores both Lambda and Web pointers with durable evidence; all production infrastructure/deploy/smoke/rollback operations remain exact `NOT RUN` absent later explicit approval.
6. Phase 473 publication reverifies from a later clean metadata HEAD using immutable Git blobs.

**Required evidence:** Three repository source receipts; two-clock gate receipts; quality/dependency/Web/CDK/workflow results; protected-environment owner verification; `staging-substrate.json`; live staging delivery/smoke; controlled rollback; failure matrix; source audit; final evidence index.

**Exit gate:** All 89 task rows and the full gate pass, staging and rollback evidence are live and source-bound, production mutation remains exact `NOT RUN`, and zero source-audit item is missing.

### Phase 475: Transactional Usage Assignment And Relationship Consistency

**Goal:** Make the core learning and relationship writes converge under partial failure, retry, and concurrency.

**Why now:** Incorrect quota/ledger state, duplicate teacher sessions, asymmetric parent binding, and inflated rate counters damage product behavior even when requests return normal-looking responses. Phase 473 also left three explicit nonblocking runtime follow-ups: a stale parent-profile scrub can overwrite concurrent profile updates, transient delivery-begin dependency failures can be mislabeled and permanently canceled, and completed account deletion cannot replay its stored receipt after a lost response.

**Depends on:** Phase 474 deterministic failure-injection baseline.

**Requirements:** V9DATA-01, V9DATA-02, V9DATA-03, V9DATA-04, V9DATA-05, V9DATA-06, V9DATA-07, V9DATA-08.

**Audit findings:** DATA-001, BUG-002, DATA-003, BUG-006, BUG-004.

**Plans:** TBD

**Likely plan slices:**

1. Transactional question quota/idempotency/ledger/upload/question state plus reconciliation of historical partial records.
2. Conditional teacher claim/session/notification and transactional parent-child binding with repair tooling; one shared CAS/version discipline for normal parent-profile writes and child scrubs.
3. Capped/idempotent rate-limit semantics, typed delivery-begin dependency/business outcomes, complete practice-attempt answer persistence, and stored terminal account-deletion receipt replay.

**Success criteria:**

1. Identical question retries create one question, consume one quota unit, and emit one ledger event after any tested timeout/failure point.
2. Two concurrent teacher takeovers produce one successful owner, one session, one notification, and a deterministic 409 loser.
3. Parent/student forward and reverse bindings cannot commit one-sided; historical repair is dry-run capable and idempotent; a child scrub racing the real ordinary profile writer preserves unrelated locale and preference bytes.
4. Repeated 429 responses do not increase counters beyond the configured limit; a transient dependency failure injected below delivery begin remains recoverable, and the healthy retry reserves and completes exactly once without false account-deletion cancellation.
5. Mistake review returns the submitted wrong answer and safely represents historical unknown answers; an identical completed account-deletion request replays the stored terminal receipt with zero additional cleanup effects.

**Required evidence:** DynamoDB transaction/failure-injection tests; barrier concurrency tests; reconciliation dry-run/apply fixtures; a real profile-writer-versus-scrub race preserving exact locale/preference bytes; quota boundary tests; delivery-begin dependency-failure injection followed by healthy retry, typed-outcome, exactly-once reservation/completion, and no-false-cancellation evidence; mistake round trips; completed-deletion receipt replay through the real terminal projection with zero additional cleanup calls.

**Known follow-up defects closed:** `profile-version-cas`, `delivery-begin-dependency-classification`, and `completed-deletion-replay` from Phase 473.

**Exit gate:** Usage and relationship state are trustworthy enough for paid access and the real Web journeys.

### Phase 476: Billing Idempotency And Paid Access Recovery

**Goal:** Ensure one parent checkout request produces one recoverable provider/local billing and entitlement outcome.

**Why now:** Paid access is a core business journey and cannot rely on optimistic provider success followed by unrelated local writes.

**Depends on:** Phase 474 verification. It may overlap Phase 475, while reusing compatible idempotency/transaction conventions once those conventions are fixed.

**Requirements:** V9BILL-01, V9BILL-02, V9BILL-03, V9BILL-04.

**Audit findings:** DATA-002, SEC-008.

**Likely plan slices:**

1. Durable checkout command/idempotency key, exact Web request contract, and deterministic Stripe idempotency propagation.
2. Ambiguous provider/local failure reconciliation, delayed/duplicate event behavior, and support-visible state.
3. Exact Web callback origin allowlist and Stripe test-mode browser-to-entitlement/quota verification.

**Success criteria:**

1. Concurrent or retried identical Web checkout requests return/recover one provider session.
2. Provider success followed by local failure is discoverable and reconciles without a second customer charge/session.
3. Delayed, duplicate, and out-of-order signed webhooks cannot regress active entitlement.
4. Lookalike, encoded, credential-bearing, wrong-port, and arbitrary HTTPS callback URLs are refused.
5. A Stripe test-mode browser checkout and signed webhook changes parent/student effective entitlement and quota exactly once and appears in the parent/admin Web views.

**Plans:** TBD
**UI hint:** yes

**Required evidence:** Web request payload and idempotency proof, Stripe sandbox request/event IDs, failure-injection results, local/provider reconciliation rows, parent/admin API and browser results, exact-origin negative matrix, and no live charge.

**Exit gate:** Paid access has an end-to-end sandbox proof suitable for the real parent Web journey.

### Phase 477: Web Foundation And Contract Convergence

**Goal:** Make the actual Web application use the authoritative backend identity, API, and environment contracts without demo data or static success masking release-path behavior.

**Why now:** `/Users/zhdeng/stoa-frontend` is a real Vite/React application with a committed lockfile, TypeScript, ESLint, and Playwright, but current evidence shows public tutor registration is still offered, core services carry demo fallbacks, the student dashboard imports static mock truth, production deploy is independent of backend identity, and accepted Web E2E commonly uses demo login or route interception.

**Depends on:** Completed Phases 472 and 473, plus Phase 474.

**Requirements:** V9AUTH-06, V9WEB-01, V9WEB-02, V9WEB-03.

**Audit findings:** FEATURE-003. Current Web gaps are grounded in the inspected frontend repository and are not relabeled native findings.

**Plans:** TBD
**UI hint:** yes

**Likely plan slices:**

1. Generate or automatically validate Web adapters against backend OpenAPI, converge casing/enums/errors/idempotency, and reject unexpected write fields.
2. Restrict public Web registration to approved roles; converge verification/resend, password login, restore/logout, forgot/reset, role navigation, and session expiry; implement real login-code request and confirmation through the authoritative custom-auth/provider flow with anti-enumeration, replay/expiry, attempt/resend, and provider-failure controls.
3. Make staging/production configuration fail closed; remove demo/static/virtual-success truth from core student/parent release paths while retaining isolated development fixtures.
4. Add component and adapter-contract coverage that imports and executes real code, then make those checks additive to Phase 474's single gate.

**Success criteria:**

1. A student and parent can register through approved Web roles, verify email, sign in with a password, request and confirm a real login code into an authoritative authenticated session, restore a session, sign out, and recover a password through the backend contract; expired, replayed, rate-limited, unknown-account, and provider-failure cases stay fail-closed and non-enumerating.
2. Public Web pages cannot offer self-service privileged onboarding, and restored tokens always route to the backend-authoritative role/profile without fabricating a demo identity.
3. Every core Web write serializes fields, enums, idempotency keys, and errors accepted by the current OpenAPI contract; incompatible or unexpected fields fail the contract check before deployment.
4. With staging/production configuration, a backend failure produces an explicit loading/error/retry/denied/session state and never swaps in mock student, parent, billing, notification, or practice truth.
5. The core student dashboard and account/billing entry points render backend state rather than `mockDashboard`, static plan success, or virtual checkout success.

**Required evidence:** OpenAPI/adapter compatibility report; negative unexpected-field tests; approved-role registration snapshots; real sandbox auth/verification/password/recovery request IDs and `/auth/me` results; login-code request/challenge/confirm/provider IDs followed by a real token and `/auth/me`; login-code expiry, replay, resend/attempt-limit, anti-enumeration, and provider-failure matrix; configuration matrix; demo-fallback absence tests for core release paths; component results; backend-backed dashboard/account/billing browser captures.

**Exit gate:** Web identity, API, and configuration behavior is authoritative and fail-closed before journey completion begins.

### Phase 478: Complete Web Role Journeys And Route Closure

**Goal:** Let real student, parent, teacher, and admin/operator accounts complete their retained Web journeys, while proving every production route is real-service functional or intentionally removed.

**Why now:** This is the main product-value phase. The Web repository contains student, parent, tutor/teacher, admin/operator, organization, and public routes, but the student dashboard is mock-backed, core services retain demo-first modes, admin includes placeholder routes, organization routes use demo surfaces, upload tests prove browser previews rather than authoritative completion, and most current journey tests replace backend boundaries with demo auth or intercepted responses.

**Depends on:** Phases 475, 476, and 477; completed Phase 473 supplies the privacy/practice boundary.

**Requirements:** V9WEB-04, V9WEB-05, V9WEB-06, V9WEB-07, V9WEB-08, V9WEB-09, V9WEB-10.

**Audit findings:** No original audit finding is relabeled here. This phase closes the actual Web completion gaps found by repository inspection and all defects confirmed while exercising the bounded production route inventory.

**Plans:** TBD
**UI hint:** yes

**Likely plan slices:**

1. Backend-backed student dashboard plus upload/question/idempotency, AI result, teacher-help, real practice, lesson completion, mistake round trip, answer/result separation, duplicate-submit, dependency failure, and retry behavior.
2. Parent bound-child, learning/usage/report/entitlement, checkout/billing-state, denied-child, and provider-failure behavior.
3. Teacher queue, assignment/takeover, conversation, help/reply/resolve, and authorized answer-review behavior, including denied, stale, and concurrent ownership cases.
4. Admin/operator identity review, support/account, curriculum, reporting, recovery, billing, moderation, and notification operations with real service responses, authorization, and durable audit evidence.
5. Generate a bounded executable inventory of every production Web route—including public, organization, student, parent, teacher, and admin/operator routes—and either prove its real-service happy/error/denied behavior or remove/disable it intentionally; close with responsive/accessibility checks and integrated Playwright against a real backend and approved provider sandboxes.

**Success criteria:**

1. A real student sees current backend state, submits one validated upload/question idempotently, receives the AI result, requests teacher help, and completes a real practice lesson and mistake review without pre-submission answer disclosure; duplicate/retry produces one usage outcome and the stored wrong answer returns exactly.
2. A real parent sees only bound children and their current learning, usage, report, and entitlement state, completes a Stripe test-mode checkout, and sees the signed entitlement/quota change exactly once; denied-child and provider-failure states remain explicit.
3. A real teacher claims or receives authorized work, handles the conversation/help/reply/resolve path, and reviews answers only within assignment/capability boundaries; stale, denied, and concurrent takeover cases remain deterministic.
4. A real admin/operator completes the retained identity-review, support/account, curriculum, reporting, recovery, billing, moderation, and notification operations with capability-correct responses and durable audit records.
5. The executable route inventory has no unclassified production route: every enabled public/protected route proves real-service happy/error/denied behavior and every nonfunctional/demo/placeholder route is intentionally removed or disabled; integrated browser E2E covers all four roles without route interception while loading, empty, dependency-down, retry, expired-session, denied-resource, provider-blocked, and ambiguous-response states never show demo success.

**Required evidence:** Versioned executable route inventory with every public, organization, student, parent, teacher, and admin/operator route classified and exercised or intentionally disabled; redacted real account IDs for all four roles; browser run IDs and traces; accessibility/responsive results; backend request/correlation IDs; upload intent/question/usage IDs; practice attempt/mistake IDs; teacher assignment/session/help/reply/resolve IDs; admin/operator action and audit IDs; Stripe checkout/event/entitlement IDs; disabled-route snapshots; no-demo/no-placeholder assertions; failure-state captures; integrated non-intercepted E2E logs bound to the Phase 474 manifest.

**Exit gate:** Every retained production Web route is accounted for, and student, parent, teacher, and admin/operator journeys are usable by real sandbox accounts for staging-based early testing without hidden fallback behavior.

### Phase 479: Broader Versioned Infrastructure And Browser WebSocket Integration

**Goal:** Make the backend/Web cloud resources and browser realtime notification path reproducible from versioned definitions and functional end to end.

**Why now:** Phase 474 already owns and proves the minimum staging, release-role, immutable-artifact, Lambda-alias, Web release-pointer, protected-promotion, and rollback topology. The broader infrastructure still needs resource reconciliation/import, explicit non-release runtime definitions, DynamoDB access-pattern and lifecycle coverage, backup/restore ownership, and a real WebSocket API. The Web client already has optional reconnect/polling code but no deployed transport evidence.

**Depends on:** Phases 474 and 477; may overlap Phase 478 after the Web notification contract is stable.

**Requirements:** V9INFRA-01, V9INFRA-02, V9INFRA-03.

**Audit findings:** FEATURE-002, OPS-003.

**Likely plan slices:**

1. Audit and preserve the Phase 474 minimum release topology while reconciling/importing authoritative AWS resources and extending CDK coverage for DynamoDB access patterns, Cognito clients/groups, S3 lifecycle, queues, alarms, non-release runtime resources, and backup/restore configuration.
2. Authenticated WebSocket connect/disconnect/subscribe/refresh handlers, indexed/paginated fanout, stale cleanup, and delivery evidence.
3. Browser reconnect/resubscribe/dedupe/out-of-order/polling fallback behavior and deployed notification smoke.

**Success criteria:**

1. A clean staging environment can be synthesized/diffed and all broader v9.0 runtime resource assumptions are represented or explicitly imported, while compatibility checks prove the Phase 474 release roles, immutable stores, aliases, Web pointer, protected environments, and rollback path remain intact.
2. Unauthorized connection/channel access is denied; owner subscriptions survive token refresh/reconnect without broad fanout.
3. More than 500 connections and multiple pages are handled without silent omission.
4. A durable notification event reaches the intended browser account once after visibility/network reconnect and duplicate/out-of-order delivery attempts.
5. Unused uploads, stale connections, backup configuration, and restore ownership are visible in versioned infrastructure/runbooks.

**Plans:** TBD

**Required evidence:** Infra/backend/Web SHAs; Phase 474 topology/manifest compatibility record; CDK synth/diff/deploy IDs; imported-versus-defined resource inventory; broader staging/production runtime topology and role policy; table/index/bucket/lifecycle/backup/restore contract results; WebSocket connection/subscription/fanout/disconnect request IDs; unauthorized-channel matrix; multi-page/>500 fixture; browser visibility/network reconnect trace; polling fallback evidence; rollback plan.

**Exit gate:** Full WebSocket is demonstrably integrated and the broader infrastructure audit is closed without deferring or weakening any Phase 474 release prerequisite; a local service contract is not sufficient.

### Phase 480: Operational Observability Pagination And Release Resilience

**Goal:** Make critical failures detectable and critical reads complete, then exercise those controls through the immutable backend/Web release set.

**Why now:** Final product evidence is not credible if health is static, logs leak content, reads truncate at page limits, or deployment cannot promote/rollback the exact tested artifact.

**Depends on:** Phases 475, 476, and 479; consumes the Phase 474 delivery path.

**Requirements:** V9PRIV-04, V9OPS-01, V9OPS-02, V9OPS-03.

**Audit findings:** SEC-006, PERF-001, OPS-004.

**Likely plan slices:**

1. Liveness/readiness, request/trace correlation, structured redacted logging, metrics, provider timeouts, and alarms.
2. Exact-key/index and pagination correction for audited practice, WebSocket, teacher, and admin paths with load/cost evidence.
3. Backend/Web staging probes, synthetic failure/alarm evidence, and a controlled non-production promotion-failure exercise of the Phase 474 release-set rollback path.

**Success criteria:**

1. Student/model text, tokens, object keys, and provider payloads do not appear in captured logs; request/event correlation remains sufficient for support.
2. Readiness fails appropriately during dependency degradation while liveness remains semantically correct.
3. Multi-page fixtures return complete stable results and no audited path silently truncates at DynamoDB's first page or a hard fanout limit.
4. Synthetic auth/question/billing/notification failures produce actionable metrics/alarms and link to a runbook.
5. The exact tested backend/Web release set passes staging probes; a controlled non-production promotion failure produces alerts and rolls both pointers back without rebuild or digest change, and the workflow applies that same fail-closed action to any failed production smoke.

**Plans:** TBD
**UI hint:** yes

**Required evidence:** Backend/Web log-redaction captures; liveness/readiness degradation results; request/trace/provider correlation IDs; metrics/alarm synthetic IDs; exact-key/index inventory; >1-page/>500 pagination/load results; staging API/browser/provider smoke IDs; Phase 474 manifest/digests; controlled failed-smoke and automatic two-pointer rollback run.

**Exit gate:** Operational evidence supports the final product-reality audit.

### Phase 481: Web Product Reality Gate And Milestone Audit

**Goal:** Reconcile backend/Web/infra source, tests, artifacts, the complete production route inventory, all-role staging/API/provider/browser results, rollback, and finding dispositions into one honest early-testing or hold decision.

**Why now:** The prior completion illusion came from equating local contracts and intercepted UI checks with live product behavior. v9.0 closes only when the actual Web journeys and release mechanics are proven on one immutable candidate and native-only audit findings are clearly deferred rather than relabeled.

**Depends on:** Phases 478 and 480; therefore transitively all Phases 472-480. Every verification must be current for the same release candidate.

**Requirements:** V9CLOSE-01, V9CLOSE-02, V9CLOSE-03.

**Audit findings:** ARCH-001, ARCH-002, DOC-001; native-only FEATURE-001, BUG-003, BUG-005, TEST-002 receive explicit post-Web-stability deferral; disposition verification covers all 31 findings.

**Plans:** TBD
**UI hint:** yes

**Likely plan slices:**

1. Documentation/configuration/architecture/Web release truth reconciliation and clean-checkout proof.
2. Bounded critical-path boundary cleanup, residual debt register, and cross-module regression review.
3. Final finding audit, immutable evidence index, staging/browser/provider proof, controlled non-production rollback evidence, and explicit early-testing/hold decision; consume real production promotion/smoke only when separately authorized, otherwise record exact `NOT RUN`.

**Success criteria:**

1. README, environment template, architecture maps, Web release docs, requirements, roadmap, and state match the executable system and use honest completion vocabulary.
2. Critical v9.0 policy/use-case/repository boundaries are testable without a broad unrelated rewrite; remaining oversized-module work has owner, trigger, and priority.
3. Every one of the 31 audit findings is closed, explicitly accepted with owner/evidence/expiry, or deferred to a named future milestone; no backend/Web-reachable P0/P1 remains open, and all four native-only findings are visibly deferred rather than marked fixed.
4. One evidence index ties exact backend/Web/infra SHAs, cross-repository manifest, artifact digests, fixed/future tests, lint/type/dependency results, the complete executable route inventory, all-role staging/API/provider request IDs, redacted browser results, protected-gate configuration, and controlled rollback evidence; separately authorized production approval/results or their exact `NOT RUN` records are explicit.
5. The final decision is explicit: start early Web testing, internal-only continuation, limited beta, or hold. Missing, stale, route-intercepted, mismatched-candidate, or failed mandatory evidence produces hold rather than completion; absent production mutation evidence is acceptable only as exact `NOT RUN` alongside complete staging and controlled rollback evidence and cannot justify a production-readiness claim.

**Required evidence:** `481-VERIFICATION.md`; v9.0 milestone audit; clean-checkout log; release checklist; immutable evidence index; current `findings.json` disposition for all 31 findings; exact manifest and digests; complete executable route inventory; student/parent/teacher/admin-operator staging/browser/provider/correlation IDs; intentionally disabled-route evidence; controlled non-production promotion-failure and automatic rollback evidence; if separately authorized, the actual protected-owner approval plus production deploy/smoke/rollback evidence, otherwise exact `NOT RUN` for each; updated project/requirements/roadmap/state/milestone archive.

**Exit gate:** v9.0 is archived only after the final audit and decision are complete.

## Requirement Coverage

| Phase | Requirements | Count |
| --- | --- | ---: |
| 472 | V9AUTH-01..05, V9ACCESS-01..03 | 8 |
| 473 | V9PRIV-01..03 | 3 |
| 474 | V9QUAL-01..07 | 7 |
| 475 | V9DATA-01..08 | 8 |
| 476 | V9BILL-01..04 | 4 |
| 477 | V9AUTH-06, V9WEB-01..03 | 4 |
| 478 | V9WEB-04..10 | 7 |
| 479 | V9INFRA-01..03 | 3 |
| 480 | V9PRIV-04, V9OPS-01..03 | 4 |
| 481 | V9CLOSE-01..03 | 3 |
| **Total** | **All milestone requirements mapped exactly once** | **51** |

## Audit Finding Coverage

| Phase | Findings | Count |
| --- | --- | ---: |
| 472 | SEC-001, SEC-002, SEC-004 | 3 |
| 473 | SEC-003, SEC-005, BUG-001 | 3 |
| 474 | TEST-001, OPS-001, OPS-002, SEC-007, QUALITY-001 | 5 |
| 475 | DATA-001, BUG-002, DATA-003, BUG-006, BUG-004 | 5 |
| 476 | DATA-002, SEC-008 | 2 |
| 477 | FEATURE-003 | 1 |
| 478 | No original audit ID; current Web repository gaps | 0 |
| 479 | FEATURE-002, OPS-003 | 2 |
| 480 | SEC-006, PERF-001, OPS-004 | 3 |
| 481 | ARCH-001, ARCH-002, DOC-001; deferred native-only FEATURE-001, BUG-003, BUG-005, TEST-002 | 7 |
| **Total** | **All audit findings assigned one primary phase** | **31** |

## Known Follow-Up Defect Coverage

Phase 473 remains complete; its four nonblocking verification findings have one explicit owner each in the remaining milestone:

| Defect | Requirement | Phase | Closure evidence |
| --- | --- | --- | --- |
| `final-head-publication-reverification` | V9QUAL-07 | 474 | Reverify the direct publication commit and four immutable artifact blobs from a later metadata HEAD; reject mutation or invalid ancestry. |
| `profile-version-cas` | V9DATA-06 | 475 | Race the real profile writer with child scrub and preserve unrelated locale/preference bytes under one CAS/version contract. |
| `delivery-begin-dependency-classification` | V9DATA-07 | 475 | Inject transient failure below delivery begin, retain recoverable state, then prove one successful retry without false deletion cancellation. |
| `completed-deletion-replay` | V9DATA-08 | 475 | Replay identical completed deletion through the real endpoint and return the stored receipt with zero new cleanup effects. |

## Milestone Risks

| Risk | Response |
| --- | --- |
| Scope is large | Backend/Web-reachable P0/P1 closure and real core journeys are mandatory; native-only work, unrelated features, and broad refactors are explicitly deferred or excluded. |
| Existing tests reveal more defects | Treat newly confirmed correctness/security defects as milestone inputs; do not weaken tests to preserve schedule. |
| Native-only audit P1 findings remain open | Keep them explicitly deferred until the Web App has launched for testing and is stable; never count them as Web fixes or hide them from the final 31-finding disposition. |
| IaC lives outside this repository | Import or link the authoritative source and record cross-repository SHAs; do not claim reproducibility from prose. |
| Provider approvals block live proof | Use approved sandbox/test-mode evidence and produce an explicit production hold; never fabricate live evidence. |
| P0 fixes affect existing accounts | Inventory and reconcile existing Cognito groups/profiles with reversible scripts and dry-run evidence. |
| Current Web breadth hides demo/static truth | Treat only staging/production fail-closed paths and integrated browser/backend/provider evidence as phase-closing; keep demo fixtures isolated to development and focused UI-state tests. |
| Full WebSocket scope expands operations | Keep it in one bounded phase with a hard browser-to-deployed-handler gate; local service or mocked-socket tests alone do not close it. |

## Progress

| Phase | Plans Complete | Status | Completed |
| --- | --- | --- | --- |
| 472. Privileged Identity And Student Resource Authorization | 22/22 | Complete | 2026-07-15 |
| 473. Student Content Privacy And Practice Integrity | 40/40 | Complete | 2026-07-18 |
| 474. Deterministic Verification And Gated Delivery | 0/80 | Planning revision | - |
| 475. Transactional Usage Assignment And Relationship Consistency | 0/TBD | Not started | - |
| 476. Billing Idempotency And Paid Access Recovery | 0/TBD | Not started | - |
| 477. Web Foundation And Contract Convergence | 0/TBD | Not started | - |
| 478. Complete Web Role Journeys And Route Closure | 0/TBD | Not started | - |
| 479. Broader Versioned Infrastructure And Browser WebSocket Integration | 0/TBD | Not started | - |
| 480. Operational Observability Pagination And Release Resilience | 0/TBD | Not started | - |
| 481. Web Product Reality Gate And Milestone Audit | 0/TBD | Not started | - |

## Next Command

Plan the already-discussed Phase 474 against its locked Web-first context:

`$gsd-plan-phase 474`

After Phase 474 is implemented and verified, discuss Phase 475:

`$gsd-discuss-phase 475`
