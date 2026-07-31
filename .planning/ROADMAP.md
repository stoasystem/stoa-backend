# Roadmap: v9.0 Web Product Reality, Authorization And Web Functionality Completion

- **Status:** In progress
- **Created:** 2026-07-14
- **Replanned:** 2026-07-18 after the owner's Web-first product correction
- **Prior milestone:** v8.4 Strategic Scale Reliability And Next-Version Decision
- **Audit baseline:** `de3bf1e4133550e1c679bf611b026437336bd219`
- **Requirements:** 51 across 10 phases
- **Phase range:** 472-481
- **Reality reconciliation:** `.planning/v9.0-MILESTONE-AUDIT.md` (2026-07-30)

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
| 474 | Deterministic Verification And Gated Delivery | In progress — 35/47 summaries; 12 retained plans; verification missing | Phases 472 and 473 |
| 475 | Transactional Usage Assignment And Relationship Consistency | Complete — 45/45 plans, independently verified 2026-07-23 | Phase 473 |
| 476 | Billing Idempotency And Paid Access Recovery | Administratively complete by owner waiver — 27/29 summaries; verification incomplete | Phase 475 |
| 477 | Web Authentication And Contract Convergence | Close login-code, Web role, adapter-contract, and reachable static-truth gaps | Phase 474; consumes Phases 472 and 473 |
| 478 | Real Web Role Journeys And Route Closure | Connect existing student, parent, teacher, and admin surfaces or disable them | Phase 477; consumes Phases 475 and 476 |
| 479 | Runtime Delta And Browser WebSocket Integration | Add only proven runtime deltas and one safe real browser notification path | Phases 474 and 477 plus the finalized Phase 478 notification contract |
| 480 | Operational Evidence, Pagination And Synthetic Probes | Close redaction, readiness, non-WebSocket pagination, alarms, and staged probes | Phases 478 and 479; consumes Phase 474 rollback |
| 481 | Evidence Reconciliation And Early-Test Decision | Index existing same-candidate evidence and emit PASS or HOLD | Phases 474, 478, and 480 |

## Phases

- [x] **Phase 472: Privileged Identity And Student Resource Authorization** (completed 2026-07-15) - Privileged identity and student-resource access fail closed.
- [x] **Phase 473: Student Content Privacy And Practice Integrity** (completed 2026-07-18 — 40/40 plans, independently verified) - Uploads, private content, and practice answers respect the completed safety boundary.
- [ ] **Phase 474: Deterministic Verification And Gated Delivery** - One formal backend/Web gate and its minimum CDK release topology control one immutable staged release set.
- [x] **Phase 475: Transactional Usage Assignment And Relationship Consistency** - Core learning and relationship state converges under failure and concurrency. (completed 2026-07-23)
- [x] **Phase 476: Billing Idempotency And Paid Access Recovery** (completed 2026-07-30 — manual waiver; 27/29 plans executed) - One Web checkout produces one recoverable provider and entitlement outcome.
- [ ] **Phase 477: Web Authentication And Contract Convergence** - Close only the remaining Web auth, role, adapter-contract, and reachable static-truth gaps.
- [ ] **Phase 478: Real Web Role Journeys And Route Closure** - Connect existing role surfaces to real services or intentionally disable them.
- [ ] **Phase 479: Runtime Delta And Browser WebSocket Integration** - Add only proven runtime deltas and safe deployed browser realtime.
- [ ] **Phase 480: Operational Evidence, Pagination And Synthetic Probes** - Complete redaction, readiness, pagination, alarms, and staged probes without rebuilding rollback.
- [ ] **Phase 481: Evidence Reconciliation And Early-Test Decision** - Index existing evidence and emit an honest `PASS` or `HOLD`; perform no feature work.

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

**Success Criteria**:

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

- [x] `473-18` — Enforce exact multipart acknowledgements, ledger-bound recovery, and create-only checksum-verified promotion.
- [x] `473-25` — Bind results to immutable attempt snapshots and replace free-form hints with a closed non-derivable template policy.

**Wave 16** *(blocked on Wave 15 completion)*

- [x] `473-19` — Prove exact multipart/object absence across retries, pagination, intent TTL, cleanup debt, and PART lifecycle.
- [x] `473-26` — Require an exact current teacher course/class assignment for answer reads while keeping admin access read-only.

**Wave 17** *(blocked on Wave 16 completion)*

- [x] `473-20` — Replace ambiguous conversation outcomes with one typed durable command, quota, usage, retry, and transport contract.
- [x] `473-24` — Add semantic passive-document validation and resource-isolated bounded extraction for every supported type.

**Wave 18** *(blocked on Wave 17 completion)*

- [x] `473-21` — Reconstruct exact replay attachments/history, fence AI leases, and keep extraction/provider failures retryable.

**Wave 19** *(blocked on Wave 18 completion)*

- [x] `473-22` — Make resource release and deletion exhaustive, fenced, paginated, reconciled, and crash-resumable.

**Wave 20** *(blocked on Wave 19 completion)*

- [x] `473-23` — Deliver owner list/view/download/delete APIs and a durable exact attachment-purge branch.

**Wave 21** *(blocked on Wave 20 completion)*

- [x] `473-29` — Add the permanent self-delete fence, replay-only post-fence authorization, and profile/question/OCR/upload closure.

