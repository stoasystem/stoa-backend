---
audit: full-project-work
audited: 2026-08-15
audit_timestamp_utc: 2026-08-15T07:30:29Z
status: gaps_found
decision: HOLD
scope: backend, Web frontend, infrastructure, deferred native client, planning history, tests, security controls, and cross-repository release evidence
predecessors:
  - docs/audit/full-project-audit.md
  - .planning/v9.0-MILESTONE-AUDIT-2026-08-15.md
source_snapshot:
  backend: 837854bec998d4f0ffc3c9ef1ad9bb5c39e0f9bf
  backend_runtime_tested: 51594ae765c5529028ff0ebf49777afd1a1f0e6d
  frontend: 87330e943f89b9b6597c84845684afce34d99507
  infra: 83c4ec2d7d0fc87ed47a0c5b3f6e5c657161e2e6
scores:
  maturity: internal alpha with broad backend implementation
  requirements_historically_independently_verified: 19/51
  requirements_latest_policy_aligned: 17/51
  requirements_claimed_by_summaries: 30/51
  phases_historically_independently_verified: 3/10
  phases_verified_as_current_tuple: 0/10
  critical_end_to_end_flows_complete: 0/9
  prior_findings_independently_closed: 11/31
  canonical_security_artifacts: 0
  canonical_nyquist_validations: 0/10
---

# STOA Full Project Work Audit — 2026-08-15

## 1. Decision

The project remains **HOLD** for early testing, beta, staging deployment, or any
claim of current product completion.

STOA is an **internal alpha with a broad and increasingly well-tested backend**.
It is not yet a coherent Web product or a reproducible staging release. The
principal gap is not raw code volume. It is the absence of one current truth
connecting product authority, backend contracts, Web adapters, executable
infrastructure, tests, and provider evidence for the same source tuple.

This audit is a forward-only successor. It does not rewrite the July 14 audit,
historical phase verifications, the August 15 current-state audit, or accepted
manual waivers. It distinguishes what those artifacts proved from what the
current repositories prove now.

The following latest human decisions are binding throughout this report:

- Public registration offers `student`, `parent`, and `teacher`.
- A Teacher verifies email, then remains `pending_review` without Teacher
  resource authority until an administrator approves the account.
- Invitation/token activation is removed from the active product.
- `teacher` is the only active role term. Runtime aliases, fields, routes, and
  fallbacks using `tutor` are not retained.
- Phase 477 remains paused after discussion area 2 of 4. This audit does not
  authorize a `477-CONTEXT.md`, a plan, implementation, or deployment.
- Phase 474 remains staging-only. The production release control plane is
  `DEFERRED_OUT_OF_SCOPE`.

No feature implementation, provider access, deployment, dependency install,
destructive cleanup, or production mutation occurred during this audit.

## 2. Executive Results

| Surface | Real work that exists | Current acceptance result |
| --- | --- | --- |
| Backend | 224 OpenAPI paths; central authorization, durable commands, upload/privacy, practice, adaptive memory, billing, notification, deletion, audit, and admin primitives | Broad local health, but full tests, Ruff, and full mypy are red; Teacher registration/review and several provider-backed paths are incomplete |
| Web frontend | 92 pages, 104 concrete routes, 53 service modules, 116 hooks; strong fail-closed served-release bootstrap; lint, typecheck, release tests, and build pass | P0 release blocker: registration, session, upload, memory, chat, Teacher, billing settings, Question Bank, Classroom, and route gating are not current-contract truthful |
| Infrastructure | Object-Locked storage, versioned artifact/pointer concepts, exact-ref and manifest verification primitives | Source still builds the superseded production topology, fails Ruff, cannot synthesize, and does not implement the locked staging-only authority |
| Native/mobile | Expo shell, adapters, route scaffolding, and a shallow contract script | Explicitly deferred; no lockfile, missing asset, no active auth/guard wiring, placeholder screens, and incompatible adapters |
| Planning/evidence | Large versioned historical corpus with three strong v9 phase verifications | Current state is internally inconsistent; 0/10 phases are verified for the current three-repository tuple and 0/9 critical flows are complete |

The strongest positive conclusion is that many backend correctness primitives
from Phases 472, 473, and 475 remain reusable. The strongest negative conclusion
is that page presence, route interception, mock-backed tests, or old topology
tests currently create a completion illusion. They do not prove a working
product journey.

## 3. Source And Worktree Custody

| Repository | Audited HEAD | Relation to `origin/main` | Worktree at audit close | Interpretation |
| --- | --- | --- | --- | --- |
| backend | `837854bec998d4f0ffc3c9ef1ad9bb5c39e0f9bf` | `0 ahead / 0 behind` | clean before this report | Runtime test commands ran at `51594ae`; the only later changes before this report were `HANDOFF.json`, the Phase 477 continuation note, and the prior audit. Runtime source, tests, workflows, and mobile files were unchanged. |
| frontend | `87330e943f89b9b6597c84845684afce34d99507` | `0 ahead / 0 behind` | pre-existing untracked `public/mockServiceWorker.js` | The worker is not started by tests and is not release evidence. It was not modified or removed. |
| infra | `83c4ec2d7d0fc87ed47a0c5b3f6e5c657161e2e6` | `0 ahead / 0 behind` | pre-existing untracked `.DS_Store` | It was not modified or removed. No provider action was performed. |

The repository tuple is synchronized in Git, but Git synchronization is not
semantic integration. No immutable manifest or staging receipt currently binds
these three heads to one built, tested, deployed, smoked, and rollback-proven
candidate.

## 4. Evidence Maturity Model

This audit uses the following evidence ladder. A higher level cannot be inferred
from a lower one.