**Wave 22** *(blocked on Wave 21 completion)*

- [x] `473-30` — Fence and scrub every moderation summary, history, event, note, and derived private-content writer.

**Wave 23** *(blocked on Wave 22 completion)*

- [x] `473-31` — Reconcile all report/recovery/support rows, exact S3 versions, SES sends, and lawful-retention exceptions.

**Wave 24** *(blocked on Wave 23 completion)*

- [x] `473-32` — Purge and fence conversations, messages, command results, teacher notes, help state, AI completion, and attachment links.

**Wave 25** *(blocked on Wave 24 completion)*

- [x] `473-33` — Purge and fence practice answers/progress/mistakes, adaptive assignments/memory, and student analytics signals.

**Wave 26** *(blocked on Wave 25 completion)*

- [x] `473-34` — Purge notification/assistance/draft copies, revoke device/realtime credentials, and stop pending external deliveries.

**Wave 27** *(blocked on Wave 26 completion)*

- [x] `473-35` — Source-discover and seal all 17 private-store branches, retained-evidence policy, zero debt, and two zero epochs.

**Wave 28** *(blocked on Wave 27 completion)*

- [x] `473-27` — Fail closed on unregistered private writes and unstrict provider/repository/parser response consumption.

**Wave 29** *(final evidence; blocked on Wave 28 completion)*

- [x] `473-28` — Test one immutable candidate with strict receipts and publish independently revalidated source-bound evidence.

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

**Success Criteria**:

1. A student can upload a supported bounded file and use it once in their own question.
2. Foreign, malformed, missing, expired, oversized, mismatched, and reused uploads are denied with stable redacted errors.
3. No student preview/overview/path/lesson response contains `correctAnswer` or answer-derived explanation before submission.
4. Authorized teacher/admin tooling retains an explicit answer-bearing contract separate from the student contract.
5. Existing question responses continue to hide object keys and raw OCR text.

**Required evidence:** Upload/object ownership matrix, content validation fixtures, S3 error redaction test, OpenAPI response checks, and student preview snapshots.

**Exit gate:** Question upload and practice preview contracts are safe enough for Web journey implementation.

### Phase 474: Deterministic Verification And Gated Delivery

**Goal:** Make it impossible for unverified backend or Web source to reach staging or production, while preserving one reproducible release identity and the minimum versioned release infrastructure from clean verification through rollback.

**Why now:** The repository needs one source-bound backend/Web/infra verification and delivery authority before later Web, realtime, and operational phases can use a trustworthy release candidate.

**Depends on:** Completed Phases 472 and 473.

**Requirements:** V9QUAL-01, V9QUAL-02, V9QUAL-03, V9QUAL-04, V9QUAL-05, V9QUAL-06, V9QUAL-07.

**Plans:** 35/47 plans executed; 12 retained plans remain.

**Cleanup record:** `474-CLEANUP.md` removes 47 unexecuted plans that were obsolete, duplicated by the completed formal-gate rebuild, or reassigned to Phases 477–480. Completed PLAN/SUMMARY pairs were preserved and plan IDs are not reused.

**Verification status:** Missing. Completed summaries preserve valuable
implementation evidence, but Phase 474 cannot close until all retained plans
finish and an independent `474-VERIFICATION.md` passes against the current
backend/Web/infra candidate.

Plans:

- [x] 474-01-PLAN.md
- [x] 474-02-PLAN.md
- [x] 474-03-PLAN.md
- [x] 474-04-PLAN.md
- [x] 474-05-PLAN.md
- [x] 474-06-PLAN.md
- [x] 474-07-PLAN.md
- [x] 474-08-PLAN.md
- [x] 474-09-PLAN.md
- [x] 474-10-PLAN.md
- [x] 474-22-PLAN.md
- [x] 474-23-PLAN.md
- [x] 474-26-PLAN.md
- [ ] 474-27-PLAN.md
- [ ] 474-28-PLAN.md
- [ ] 474-32-PLAN.md
- [ ] 474-33-PLAN.md
- [ ] 474-34-PLAN.md
- [ ] 474-35-PLAN.md
- [ ] 474-36-PLAN.md
- [ ] 474-37-PLAN.md
- [ ] 474-38-PLAN.md
- [x] 474-39-PLAN.md
- [x] 474-40-PLAN.md
- [x] 474-41-PLAN.md
- [x] 474-42-PLAN.md
- [x] 474-72-PLAN.md
- [x] 474-73-PLAN.md
- [ ] 474-76-PLAN.md
- [x] 474-77-PLAN.md
- [x] 474-78-PLAN.md
- [ ] 474-79-PLAN.md
- [ ] 474-80-PLAN.md
- [x] 474-81-PLAN.md
- [x] 474-82-PLAN.md
- [x] 474-83-PLAN.md
- [x] 474-84-PLAN.md
- [x] 474-85-PLAN.md
- [x] 474-86-PLAN.md
- [x] 474-87-PLAN.md
- [x] 474-88-PLAN.md
- [x] 474-89-PLAN.md
- [x] 474-90-PLAN.md
- [x] 474-91-PLAN.md
- [x] 474-92-PLAN.md
- [x] 474-93-PLAN.md
- [x] 474-94-PLAN.md

**Completed verification and policy foundation**

- [x] `474-01` through `474-10` — Candidate preflight, canonical gate, hermetic Python, publication reverification, dependency policy, reproducible artifact, and initial mypy families.
- [x] `474-23`, `474-26`, `474-39` through `474-42` — Web dependency remediation, immutable release storage/roles, and authorization/report/realtime typing boundaries.
- [x] `474-72`, `474-73` — Closed Web runtime configuration and served-release descriptor contracts.
- [x] `474-81` through `474-94` — Runtime startup closure, portable exact-source gate, fresh Web verification, formal aggregate, thin read-only callers, final source handoff, and two Linux formal PASS runs.

**Completed Wave 5**

- [x] `474-77` — Published Lambda versions and environment aliases.

**Completed Wave 7**

- [x] `474-22` — Current full-repository Ruff/mypy-zero gate.

**Completed Wave 8**

- [x] `474-78` — Immutable served Web release pointer.

**Remaining Wave 9**

- [ ] `474-27` — Durable two-pointer delivery coordinator.

**Remaining Wave 10**

- [ ] `474-28` — Thin exact-ref infrastructure delivery workflow.

**Remaining Wave 18**

- [ ] `474-33` — Read-only live environment and CDK inventory.
- [ ] `474-76` — Thin exact-ref frontend delivery workflow.

**Remaining Wave 19**

- [ ] `474-32` — Backend delivery workflow and environment controller.
- [ ] `474-34` — Staging-only immutable CDK substrate.
- [ ] `474-79` — GitHub protected environments.

**Remaining Wave 20**

- [ ] `474-80` — Owner verification of GitHub and staging evidence. *(blocking checkpoint)*

**Remaining Wave 21**

- [ ] `474-35` — Live staging delivery smoke and controlled rollback.

**Remaining Wave 22**

- [ ] `474-36` — Integrated intentional-failure matrix.

**Remaining Wave 23**

- [ ] `474-37` — Final requirement and source-coverage audit.

**Remaining Wave 24**

- [ ] `474-38` — Final evidence sealing and later-HEAD reverification.

**Scope boundary:** Product-level OpenAPI/Web adapter convergence and real
student, parent, teacher, and admin journeys belong to Phases 477 and 478.
Phase 479 owns only proven retained-route runtime deltas and browser WebSocket
integration. Phase 480 owns operational evidence and probes, but only consumes
the release and rollback mechanism implemented here.

**Success Criteria**:

1. One authoritative command verifies exact clean backend/Web/infra identities; the existing fixed formal aggregate remains source-bound and reproducible.
2. Ruff and the exact full-repository mypy command reach true zero without baselines, broad suppression, exclusions, or reduced scope.
3. Backend and Web artifacts build once, and the minimum Lambda alias plus immutable served-Web topology deploys the verified set without rebuilding.
4. Protected environments enforce sole-owner review; staging delivery and a controlled nonproduction failure prove automatic backend/Web rollback.
5. The final failure matrix, source audit, and evidence index bind the current source tuple and retain production mutation as exact `NOT RUN` absent separate approval.

**Required evidence:** Current Ruff/mypy results; exact source/formal receipts; immutable release topology; protected-environment owner verification; staging substrate and delivery; controlled rollback; failure matrix; source audit; final evidence index.

**Exit gate:** All 47 retained plan records have matching summaries, the current formal and quality gates pass, staging/rollback evidence is live and source-bound, production mutation remains exact `NOT RUN`, and independent Phase 474 verification passes.

### Phase 475: Transactional Usage Assignment And Relationship Consistency

**Goal:** Make the core learning and relationship writes converge under partial failure, retry, and concurrency.

**Why now:** Incorrect quota/ledger state, duplicate teacher sessions, asymmetric parent binding, and inflated rate counters damage product behavior even when requests return normal-looking responses. Phase 473 also left three explicit nonblocking runtime follow-ups: a stale parent-profile scrub can overwrite concurrent profile updates, transient delivery-begin dependency failures can be mislabeled and permanently canceled, and completed account deletion cannot replay its stored receipt after a lost response.

**Depends on:** Completed Phase 473; consumes the Phase 474 deterministic failure-injection contract without claiming Phase 474 delivery completion.

**Requirements:** V9DATA-01, V9DATA-02, V9DATA-03, V9DATA-04, V9DATA-05, V9DATA-06, V9DATA-07, V9DATA-08.

**Audit findings:** DATA-001, BUG-002, DATA-003, BUG-006, BUG-004.

**Plans:** 45/45 plans complete

Plans:

**Wave 1**

- [x] `475-01` — Atomic question-admission primitive.
- [x] `475-06` — Atomic parent binding and profile projection.
- [x] `475-09` — Capped, idempotent rate admission.
- [x] `475-11` — Typed delivery-begin outcomes.

**Wave 2**

- [x] `475-02` — Question route processing and replay projection.
- [x] `475-04` — Atomic teacher claim and deterministic session.
- [x] `475-08` — Shared profile-version/CAS discipline and real scrub race.
- [x] `475-10` — Bounded mistake-answer storage and legacy-unknown projection.
- [x] `475-12` — Completed account-deletion receipt replay.

**Wave 3**

- [x] `475-03` — Question reconciliation and exact terminal reversal.
- [x] `475-05` — Recoverable exactly-once teacher notification effect.
- [x] `475-07` — Preview/apply parent-binding reconciliation.