| Level | Meaning | Current project position |
| --- | --- | --- |
| L0 | Page, route, source, or plan exists | Broadly present |
| L1 | Isolated unit/component/contract test passes | Strong in many backend domains; mixed in Web/infra |
| L2 | Current frontend and backend contracts execute together without replacing the boundary under test | Not achieved for any complete critical journey |
| L3 | Exact backend/Web/infra tuple builds once and deploys unchanged to the locked staging topology | Not achieved |
| L4 | Staging provider behavior, smoke, degradation, and controlled rollback are observed and retained | Not achieved |
| L5 | Separately authorized production verification | Last declared production-verified version is v3.2; not evidence for current v9 source |

Historical receipts remain valid at the level and source they record. They do
not automatically authorize current source, a new product policy, or a changed
infrastructure topology.

## 5. Project Work And Evidence Inventory

### 5.1 Planning corpus

| Inventory | Count / state | Audit judgment |
| --- | --- | --- |
| Tracked `.planning` files | 2,235, approximately 14 MB | Valuable history, but too much live/historical material is presented in the same active namespace |
| Active phase directories | 61 | 55 pre-v9 phase directories remain mixed with the six current v9 directories |
| Active phase artifacts | 238 plans, 228 summaries, 58 verifications, 5 validation files, 0 security files | Plan completion substantially exceeds current verification/security closure |
| Archived milestone directories | 62, containing 281 phase directories | Current GSD archive discovery reports `archive_count: 0`, so the archive layout and current tool discovery disagree |
| Archived phase artifacts | 287 plans, 280 summaries, 293 verifications, 3 validations, 0 security files | 130 of 293 verification files are 20 lines or shorter; repeated commands prove narrow local contracts, not current integration |
| Archived milestone audits | 71 | 30 declare passed, 2 tech debt, 39 have no YAML status |
| Tracked `evidence/` files | 15 | Too small to establish provider and current release custody for the breadth of claimed work |
| Backend commits since 2026-05-23 | 1,415 | High delivery velocity; not a completion metric |

### 5.2 Current v9 phase state

| Phase | Plans / summaries | Independent verification | Nyquist status | Current result |
| --- | ---: | --- | --- | --- |
| 472 Identity and access | 22 / 22 | historical PASS | `green`, not canonical `validated` | Reusable local controls; invitation-only Teacher conclusions are policy-superseded |
| 473 Privacy and practice | 40 / 40 | historical PASS | `local_gates_complete` | Reusable local controls; current Web integration and live S3 observations remain open |
| 474 Verification and delivery | 47 / 39 | missing | draft | Eight retained plans (`33`–`38`, `79`, `80`), no phase verification, and current infra contradicts the locked topology |
| 475 Data consistency | 45 / 45 | historical PASS | `ready`, not canonical `validated` | Reusable local transaction/concurrency controls; current integration/provider proof remains partial |
| 476 Billing | 29 / 27 | owner waiver, not independent PASS | draft | Local command core exists; provider/browser/security proof is incomplete |
| 477 Web auth/contracts | 0 / 0 | missing | missing | Discussion paused at 2/4; no context or plan |
| 478 Web journeys | directory absent | missing | missing | Requirements have no current phase evidence |
| 479 Infrastructure/realtime | directory absent | missing | missing | Requirements have no current phase evidence |
| 480 Operations | directory absent | missing | missing | Requirements have no current phase evidence |
| 481 Closeout | directory absent | missing | missing | Requirements have no current phase evidence |

Only Phases 472, 473, and 475 have independent historical verification. None is
verified as part of the current backend/Web/infra tuple. No current phase has a
canonical `status: validated` Nyquist artifact, and no active phase has a
canonical security report.

### 5.3 Planning authority drift

- `ROADMAP.md` marks four phases complete, `STATE.md` says three completed and
  Phase 474 executing, while the current GSD initializer reports five.
- `STATE.md` and `ROADMAP.md` still point toward executing Phase 474, while the
  current handoff requires audit review and forbids automatic Phase 477 resume.
- `REQUIREMENTS.md` and `ROADMAP.md` still encode invitation-only Teacher
  onboarding. The Phase 477 checkpoint contains the newer public-registration
  plus administrator-review decision.
- `PROJECT.md` still contains stale v5.12 active-requirement language.
- `.planning/codebase/` maps date from July 15 and still project native work into
  Phase 477/478, contrary to the current Web-first/native-deferred boundary.
- New `.planning/` and `evidence/` files were briefly hidden by `.gitignore` in a
  prior commit; tracking was restored, but the incident confirms that planning
  custody needs an executable check.

## 6. All 51 Requirements: Three-Source And Integration Audit

Legend:

- **Summary**: one or more phase summaries claim the requirement.
- **Verify**: an independent phase verification historically accepted it.
- **Integration**: the current cross-repository connection is `PARTIAL` or
  `UNWIRED`; none is complete.
- **Final** is the current audit disposition, not a rewrite of history.