**Wave 4**

- [x] `475-13` — Integrated source-bound Phase 475 evidence gate. (completed 2026-07-23)

**Gap Closure Wave 1**

- [x] `475-14` — Required caller-owned question idempotency key.
- [x] `475-22` — Dual parent/student lifecycle and profile-version fence.
- [x] `475-24` — Immutable per-operation rate-limit receipt.
- [x] `475-25` — Closed cross-account deletion-reference discovery.
- [x] `475-29` — Deterministic completed-deletion receipt replay proof.
- [x] `475-31` — Practice-repository mypy cleanup.
- [x] `475-40` — Practice-router mypy cleanup.

**Gap Closure Wave 2**

- [x] `475-15` — Opaque question command, ledger, and receipt coordinates.
- [x] `475-23` — Non-revivable relationship status lifecycle.
- [x] `475-28` — Notification actor/metadata discovery-to-CAS-cleanup closure.
- [x] `475-41` — Auth-router mypy cleanup.

**Gap Closure Wave 3**

- [x] `475-16` — Opaque reconciliation job command coordinates.
- [x] `475-17` — State/version CAS for every question writer.
- [x] `475-26` — Parent relationship discovery-to-CAS-cleanup closure.
- [x] `475-34` — Notification-service mypy cleanup.
- [x] `475-38` — Admin-router mypy cleanup.

**Gap Closure Wave 4**

- [x] `475-18` — Durable OCR/AI effect receipt and recovery.
- [x] `475-21` — Active canonical-teacher takeover fence.
- [x] `475-32` — User-repository mypy cleanup.

**Gap Closure Wave 5**

- [x] `475-19` — Strict question replay integrity and ownership validation.
- [x] `475-27` — Teacher question/session discovery-to-CAS-cleanup closure.
- [x] `475-37` — Teacher-router mypy cleanup.

**Gap Closure Wave 6**

- [x] `475-20` — Production-reachable terminal proof and exact-once compensation.
- [x] `475-30` — Account-deletion-repository mypy cleanup.
- [x] `475-33` — Account-deletion-service mypy cleanup.

**Gap Closure Wave 7**

- [x] `475-35` — Usage-ledger-service mypy cleanup.
- [x] `475-36` — Subscription/quota-service mypy cleanup.
- [x] `475-39` — Question-router mypy cleanup.

**Gap Closure Wave 8**

- [x] `475-42` — Fail-closed unfiltered mypy evidence gate after all functional and type plans.

**Gap Closure Wave 9**

- [x] `475-43` — Exhaustive fail-closed source snapshot.

**Gap Closure Wave 10**

- [x] `475-44` — Complete truthful D/V9DATA/CR/WR coverage registry.

**Gap Closure Wave 11**

- [x] `475-45` — Final immutable source-bound evidence publication.

**Cross-cutting constraints:** Every plan contains exactly one implementation task; application-owned commands provide durable idempotency; strict bidirectional authorization remains unchanged; canonical roles are exactly `student|parent|teacher|admin` and teacher is spelled only `teacher`; public errors stay structured and redacted; evidence exercises lower-boundary failure and concurrency; no native/mobile scope is introduced. Live AWS runtime evidence belongs to Phase 479, live provider-effect and staged-probe evidence to Phase 480, deployment/rollback to Phase 474, and production smoke remains separately authorized or exact `NOT RUN`.

**Success Criteria**:

1. Identical question retries create one question, consume one quota unit, and emit one ledger event after any tested timeout/failure point.
2. Two concurrent teacher takeovers produce one successful owner, one session, one notification, and a deterministic 409 loser.
3. Parent/student forward and reverse bindings cannot commit one-sided; historical repair is dry-run capable and idempotent; a child scrub racing the real ordinary profile writer preserves unrelated locale and preference bytes.
4. Repeated 429 responses do not increase counters beyond the configured limit; a transient dependency failure injected below delivery begin remains recoverable, and the healthy retry reserves and completes exactly once without false account-deletion cancellation.
5. Mistake review returns the submitted wrong answer and safely represents historical unknown answers; an identical completed account-deletion request replays the stored terminal receipt with zero additional cleanup effects.

**Required evidence:** DynamoDB transaction/failure-injection tests; barrier concurrency tests; reconciliation dry-run/apply fixtures; a real profile-writer-versus-scrub race preserving exact locale/preference bytes; quota boundary tests; delivery-begin dependency-failure injection followed by healthy retry, typed-outcome, exactly-once reservation/completion, and no-false-cancellation evidence; mistake round trips; completed-deletion receipt replay through the real terminal projection with zero additional cleanup calls.

**Known follow-up defects closed:** `profile-version-cas`, `delivery-begin-dependency-classification`, and `completed-deletion-replay` from Phase 473.

**Exit gate:** Usage and relationship state pass every functional gap regression, unfiltered mypy exits zero, the exhaustive source-bound evidence package closes all D/V9DATA/CR/WR mappings, and later-phase live AWS/provider/deployment obligations remain exact `NOT RUN`.

### Phase 476: Billing Idempotency And Paid Access Recovery

**Goal:** Ensure one parent checkout request produces one recoverable provider/local billing and entitlement outcome.

**Why now:** Paid access is a core business journey and cannot rely on optimistic provider success followed by unrelated local writes.

**Depends on:** Verified Phase 475; consumes the Phase 474 common gate and Web runtime foundation without claiming Phase 474 delivery completion.

**Requirements:** V9BILL-01, V9BILL-02, V9BILL-03, V9BILL-04.

**Audit findings:** DATA-002, SEC-008.

**Likely plan slices:**

1. Durable checkout command/idempotency key, exact Web request contract, and deterministic Stripe idempotency propagation.
2. Ambiguous provider/local failure reconciliation, delayed/duplicate event behavior, and support-visible state.
3. Exact Web callback origin allowlist and Stripe test-mode browser-to-entitlement/quota verification.

**Success Criteria**:

1. Concurrent or retried identical Web checkout requests return/recover one provider session.
2. Provider success followed by local failure is discoverable and reconciles without a second customer charge/session.
3. Delayed, duplicate, and out-of-order signed webhooks cannot regress active entitlement.
4. Lookalike, encoded, credential-bearing, wrong-port, and arbitrary HTTPS callback URLs are refused.
5. A Stripe test-mode browser checkout and signed webhook changes parent/student effective entitlement and quota exactly once and appears in the parent/admin Web views.

**Plans:** 27/29 plans executed; Plans 476-28 and 476-29 accepted as waived by the project owner on 2026-07-30.
Plans:
**Wave 1**

- [x] 476-01-PLAN.md — Define canonical billing, entitlement, allowance, reminder, and recovery contracts.
- [x] 476-02-PLAN.md — Enforce exact configured checkout return origins and paths.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 476-03-PLAN.md — Converge backend plan identities, defaults, and Stripe configuration.
- [x] 476-05-PLAN.md — Persist one durable checkout command per browser idempotency key.
- [x] 476-10-PLAN.md — Persist immutable, ordered, idempotent Stripe billing facts.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 476-04-PLAN.md — Preview and conditionally apply legacy plan-identity migration.
- [x] 476-06-PLAN.md — Create or recover one Stripe Checkout Session per command.
- [x] 476-15-PLAN.md — Persist Zurich-week allowance ledgers and exact plan budgets.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 476-07-PLAN.md — Supersede or expire stale payable attempts on confirmed plan changes.
- [x] 476-08-PLAN.md — Reconcile provider/local checkout ambiguity without a second charge path.
- [x] 476-16-PLAN.md — Capture actual provider input/output token evidence.
- [x] 476-22-PLAN.md — Converge Web plan types, pricing, and display identities.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 476-09-PLAN.md — Expose parent/admin billing status and same-command recheck APIs.
- [x] 476-11-PLAN.md — Converge signed duplicate, delayed, and out-of-order webhook evidence.
- [x] 476-17-PLAN.md — Finalize question token debits across delivery and retry outcomes.
- [x] 476-18-PLAN.md — Finalize conversation and hint token debits across terminal outcomes.

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 476-12-PLAN.md — Apply exact beneficiary grants and immediate paid upgrades once.

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 476-13-PLAN.md — Apply period-end downgrade/cancel, grace, and storage transitions.

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 476-14-PLAN.md — Enforce one historical 14-day free trial and post-expiry AI/support limits.
- [x] 476-19-PLAN.md — Enforce teacher-supported and family support-case allowances.
- [x] 476-20-PLAN.md — Deliver idempotent payment-method expiry reminders safely.

**Wave 9** *(blocked on Wave 8 completion)*

- [x] 476-21-PLAN.md — Project canonical billing, allowance, reminder, and recovery state.

**Wave 10** *(blocked on Wave 9 completion)*

- [x] 476-23-PLAN.md — Drive Web checkout with durable identity and explicit beneficiaries.

**Wave 11** *(blocked on Wave 10 completion)*

- [x] 476-24-PLAN.md — Render confirming, active, incomplete, and support-needed results.
- [x] 476-25-PLAN.md — Render parent allowance, trial, payment-method, and reminder state.
- [x] 476-26-PLAN.md — Render redacted admin billing recovery and same-command recheck.

**Wave 12** *(blocked on Wave 11 completion)*

- [x] 476-27-PLAN.md — Define a mock-disabled, fail-closed Stripe sandbox browser project.

**Wave 13** *(blocked on Wave 12 completion)*

- [ ] 476-28-PLAN.md — Prove hosted Stripe sandbox checkout through signed webhook and paid access.

**Wave 14** *(blocked on Wave 13 completion)*

- [ ] 476-29-PLAN.md — Enforce zero open ASVS L1 High threats and capture source-bound Phase 476 requirement, decision, and security evidence.

**UI hint:** yes

**Required evidence:** Web request payload and idempotency proof, Stripe sandbox request/event IDs, failure-injection results, local/provider reconciliation rows, parent/admin API and browser results, exact-origin negative matrix, and no live charge.

**Original automated exit gate:** Paid access has an end-to-end sandbox proof
suitable for the real parent Web journey. This gate was not independently
reproduced in the repository.

**Completion status:** Administratively completed by explicit project-owner
waiver on 2026-07-30. This is not an automated verification pass. See
`476-MANUAL-WAIVER.md`; Plans 476-28 and 476-29 remain unchecked to preserve the
formal evidence gap.