| Requirement | Phase | Summary | Verify | Current integration | Final disposition |
| --- | ---: | --- | --- | --- | --- |
| V9AUTH-01 | 472 | yes | yes | UNWIRED | policy-superseded; current Teacher registration authority unsatisfied |
| V9AUTH-02 | 472 | yes | yes | PARTIAL | historically satisfied locally; current tuple unverified |
| V9AUTH-03 | 472 | yes | yes | UNWIRED | policy-superseded invitation model; replacement lifecycle unsatisfied |
| V9AUTH-04 | 472 | yes | yes | PARTIAL | historically satisfied locally; Web/backend role truth still drifts |
| V9AUTH-05 | 472 | yes | yes | PARTIAL | historically satisfied locally; current session journey incomplete |
| V9AUTH-06 | 477 | no | no | UNWIRED | unsatisfied; login-code UI/provider session absent |
| V9ACCESS-01 | 472 | yes | yes | PARTIAL | historically satisfied locally; current Web proof absent |
| V9ACCESS-02 | 472 | yes | yes | PARTIAL | historically satisfied locally; current route consumers incomplete |
| V9ACCESS-03 | 472 | yes | yes | PARTIAL | historically satisfied locally; no current integrated matrix |
| V9PRIV-01 | 473 | yes | yes | UNWIRED | local backend proof retained; Web upload contract broken |
| V9PRIV-02 | 473 | yes | yes | UNWIRED | local backend proof retained; Web upload lifecycle broken |
| V9PRIV-03 | 473 | yes | yes | PARTIAL | local backend proof retained; complete real Web path unproven |
| V9PRIV-04 | 480 | no | no | UNWIRED | unsatisfied; cross-repository redaction proof absent |
| V9QUAL-01 | 474 | yes | no | PARTIAL | summary-claimed, independently unverified |
| V9QUAL-02 | 474 | yes | no | PARTIAL | summary-claimed; current full test is red and no current 2x formal receipt |
| V9QUAL-03 | 474 | yes | no | PARTIAL | summary-claimed; Web static gates pass, integration does not |
| V9QUAL-04 | 474 | yes | no | PARTIAL | summary-claimed; current Ruff and mypy fail |
| V9QUAL-05 | 474 | yes | no | PARTIAL | summary-claimed; current advisory DB audit not reproduced |
| V9QUAL-06 | 474 | yes | no | UNWIRED | locked staging-only topology not implemented |
| V9QUAL-07 | 474 | yes | no | UNWIRED | summary-claimed; independent current-candidate proof absent |
| V9DATA-01 | 475 | yes | yes | PARTIAL | historically satisfied locally; current product path unverified |
| V9DATA-02 | 475 | yes | yes | PARTIAL | historically satisfied locally; Web Teacher flow does not consume it |
| V9DATA-03 | 475 | yes | yes | PARTIAL | historically satisfied locally; current journey proof absent |
| V9DATA-04 | 475 | yes | yes | UNWIRED | historically satisfied locally; current Web retry/rate behavior unproven |
| V9DATA-05 | 475 | yes | yes | PARTIAL | historically satisfied locally; real Web mistake path unproven |
| V9DATA-06 | 475 | yes | yes | PARTIAL | historically satisfied locally; current tuple unverified |
| V9DATA-07 | 475 | yes | yes | PARTIAL | historically satisfied locally; provider delivery unobserved |
| V9DATA-08 | 475 | yes | yes | PARTIAL | historically satisfied locally; current endpoint journey unproven |
| V9BILL-01 | 476 | yes | no | PARTIAL | owner-waived, not independently verified |
| V9BILL-02 | 476 | yes | no | PARTIAL | owner-waived, not independently verified |
| V9BILL-03 | 476 | yes | no | PARTIAL | owner-waived, not independently verified |
| V9BILL-04 | 476 | yes | no | UNWIRED | owner-waived; provider/browser evidence absent |
| V9WEB-01 | 477 | no | no | UNWIRED | unsatisfied; OpenAPI/adapter authority unresolved |
| V9WEB-02 | 477 | no | no | UNWIRED | unsatisfied and stale after latest Teacher decision |
| V9WEB-03 | 477 | no | no | UNWIRED | startup foundation exists; route-level truth closure absent |
| V9WEB-04 | 478 | no | no | UNWIRED | unsatisfied; student core journey broken |
| V9WEB-05 | 478 | no | no | UNWIRED | unsatisfied; real practice journey unproven |
| V9WEB-06 | 478 | no | no | UNWIRED | unsatisfied; parent/billing integrated proof absent |
| V9WEB-07 | 478 | no | no | UNWIRED | unsatisfied; browser acceptance boundary is intercepted/invalid |
| V9WEB-08 | 478 | no | no | UNWIRED | unsatisfied; Teacher workflow not wired |
| V9WEB-09 | 478 | no | no | UNWIRED | unsatisfied; retained admin routes include placeholders/missing APIs |
| V9WEB-10 | 478 | no | no | UNWIRED | unsatisfied; enabled-route truth inventory not enforced |
| V9INFRA-01 | 479 | no | no | UNWIRED | unsatisfied; runtime delta and provider observations absent |
| V9INFRA-02 | 479 | no | no | UNWIRED | unsatisfied; authenticated WebSocket lifecycle not deployed |
| V9INFRA-03 | 479 | no | no | UNWIRED | unsatisfied; reconnect/order/dedupe/fallback flow unproven |
| V9OPS-01 | 480 | no | no | UNWIRED | unsatisfied; readiness/metrics/alarms/deployed cleanup proof absent |
| V9OPS-02 | 480 | no | no | UNWIRED | unsatisfied; exact-key/pagination closure absent |
| V9OPS-03 | 480 | no | no | UNWIRED | unsatisfied; provider/staging probes and rollback observation absent |
| V9CLOSE-01 | 481 | no | no | UNWIRED | unsatisfied; documentation truth remains stale |
| V9CLOSE-02 | 481 | no | no | UNWIRED | unsatisfied; final bounded review cannot pass with current blockers |
| V9CLOSE-03 | 481 | no | no | UNWIRED | unsatisfied; no same-candidate final decision package |

Totals:

- **19/51** have independent historical verification.
- Of those 19, **17/51** remain aligned with the latest policy.
- **2/51** (`V9AUTH-01`, `V9AUTH-03`) preserve valid historical defect closure
  but are superseded as the active Teacher product policy.
- **11/51** (seven `V9QUAL` and four `V9BILL`) are claimed by summaries without
  independent verification.
- **21/51** are pending/orphaned without phase summary and independent proof.
- **0/51** is complete as a current cross-repository, same-candidate product
  connection.

## 7. July 14 Audit Finding Disposition

The July audit contained 31 findings: P0 2, P1 9, P2 18, P3 2. Current evidence
does not justify marking all 31 closed.