**Milestone evidence status:** Owner-waived, automated verification incomplete.
Later phases consume the implemented billing surfaces and this waiver; they do
not silently convert it into an independent provider pass or build a second
checkout/webhook implementation.

### Phase 477: Web Authentication And Contract Convergence

**Goal:** Close only the remaining Web authentication, role, adapter-contract, and reachable shared static-truth gaps while consuming the Phase 474 runtime and formal-gate foundation.

**Current reality:** Phase 474 already implemented closed runtime configuration,
the served-release startup barrier, forced-off demo flags, locked Web
install/lint/type/build checks, and common formal callers. Remaining gaps are
concrete: login-code endpoints still return `deferred`; Web registration offers
`tutor` and sends rejected fields; role restoration can fabricate `student`; no
OpenAPI-to-Web drift gate exists; and several shared services still return
static or virtual success.

**Depends on:** Phase 474; consumes verified Phases 472 and 473.

**Requirements:** V9AUTH-06, V9WEB-01, V9WEB-02, V9WEB-03.

**Audit finding:** FEATURE-003.

**Plans**: TBD

Plans:

**Atomic planning boundaries** *(detailed PLAN.md files are not generated yet;
planning may split a boundary further but must not merge unrelated boundaries)*:

1. Real login-code provider flow and authoritative backend session lifecycle.
2. Canonical Web registration, recovery, refresh/logout, role restoration, and
   teacher-invitation entry.
3. Generated or mechanically checked OpenAPI adapters, closed write fields,
   errors, enums, and idempotency.
4. Reachable shared static/virtual truth removal plus adapter/component tests
   added to the existing Phase 474 gate.

**Explicitly excluded:** Rebuilding runtime configuration, served-release
startup, demo-flag policy, locked dependency/build checks, formal workflow
callers, or release delivery.

**Success Criteria**:

1. Login-code expiry, replay, resend/attempt limit, anti-enumeration, and provider-failure behavior produce one real authenticated Web session.
2. Public Web onboarding offers only approved roles; teacher entry uses the Phase 472 invitation path; `/auth/me` restores exactly one authoritative role without local fallback.
3. Registration, upload, practice, parent, teacher, and admin adapter drift is detected before deployment, including unexpected write fields.
4. Shared staging/production services expose explicit loading, error, denied, retry, and expired-session states and cannot return static or virtual success.

**Required evidence:** Real auth/provider request IDs and `/auth/me`; negative
auth matrix; OpenAPI/adapter drift report; unexpected-field tests; component
results; no-static-truth assertions bound into the Phase 474 candidate.

**Exit gate:** Web authentication and shared contracts are authoritative before
role-journey closure begins.

### Phase 478: Real Web Role Journeys And Route Closure

**Goal:** Connect the existing student, parent, teacher, and admin/operator Web surfaces to their verified backend contracts, or intentionally disable them.

**Current reality:** The backend primitives are substantially complete, and
Phase 476 already implemented billing contracts and UI. The remaining work is
integration: Web upload and practice shapes conflict with the backend, teacher
adapters call `/tutors` instead of `/teachers`, several admin routes are
placeholders, and current Playwright coverage commonly intercepts the boundary
under test.

**Depends on:** Phase 477; consumes verified Phases 473 and 475 plus the Phase 476 implementation and manual waiver.

**Requirements:** V9WEB-04, V9WEB-05, V9WEB-06, V9WEB-07, V9WEB-08, V9WEB-09, V9WEB-10.

**Plans**: TBD

Plans:

**Atomic planning boundaries:**

1. Executable router-derived production route inventory and explicit
   enable/disable decisions.
2. Real student dashboard, upload/question, AI result, and teacher-help journey.
3. Real student practice, lesson result, hint, and exact mistake-answer journey.
4. Real parent child, learning, usage, report, entitlement, and existing billing
   consumption journey.
5. Real teacher queue, dispatch/takeover, conversation/reply/resolve, and
   answer-read journey using canonical `/teachers` contracts.
6. Real admin/operator retained routes, with placeholder routes disabled and
   capability/error/audit behavior visible.

Each journey boundary owns its integrated browser, loading, empty, denied,
retry, expired-session, accessibility, and responsive evidence. Phase 478 does
not add one later super-plan that repeats every browser run.

**Explicitly excluded:** Reimplementing Phase 473/475 backend policy or
transaction primitives, or Phase 476 checkout, webhook, allowance, reminder,
and admin-recovery logic. The Phase 476 manual-waiver limitation remains visible.

**Success Criteria**:

1. Every enabled route is classified and backed by a real service; every unsupported static/demo/placeholder route is disabled or removed.
2. Student question and practice journeys consume the existing privacy, idempotency, result, and stored-mistake contracts exactly.
3. Parent billing uses the Phase 476 surfaces rather than creating a second provider proof; other bound-child/report paths are integrated.
4. Teacher and admin journeys use canonical routes and preserve assignment, capability, stale-work, concurrent-claim, and concealed-resource behavior.
5. Browser acceptance does not replace backend or provider boundaries with route interception.

**Required evidence:** Executable route inventory; one integrated trace per
retained journey; request/correlation and durable record IDs; disabled-route
evidence; failure-state, accessibility, and responsive results bound to the
Phase 474 manifest.

**Exit gate:** All retained routes are usable by real sandbox accounts for early
Web testing or are intentionally unavailable.

### Phase 479: Runtime Delta And Browser WebSocket Integration

**Goal:** Add only runtime infrastructure proven missing after Phase 474 and deliver one safe authorized notification to the real browser client.

**Current reality:** Base CDK, local WebSocket repository/service logic, and Web
reconnect/polling code exist. No deployed WebSocket API lifecycle exists.
Direct-event channel matching can broaden a user-specific notification to
same-role connections, fanout can truncate at 500 or stop on one result, and the
Web places token/user/role values in the URL. Phase 473's real S3
multipart/version/promotion/restart observation and Phase 475's live DynamoDB
observation also remain exact `NOT RUN` obligations assigned to this phase.

**Depends on:** Phases 474 and 477 plus the finalized Phase 478 notification contract; it may overlap other Phase 478 journeys after that contract is stable.

**Requirements:** V9INFRA-01, V9INFRA-02, V9INFRA-03.

**Audit findings:** FEATURE-002, OPS-003.

**Plans**: TBD

Plans:

**Atomic planning boundaries:**

1. Read-only retained-route runtime inventory and exact import/definition delta;
   create a non-WebSocket delta plan only if this inventory proves one is needed.
2. Real retained-route S3 multipart/version/promotion/restart and DynamoDB
   transaction/access-pattern observation; unavailable authority produces exact
   `NOT RUN` and a phase `HOLD`, not a local-fake pass.
3. WebSocket identity, channel authorization, safe credential transport, and
   direct-event isolation.
4. Deployed connect/disconnect/subscribe/refresh lifecycle plus indexed,
   paginated fanout and stale cleanup.

5. Browser visibility/network recovery, resubscription, ordering, deduplication,
   polling fallback, and one real staged notification.

**Explicitly excluded:** Release roles, immutable stores, Lambda aliases, Web
release pointers, protected environments, promotion, delivery coordination,
rollback, and release evidence sealing; all remain Phase 474 work.

**Success Criteria**:

1. Runtime inventory defines or imports only exact retained-route gaps and preserves the Phase 474 topology.
2. Real S3 multipart/version/promotion/restart and live DynamoDB behavior are observed against the current retained-route candidate; missing authority yields `HOLD`.
3. A user-specific event cannot reach another user through a role channel, and client-provided user/role values never establish authority.
4. Multiple connection pages and more than 500 connections complete without omission or whole-fanout abort.
5. One durable event reaches the intended browser once after visibility/network recovery and duplicate/out-of-order delivery.

**Required evidence:** Three-repository SHAs; runtime delta inventory; real S3
and DynamoDB observation receipts; WebSocket authorization matrix; multi-page
fanout results; deployed lifecycle request IDs; browser reconnect/polling trace;
one real notification correlation chain.

**Exit gate:** The retained real S3/DynamoDB obligations are observed and browser
realtime works against deployed handlers; a local service, local fake, or
MockWebSocket test is insufficient.

### Phase 480: Operational Evidence, Pagination And Synthetic Probes

**Goal:** Close cross-repository redaction, readiness, critical non-WebSocket pagination, metrics/alarms, and staged probes while consuming Phase 474 release and rollback behavior.

**Current reality:** Closed backend private telemetry, partial Web redaction,
liveness, correlation helpers, several paginated repositories, and basic
Lambda/API alarms already exist. Retained exception/log paths can still leak,
readiness is absent, critical routes still truncate, and no staged synthetic
probe produces correlation/alarm evidence. Phase 473's deployed cleanup
scheduler/retry/alarm and deployed-log observations plus Phase 475's live
provider-effect observation remain exact obligations here. Phase 475's older
assignment of deployment/production smoke to Phase 480 is superseded: Phase 474
owns deployment/rollback, and production smoke remains separately authorized or
exact `NOT RUN`.

**Depends on:** Phases 478 and 479; consumes Phase 474 delivery and rollback.

**Requirements:** V9PRIV-04, V9OPS-01, V9OPS-02, V9OPS-03.

**Audit findings:** SEC-006, PERF-001, OPS-004.

**Plans**: TBD

Plans:

**Atomic planning boundaries:**

1. One backend/Web retained-route sensitive-log inventory and adversarial
   redaction proof, including deployed log capture.
2. Deployed cleanup scheduler, retry, lifecycle, and alarm observation.
3. Dependency readiness, global correlation, critical metrics, actionable
   alarms, and runbook links.
4. Exact index and complete pagination closure for non-WebSocket practice,
   teacher, admin, and notification paths.

5. Live provider-effect observation for the current candidate.
6. Staged browser/API synthetic probes and observation of the existing Phase 474
   rollback coordinator under one controlled non-production failure.

**Explicitly excluded:** Reimplementing WebSocket pagination from Phase 479 or
promotion/rollback from Phase 474.

**Success Criteria**:

1. Sensitive content is absent while bounded request/event correlation remains.
2. The cleanup scheduler, retries, lifecycle, deployed logs, and live provider effects are observed; unavailable authority yields exact `NOT RUN` and `HOLD`.
3. Dependency degradation changes readiness without falsifying process liveness.
4. All audited list paths return complete stable multi-page results.
5. Synthetic auth/question/billing/notification failures create actionable evidence, and the Phase 474 rollback is invoked and observed without rebuild.