| Disposition | Count | Finding IDs | Interpretation |
| --- | ---: | --- | --- |
| Independently closed | 11 | `SEC-001`, `SEC-002`, `SEC-004`, `SEC-003`, `SEC-005`, `BUG-001`, `DATA-001`, `BUG-002`, `DATA-003`, `BUG-006`, `BUG-004` | Original vulnerabilities/defects have historical independent closure evidence. `SEC-001` remains closed as an escalation defect, but its invitation-only replacement policy is superseded. |
| Owner-waived, not independently verified | 2 | `DATA-002`, `SEC-008` | Waiver is preserved and visible; it is not provider/security proof. |
| Phase 474 partial | 5 | `TEST-001`, `OPS-001`, `OPS-002`, `SEC-007`, `QUALITY-001` | Work exists, but current formal, lint/type, dependency, delivery, or verification evidence is incomplete/red. |
| Pending or deferred | 13 | `FEATURE-003`, `FEATURE-002`, `OPS-003`, `SEC-006`, `PERF-001`, `OPS-004`, `ARCH-001`, `ARCH-002`, `DOC-001`, `FEATURE-001`, `BUG-003`, `BUG-005`, `TEST-002` | Web/backend/ops work remains open; four native-only findings remain explicitly deferred. |

The historical closure rate is therefore **11/31 independently closed**, not
31/31. This does not reopen valid closed defects; it prevents their evidence
from being stretched into unrelated current product claims.

## 8. Current Implementation Audit By Domain

### 8.1 Backend

| Domain | Implemented work | Test/evidence strength | Current gap |
| --- | --- | --- | --- |
| Identity and roles | JWT validation, central Actor model, capability checks, admin provisioning, global sign-out | Strong local Phase 472 and focused regression evidence | Public resolver only supports Student/Parent; login discards refresh token; missing role can default to Student; pending Teacher cannot resolve as an Actor |
| Public registration | Student/Parent Cognito and profile lifecycle | Local tests for old policy | Teacher is rejected, email confirmation activates old roles, no `pending_review` lifecycle or admin approval of a registered Teacher |
| Old Teacher onboarding | Application/invitation/consume router remains mounted | Historical tests | Superseded authority; raw boto3 activation omits required `UserPoolId`; candidacy fields trust caller-provided verification/application values |
| Authorization | Central student-resource policy, broad route inventory, 113 admin-capability routes | Historical independent verification and generated checks | Current Web role restoration and current all-role journey proof absent |
| Conversations/chat | Durable idempotent commands, strict typed attachments, replay/fingerprint, normal and pseudo-stream routes | Strong local tests | Stream buffers a completed answer into chunks; Web request body is incompatible |
| Files/privacy | Intent/chunk/complete lifecycle, ownership, validation, saved attachment inventory | Strong local Phase 473 evidence | Web still posts legacy multipart `/files`; live S3 behavior not observed for current tuple |
| Questions/practice | Question, OCR, answer integrity, attempts, mistakes, lessons, rate behavior | Broad focused coverage | Practice Teacher-help returns random hard-coded ready IDs; complete real Web journey absent |
| Adaptive/memory | Memory read/refresh and assignment lifecycle | Local fake-provider tests | Web uses wrong unprefixed memory path and does not consume full assignment lifecycle |
| Teacher help/workflow | Durable conversation case plus queue, dispatch, takeover, reply, resolve | Strong local concurrency/lifecycle primitives | Three separate status truths; practice help is virtual, arbitrary status strings lack CAS, and student status GET is absent |
| AI | Bedrock adapter, student response path, local fakes | Local adapter and domain tests | Teacher AI tool returns a fixed template/placeholder; malformed model JSON can fall back to raw text instead of failing closed |
| Notifications/realtime | Records, preferences, digest, push-token contracts, safe wrappers | Local fake-provider tests | Unexpected push errors may be swallowed; live delivery/WebSocket provider path unobserved |
| Billing/entitlements | Idempotent commands, state/recovery projections, provider adapters | Local tests plus owner waiver | No current Stripe browser/webhook/provider evidence; Web payment truth and role gating incomplete |
| Admin/ops | Broad admin/report/curriculum/account/audit surfaces | Many local tests | Several Web admin callers target absent paths; readiness is static and provider degradation is not represented |

The backend has no active runtime `tutor` role contract; all 13 current backend
occurrences are bounded negative or historical evidence. The Web repository,
however, still contains active tutor aliases, fields, routes, components, types,
and fixtures. Reintroducing backend compatibility would violate the latest
decision.

### 8.2 Web frontend

The Web inventory contains **92 page modules, 104 concrete routes, 53 service
modules, and 116 hooks**. Presence is broad; real-service truth is not.