**Required evidence:** Redaction canaries and deployed log capture; cleanup
scheduler/retry/alarm receipt; live provider-effect receipt; readiness
degradation results; correlation chain; alarm IDs; exact-key/pagination inventory
and multi-page fixtures; staged probe IDs; unchanged-artifact rollback
observation.

**Exit gate:** All mandatory deployed operational observations are current and
can support the final early-test decision; an unavailable obligation produces
`HOLD`.

### Phase 481: Evidence Reconciliation And Early-Test Decision

**Goal:** Reconcile existing same-candidate evidence and emit an honest `PASS` or `HOLD` without implementing features or rerunning valid work.

**Depends on:** Phases 474, 478, and 480; transitively consumes all earlier verified or owner-waived outcomes.

**Requirements:** V9CLOSE-01, V9CLOSE-02, V9CLOSE-03.

**Audit findings:** ARCH-001, ARCH-002, DOC-001; native-only FEATURE-001,
BUG-003, BUG-005, and TEST-002 remain explicitly deferred until post-Web
stability.

**Plans**: TBD

Plans:

**Exactly two atomic planning boundaries:**

1. Truth reconciliation: 51 requirements, 31 immutable baseline findings,
   documentation, architecture maps, configuration, state, waivers, debt, and
   exact `NOT RUN` boundaries.
2. Evidence index and decision: validate source identities, artifact hashes,
   phase verification status, route/journey/provider/staging/rollback receipts,
   then publish `481-VERIFICATION.md` and `PASS` or `HOLD`.

**Explicitly excluded:** Feature implementation, broad architecture refactoring,
Stripe/browser/deployment/rollback reruns when a valid same-candidate receipt
already exists, or milestone archive before the decision.

**Success Criteria**:

1. Project documentation matches clean-checkout behavior and uses precise contract, integrated, staging-verified, live-verified, waived, and product-complete vocabulary.
2. Every finding is closed, explicitly owner-accepted, or deferred with owner and trigger; native-only findings are not relabeled.
3. One index validates the current backend/Web/infra tuple and all mandatory receipts without accepting stale, intercepted, or mismatched-candidate proof.
4. The result is explicit: begin early Web testing, continue internal-only, limited beta, or hold. Missing mandatory evidence yields `HOLD`; production work remains exact `NOT RUN` unless separately authorized.

**Required evidence:** `481-VERIFICATION.md`; v9.0 milestone audit; reconciled
requirement/finding matrix; clean-checkout result; evidence index; current route
inventory and all-role receipts; Phase 474 rollback receipt plus Phase 480
observation; waiver and `NOT RUN` records.

**Exit gate:** The decision exists. Milestone archive is a later administrative
action, not evidence required to make the decision.

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

Phase 473 remains complete. Three of its four nonblocking verification findings
were closed and independently verified by Phase 475; only
`final-head-publication-reverification` remains inside Phase 474:

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
| IaC is a sibling repository with partial coverage | Bind `/Users/zhdeng/stoa-infra` by exact SHA and add only runtime deltas proven by the Phase 479 inventory. |
| Provider approvals block live proof | Use approved sandbox/test-mode evidence and produce an explicit production hold; never fabricate live evidence. |
| P0 fixes affect existing accounts | Inventory and reconcile existing Cognito groups/profiles with reversible scripts and dry-run evidence. |
| Current Web breadth hides demo/static truth | Treat only staging/production fail-closed paths and integrated browser/backend/provider evidence as phase-closing; keep demo fixtures isolated to development and focused UI-state tests. |
| Full WebSocket scope expands operations | Keep it in one bounded phase with a hard browser-to-deployed-handler gate; local service or mocked-socket tests alone do not close it. |
| Direct realtime channel matching can broaden a user event to same-role connections | Phase 479 must make user-specific delivery exact before any deployed notification smoke. |

## Progress

| Phase | Plans Complete | Status | Completed |
| --- | --- | --- | --- |
| 472. Privileged Identity And Student Resource Authorization | 22/22 | Complete | 2026-07-15 |
| 473. Student Content Privacy And Practice Integrity | 40/40 | Complete | 2026-07-18 |
| 474. Deterministic Verification And Gated Delivery | 34/47 | In progress — 13 retained plans; verification missing | - |
| 475. Transactional Usage Assignment And Relationship Consistency | 45/45 | Complete — independently verified | 2026-07-23 |
| 476. Billing Idempotency And Paid Access Recovery | 27/29 | Administratively complete — owner waiver; verification incomplete | 2026-07-30 |
| 477. Web Authentication And Contract Convergence | 0/TBD | Reconciled scope; not planned | - |
| 478. Real Web Role Journeys And Route Closure | 0/TBD | Reconciled scope; not planned | - |
| 479. Runtime Delta And Browser WebSocket Integration | 0/TBD | Reconciled scope; not planned | - |
| 480. Operational Evidence, Pagination And Synthetic Probes | 0/TBD | Reconciled scope; not planned | - |
| 481. Evidence Reconciliation And Early-Test Decision | 0/TBD | Reconciled scope; not planned | - |

## Next Command

Execute the 14 remaining retained Phase 474 plans; do not regenerate the removed plans:

`$gsd-execute-phase 474`

After Phase 474 is complete and independently verified:

`$gsd-discuss-phase 477`