| Domain | Current source truth | Acceptance |
| --- | --- | --- |
| Public/Home | Marketing/legal pages are static; `/` directly serves HomeV2; `/assistant` fabricates answers and bookings | P0: Home switch crossed an explicit approval boundary and assistant is synthetic success |
| Auth | Password login is wired; register UI offers roles and sends terms fields | P0: real Student/Parent registration returns 422; Teacher invalid; no login-code, refresh, global logout, safe return, or pending/rejected Teacher shell |
| Role enforcement | Token route plus client role route | P0: `tutor/tutors/teachers` aliases accepted and unknown roles default to Student |
| Student dashboard/profile | Broad pages exist | P0: dashboard is substantially static; real profile is merged with fake Anna/Martin/guardian/billing PII |
| Chat/attachments/memory | Conversation UI and streaming hooks exist | P0: stream omits idempotency and typed references; upload and memory paths disagree with backend |
| Practice | Core adapter paths mostly align | P1: no generated adapter/schema contract lane; direct result navigation can fall back to mock lesson |
| Question Bank | Eight P0/P1 routes exist | P0: entire service is an in-memory mock |
| Classroom | Nine Student/Teacher entry paths exist | P0: entire service is in-memory mock and routes are not demo-gated |
| Parent | Children, summary, history, profile, subscription, and reports have significant real paths | P1: monthly report is absent; browser evidence is mostly intercepted |
| Teacher | Nine routes remain under `/tutor...` | P0: no pending/rejected restriction, no real queue/takeover/reply consumption, missing profile endpoint, and `tutor` response fields drift from backend `teacher` fields |
| Admin | Twenty routes cover broad operations | P1: curriculum/report/subscription/account recovery are reusable; analytics, usage, feedback, help, support, and users include missing APIs or placeholders |
| Organization | Thirteen routes exist | P1: backend organization API absent; most but not all routes are demo-gated |
| Billing | Checkout command/idempotency/session successor core aligns well | P0: routes accept any token; Payment Settings hard-codes a parent identity, email, and Visa 4242 |
| Notifications | REST list/read/archive paths substantially align | P1 security: bearer token, user ID, and role are put in WebSocket URL query; preferences/digest/push lifecycle unconsumed |
| Release configuration | Served-release digest, startup barrier, and secret-shape rejection are strong | Preserve; business feature flags are declared but do not gate routes, navigation, buttons, or mutations |

Active frontend callers also target absent backend families including contact,
support tickets, referrals, organizations, analytics events, and frontend error
monitoring. These are expected 404 paths, not minor response-schema drift.

### 8.3 Infrastructure and release delivery

The locked Phase 474 authority is exact:

- one reviewer-free, `main`-only GitHub Environment named `staging`;
- one `StoaReleaseStaging` stack;
- exactly three roles: `StoaStagingDeployRole`, `StoaStagingReadRole`, and
  `StoaStagingRollbackRole`;
- all three trust only
  `repo:stoasystem/stoa-backend:environment:staging`;
- deploy, read, and rollback policies remain disjoint and staging-only;
- production environments, stacks, roles, trusts, promotion, smoke, and
  rollback are `DEFERRED_OUT_OF_SCOPE`.

Current source does not implement that authority:

| Area | Reusable primitive | Current contradiction |
| --- | --- | --- |
| Evidence storage | Private encrypted versioned Object Lock; local tests assert 90-day candidate and 2555-day evidence defaults | Current/known-good indefinite coordinates and provider readback are unproven |
| Artifact build | Backend artifact build/hash and manifest verification exist | CDK synth stops on missing backend `dist/.stoa-build-manifest.json` |
| IAM/OIDC | OIDC role patterns exist | `ReleaseDeliveryStack` defines five old roles including production and rollback roles/subjects; not the exact three staging roles |
| Stack assembly | CDK stack modules exist | `app.py` assembles production and sandbox stacks and uses undefined `tags` at line 138 |
| Delivery workflow | Exact SHA checkout and formal-gate job concepts exist | Staging jobs run digest/script/`--help`; they do not configure credentials, deploy, smoke, or invoke automatic rollback |
| Environment policy | Historical inventory/receipt scripts exist | Backend release policy still models six environments including staging-smoke, staging-rollback, and production |
| Tests | 12 infra topology tests and 43 backend workflow/environment tests pass | They positively assert the obsolete production topology, so green means conformity to the wrong contract |
| Provider state | Historical receipts exist | Latest protected-environment receipt is blocked; historical inventory states `CLOUDFORMATION_STAGING_STACK_DOES_NOT_EXIST`; no current provider PASS/readback exists |

### 8.4 Deferred native/mobile surface

Native is correctly classified as deferred, not implemented product work:

- no JavaScript lockfile or installed dependency tree;
- `app.json` references missing `mobile/assets/notification-icon.png`;
- root layout installs only QueryClient/Stack and does not initialize runtime
  config, auth restoration, or guards;
- Student, Parent, Teacher, auth, and notification screens are StateCard or
  explanatory shells;
- adapters have no active screen call sites;
- question adapter sends snake_case `idempotency_key` and legacy
  `image_s3_key`, while backend requires `idempotencyKey` plus typed attachment;
- notification adapter sends extra/casing-drifted provider/device fields;
- `validate-mobile-contracts.mjs` passes only a source-string/manifest check.

These findings do not block the Web-first scope by themselves. They block any
statement that native is functional, buildable, or contract-integrated.

## 9. Current Test, Build, Type, Dependency, And Provider Matrix

| Surface | Current result | What is proved | Release-significant limitation |
| --- | --- | --- | --- |
| Backend focused regression | 564 passed, 1 warning | 14 critical auth/Teacher/conversation/attachment/route/billing modules are green | Not the whole suite or live providers |
| Backend full pytest | 3155 passed, 1 failed, 2 warnings in 128.26s | Broad current runtime health | Fixed July 24 free-trial fixture reads the real August 15 clock and fails; zero-failure claim blocked |
| Backend Ruff | fail, 2 findings | Scope is small and actionable | `provision_sandbox_accounts.py`: unused import and empty f-string |
| Backend full mypy | fail, 1 error across 314 files | Most source typechecks | `security/identity.py:135` calls `int(object)` without a narrowed type |
| Backend generated checks | route auth, client actions, Teacher terminology PASS | Generated inventories and terminology boundary are stable | Not Web adapter compatibility |
| Backend lock | `uv lock --check` PASS, 92 packages | Lock consistency | Current live advisory DB scan not run; `ecdsa 0.19.2 / PYSEC-2026-1325` exception expires 2026-08-18 09:00Z |
| Backend OpenAPI/input probe | 224 paths; 101 JSON write bodies | Current schema inventory | 71/101 write bodies have open or unset `additionalProperties` behavior |
| Web lint and three no-write typechecks | PASS | Static code/test-project quality | No runtime contract proof |
| Web release tests | 35/35 PASS | Served-release/runtime fail-closed foundation | Business routes and mutations do not consume many feature flags |
| Web release verifier | 18/18 PASS | Release descriptor/verifier contract | No exact current staging receipt |
| Web production build | PASS, 2659 modules; >500 kB chunk warning | Build completes | No deployed startup/live API proof |
| Web component tests | 2 suites failed; 3 suites/27 tests passed | Three isolated scopes pass | `authStore` reads unavailable `localStorage.getItem` at module import; suite is red |
| Web E2E assets | 29 specs, 106 declared tests; not rerun | Broad intended journeys are documented | Harness uses ignored `VITE_*` flags and route interception; it cannot establish live acceptance |
| MSW | server file and handlers exist | Mock assets exist | No test starts the server; handlers encode several wrong paths/bodies |
| Infra lock | PASS | Dependency lock consistency | Not synth/deploy readiness |
| Infra Ruff | FAIL | Defects identified | Undefined `tags` and unused `Duration` |
| Infra topology tests | 12/12 PASS | Old topology is internally asserted | Test oracle contradicts locked staging-only authority |
| CDK synth | FAIL | Failure is reproducible | Missing backend manifest occurs before the latent undefined `tags` defect |
| Provider-backed acceptance | NOT RUN | No mutation occurred | Cognito, S3, DynamoDB, Bedrock, SES/push, WebSocket, Stripe, staging smoke, and rollback are not current evidence |
| Current-tree secret pattern scan | only test canaries observed | No obvious current-source credential found | Full Git-history secret scan was not performed |

## 10. Cross-Repository Integration Audit

The integration checker found ten local source connections, twelve active
broken/orphan/mock contracts, and eighteen missing expected connections. Of 15
backend route families with Web callers, 12 have a broken, orphaned, or mock
active consumer. All nine critical product/release flows are broken.

| Flow | Required path | Current break | Result |
| --- | --- | --- | --- |
| 1 Registration and Teacher review | public Student/Parent/Teacher → email verify → `pending_review` → admin approve → protected Teacher | Frontend payload 422; backend rejects Teacher; old invitation path remains; no pending/rejected shell or approval path | BROKEN |
| 2 Session lifecycle | password or login code → restore → one coalesced refresh → safe return → global logout | Login code deferred/unconsumed; refresh token discarded; Web clears locally; unknown/missing role can become Student | BROKEN |
| 3 Student question/AI/help | dashboard → upload → idempotent question → AI → chat/attachments → memory → Teacher help status | Legacy upload, wrong memory prefix, invalid stream body, virtual practice help, missing status GET, static/mock data | BROKEN |
| 4 Practice/lesson/mistake | real path → answer → result-only feedback → complete → exact mistake review | Backend primitives exist; browser integration/schema lane absent and result can use mock lesson | BROKEN |
| 5 Parent/billing | bound child → report/usage/entitlement → checkout/recovery → explainable state | Main backend paths exist; browser proof intercepted, monthly report absent, billing routes mis-gated, fake payment PII shown | BROKEN |
| 6 Teacher workflow | approved Teacher → queue/assignment → takeover → context → reply/resolve | Web still uses tutor routes/types and does not consume core queue/takeover/reply contracts | BROKEN |
| 7 Admin/operator | identity review → support/account → curriculum/report → billing/moderation/notification | Broad UI/backend pieces exist; multiple callers target absent endpoints and `/admin/users` remains placeholder | BROKEN |
| 8 Notification/realtime | authenticated connect → subscribe → fanout → order/dedupe/reconnect → bounded polling | No deployed authenticated lifecycle; URL-query bearer token; real reconnect/fallback path unproven | BROKEN |
| 9 Release | exact tuple → formal gate → build once → staging deploy → smoke → controlled failure → automatic rollback | Infra topology wrong; lint/synth fail; jobs do not deploy/smoke/rollback; no provider receipt | BROKEN |

## 11. Security And Control Audit

### Controls worth preserving

- Central resource authorization and a generated route authorization inventory.
- Canonical active backend roles without a runtime `tutor` alias.
- Strict conversation command model with required idempotency and typed
  attachment references.
- Upload ownership/validation and practice answer-integrity controls.
- Durable concurrency/idempotency controls for question, takeover, binding,
  notification, deletion, and selected billing workflows.
- Backend global sign-out that does not report provider failure as success.
- Web served-release startup barrier, secret-shaped config rejection, public-path
  Authorization stripping, and disabled release demo fallback.
- Private encrypted versioned Object Lock storage primitives.

### Open security/control gaps

| Gap | Security/control effect |
| --- | --- |
| Teacher authority not implemented | Pending/rejected authority cannot be enforced because the identity state and admin transition do not exist end to end |
| Unknown/missing role fallback | Web aliases/defaults and backend missing-profile defaults can fabricate Student authority instead of failing closed |
| Staging config uses production-only strictness | A staging process can start with empty Cognito authority and a development audit key; `/health` remains static OK |
| WebSocket token in URL query | Bearer token can reach proxy/access logs and client history; client-provided user/role/channel identity cannot be trusted |
| 71 open/unset JSON write schemas | Unexpected fields may cross write boundaries unless each route independently rejects them |
| Old Teacher application input trust | Caller-supplied verification/application references participate in the superseded lifecycle |
| Provider evidence absent | Local fakes do not prove IAM, Cognito, S3, DynamoDB, Bedrock, Stripe, SES/push, or WebSocket failure behavior |
| No canonical security artifact | Threat mitigations are not independently aggregated for any current v9 phase |
| Dependency exception nearing expiry | The `ecdsa` exception requires renewal/removal based on a current advisory/reachability review; it cannot silently pass expiry |
| Current-tree-only secret scan | No complete Git-history credential result exists |

No new claim of an exploitable production incident is made here. These are
source/control and evidence gaps that block acceptance until the required proof
exists.

## 12. Consolidated Gap Register

| ID | Severity | Finding | Closure evidence required |
| --- | --- | --- | --- |
| FPW-001 | P0 | Latest public Teacher registration and admin-review authority is absent from requirements, runtime, Web, and tests | Forward authority successor plus negative/positive lifecycle tests across backend and Web |
| FPW-002 | P0 | Current registration UI deterministically sends a backend-forbidden body; Teacher registration is invalid | Generated request contract test and integrated Student/Parent/Teacher registration evidence |
| FPW-003 | P0 | Login-code, refresh, safe return, global Web logout, and fail-closed role restoration do not form one session lifecycle | Integrated expiry/replay/coalescing/provider-failure tests |
| FPW-004 | P0 | Enabled core routes expose synthetic success or fake PII: assistant, Question Bank, Classroom, uploads, dashboard/profile, Payment Settings | Disable/remove or connect to authoritative services; executable route inventory proves no enabled fake surface |
| FPW-005 | P0 | Upload, memory, chat/attachment, Teacher-help, Teacher response, and numerous route families disagree across repositories | One OpenAPI/adapter authority and non-intercepted contract lane |
| FPW-006 | P0 | Current infra source contradicts locked staging-only authority and fails lint/synth | Exact stack/role/environment policy tests, clean synth, and source review against Phase 474 authority |
| FPW-007 | P0 | No same-candidate formal, deploy, smoke, and rollback evidence exists for the current tuple | Immutable manifest, build-once artifacts, staging receipts, controlled rollback receipt |
| FPW-008 | P0 | Business feature flags do not gate routes/actions and HomeV2 crossed its explicit switch boundary | Route/navigation/mutation fail-closed tests and reviewed Home authority successor |
| FPW-009 | P1 | Backend full pytest, Ruff, and full mypy are red | Zero-failure current-candidate receipts without weakening assertions |
| FPW-010 | P1 | Web component suite is red; MSW is inert; Playwright harness is not a valid live boundary | Green component suite plus runtime-descriptor and non-intercepted browser lane |
| FPW-011 | P1 | Teacher-help status has multiple non-convergent truths and no student status GET | One durable state model, CAS transitions, and role/resource matrix |
| FPW-012 | P1 | Active Web callers target absent public, growth, organization, analytics, monitoring, learning, Teacher, and admin endpoints | Route-by-route enable/disable decision and generated coverage |
| FPW-013 | P1 | WebSocket bearer and identity are placed in URL query | Server-authenticated connection/channel design and redacted transport evidence |
| FPW-014 | P1 | Planning state, requirement policy, phase counts, archive discovery, and next action disagree | Reviewed forward-only planning reconciliation with executable consistency checks |
| FPW-015 | P1 | Provider-backed Cognito/S3/DynamoDB/Bedrock/Stripe/notifications/release behavior is not current evidence | Approved sandbox/staging observations bound to exact source |
| FPW-016 | P1 | Dependency acceptance relies on an expiring exception without current advisory DB reproduction | Current audit, reachability record, owner decision, and non-expired successor/removal |
| FPW-017 | P1 | Most JSON write bodies do not declare a closed extra-field contract | Route-specific classification and negative unexpected-field tests |
| FPW-018 | P2 | Native client is a deferred shell with no reproducible build or compatible active adapters | Preserve explicit deferment; later native milestone starts with lock/build/auth-contract proof |
| FPW-019 | P2 | Conversation stream is post-completion chunking rather than true provider streaming | Either document the honest contract or add measured real streaming in a later authorized scope |
| FPW-020 | P2 | Readiness, provider degradation, correlation, pagination, and operational evidence remain incomplete | Phase 480 implementation and deployed observation after staging authority is sound |
| FPW-021 | P2 | Documentation/codebase maps and milestone vocabulary are stale | Phase 481 clean-checkout and terminology reconciliation |

## 13. Release And Product Readiness Decision

| Claim | Decision | Reason |
| --- | --- | --- |
| Backend development foundation | ACCEPT WITH GAPS | Substantial reusable implementation and strong local coverage |
| Web product for internal real-user testing | HOLD | Core routes return 404/422, synthetic success, or incompatible data |
| Staging deployability | HOLD | Locked topology absent; infra lint/synth and workflow behavior fail |
| Security closure | HOLD | Latest role lifecycle, staging config, WebSocket auth, write schemas, and security aggregation are incomplete |
| Billing/provider readiness | HOLD / waiver preserved | Local core exists; current provider/browser proof absent |
| Native/mobile readiness | DEFERRED | Explicit Web-first scope; shell cannot be represented as implemented |
| Production release | OUT OF SCOPE | Production control plane is explicitly deferred and not authorized |

## 14. Recommended Closure Sequence

This is a proposed ordering, not authorization to resume a phase.

### Gate 0 — Human audit review

- Accept or amend this HOLD inventory.
- Keep Phase 477 paused and preserve the exact repository tuple.
- Decide whether exposed synthetic routes are disabled immediately or retained
  only behind an explicit non-production demo boundary.

Exit: an explicit closure boundary and no disputed P0 scope.

### Gate 1 — Forward authority reconciliation

- Create a reviewed successor for Teacher public registration,
  `pending_review`, administrator activation, and teacher-only terminology.
- Reconcile `PROJECT`, `ROADMAP`, `REQUIREMENTS`, `STATE`, handoff, and phase
  counts without rewriting historical evidence.
- Freeze the exact Phase 474 staging-only authority and the production deferment.

Exit: planning sources and next action agree; no invitation or runtime tutor
authority remains in active requirements.

### Gate 2 — Honest surface containment and clean local baseline

- Disable or demo-gate synthetic/absent routes and remove fake PII from real
  response paths.
- Fix the one backend full-test clock leak, two Ruff findings, one mypy finding,
  and Web component import failure.
- Reproduce dependency policy before the exception expires.

Exit: enabled surfaces are honest, and current backend/Web/infra local gates are
green without waivers being relabeled as independent proof.

### Gate 3 — Contract and authentication convergence

- Resume Phase 477 discussion areas 3 and 4 only after explicit approval.
- Select one OpenAPI/adapter authority and one mock/real-service boundary.
- Implement public Teacher review lifecycle, exact role parsing, login-code,
  refresh, safe return, and global logout.
- Align upload, attachments, memory, chat idempotency, and Teacher-help status.

Exit: generated contract checks plus non-intercepted auth and student command
lanes pass.

### Gate 4 — Retained Web journeys

- Implement or intentionally disable every route in the executable inventory.
- Close Student, Practice, Parent/Billing, Teacher, Admin, and Notification flows
  against real local/sandbox services.
- Preserve Phase 476 waiver visibility and do not synthesize provider evidence.

Exit: all retained routes are real-service functional and the required browser
failure/retry/session states pass.

### Gate 5 — Phase 474 staging-only release repair

- Replace the obsolete infra topology with one `StoaReleaseStaging` and the
  exact three disjoint staging roles.
- Make the formal gate, build-once manifest, immutable storage, deploy, smoke,
  controlled failure, and rollback jobs executable.
- Remove production release authority from this scope.

Exit: lint, synth, intentional-failure tests, and topology-policy checks pass.

### Gate 6 — Approved staging/provider evidence

- Under a separate explicit provider authorization, bind exact SHAs, locks,
  artifacts, configuration, run IDs, and redacted observations.
- Prove staging deploy, all-role smoke, dependency degradation, and automatic
  restoration of the known-good set.

Exit: same-candidate L3/L4 evidence exists. Only then can the project reconsider
HOLD for early testing. Production remains separately out of scope.

## 15. Minimum Evidence Needed To Change HOLD

HOLD cannot change merely because more plans, pages, mocks, or isolated tests
exist. At minimum, the decision package must contain:

1. a forward-approved Teacher authority successor and no active runtime `tutor`
   compatibility;
2. green current backend full tests, Ruff, mypy, Web component/release/build,
   infra lint/synth, and current dependency policy;
3. generated OpenAPI/Web adapter compatibility with unexpected-field negatives;
4. non-intercepted Student, Parent, Teacher, and Admin/operator journeys;
5. an executable inventory proving each enabled route is real or intentionally
   disabled;
6. one immutable manifest binding exact backend/Web/infra source and build-once
   artifact digests;
7. locked staging-only IAM/environment/stack topology;
8. approved staging smoke, controlled failure, and automatic rollback receipts;
9. current security and Nyquist aggregation without converting NOT RUN or owner
   waiver into PASS;
10. an explicit early-testing decision that continues to record the production
    control plane and native client as deferred.

## 16. Primary Evidence Anchors

| Area | Anchor |
| --- | --- |
| Latest Teacher authority | `.planning/phases/477-web-authentication-and-contract-convergence/477-DISCUSS-CHECKPOINT.json:54` |
| Locked staging-only authority | `.planning/phases/474-deterministic-verification-and-gated-delivery/474-CONTEXT.md:27`; `474-34-PLAN.md:69,89,109` |
| Backend registration model | `src/stoa/models/user.py:14-50`; `src/stoa/services/public_identity_service.py:265` |
| Backend session/role gaps | `src/stoa/routers/auth.py:74,189,587,874,938-953`; `src/stoa/security/identity.py:145` |
| Backend Teacher lifecycle | `src/stoa/services/teacher_application_service.py:73,242`; `src/stoa/main.py:48` |
| Backend strict chat contract | `src/stoa/routers/conversations.py:622-635,1161`; `src/stoa/models/attachment.py:103-113` |
| Backend staging configuration | `src/stoa/config.py:117,205,284`; `src/stoa/main.py:62` |
| Web registration and roles | `/Users/zhdeng/stoa-frontend/src/components/auth/RegisterForm.tsx:68,141,178`; `/Users/zhdeng/stoa-frontend/src/store/authStore.ts:19-43` |
| Web chat/upload/memory/help | `/Users/zhdeng/stoa-frontend/src/services/chat/chatStreamApi.ts:4`; `src/services/files/fileApi.ts:4`; `src/services/learning/memoryApi.ts:42`; `src/services/teacherHelp/teacherHelpApi.ts:31` |
| Web synthetic surfaces | `/Users/zhdeng/stoa-frontend/src/services/questionBank/questionBankApi.ts:1`; `src/features/live-classroom/services/liveClassroomService.ts:1`; `src/pages/assistant/StudentAssistantEntryPage.tsx:98` |
| Web fake PII | `/Users/zhdeng/stoa-frontend/src/services/student/studentApi.ts:7,139`; `src/pages/billing/PaymentSettingsPage.tsx:22` |
| Web router/governance | `/Users/zhdeng/stoa-frontend/src/app/router/AppRouter.tsx:114-244`; `/Users/zhdeng/stoa-frontend/.planning/STATE.md:22` |
| Infra contradiction | `/Users/zhdeng/stoa-infra/app.py:33-138`; `/Users/zhdeng/stoa-infra/stacks/release_delivery_stack.py:52-146` |
| Infra stale tests | `/Users/zhdeng/stoa-infra/tests/test_release_topology.py:135,362`; backend `tests/test_infra_workflow_contract.py`, `tests/test_delivery_workflow_contract.py`, `tests/test_release_environment.py` |

---

**Final audit verdict:** preserve the implemented backend foundation and the
valid historical receipts, but do not call the current project integrated,
staging-ready, beta-ready, or product-complete. Close authority and truth gaps
before expanding functionality.
