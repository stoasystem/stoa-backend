# STOA Full Project Audit

- Audit timestamp: `2026-07-14T12:22:42Z`
- Audit commit: `de3bf1e4133550e1c679bf611b026437336bd219`
- Branch and remote baseline: `main` = `origin/main`
- Scope: repository-wide source, tests, configuration, build, dependency, API, data, security, mobile, CI/CD, documentation, and planning review. No production mutation was performed.

## 1. Executive Summary

STOA is best described as an **internal alpha with a broad backend implementation**, not as a beta-ready or production-ready product. The FastAPI backend exposes substantial student, parent, teacher, billing, reporting, curriculum, notification, and administrative behavior. A fresh Python 3.12 Lambda artifact can be built, the dependency lock is internally consistent, OpenAPI generation succeeds, and 640 Python tests pass. Those strengths do not offset the release blockers found in the actual user and authorization paths.

Two P0 issues are confirmed. First, the public registration endpoint accepts a caller-selected `admin` or `teacher` role and then adds the new Cognito user to the corresponding privileged group. Second, several student data endpoints authorize only by role, allowing an unrelated parent or teacher to read another student's learning data. These defects make expansion to beta or a broader production audience unsafe until fixed and regression-tested.

The largest completion illusion is the gap between planning completion and deployable product completion. Planning marks v8.0-v8.4 complete as local gated contracts, while the same planning files explicitly say live rollout remains blocked. The mobile application is mostly placeholder screens, its dependency manifest cannot currently be installed, its authentication contract does not match the backend, WebSocket handlers are not connected to API Gateway routes, and several provider-backed flows remain configuration-gated. A milestone should not be called product-complete when only local decision functions or source-string contract checks are complete.

Recommendation: continue development, but define the next milestone as **v9.0 Product Reality, Authorization And Core Journey Completion**. Phase 0 must close the two authorization failures, object ownership and answer exposure, and restore a trustworthy green test/CI baseline. Only then should the team finish real mobile journeys, live notification integration, provider failure handling, observability, and infrastructure reproducibility.

Finding counts: **P0 2, P1 9, P2 18, P3 2, P4 0; total 31**.

## 2. Repository Baseline

### Git state

| Item | Result |
| --- | --- |
| Current branch | `main` |
| Upstream | `origin/main` |
| HEAD | `de3bf1e4133550e1c679bf611b026437336bd219` |
| Remote baseline after fetch | `de3bf1e4133550e1c679bf611b026437336bd219` |
| Ahead / behind | `0 / 0` |
| Worktree at audit start | Clean; no tracked or untracked changes |
| Stash | Empty |
| Audit correspondence | Fully corresponds to fetched `origin/main` at the timestamp above |

`git fetch --prune origin` was used to refresh remote state. No reset, clean, force checkout, rebase, merge, or production deployment was performed.

### Runtime and repository facts

- Backend: Python, FastAPI, Mangum, Pydantic; deployment target Python 3.12 on AWS Lambda arm64.
- Local checked-in virtual environment runtime: Python 3.14.5, which differs from the deployment target.
- Data and cloud services: DynamoDB, S3, Cognito, Bedrock, Rekognition, SQS, SES, Stripe, API Gateway WebSocket assumptions.
- Mobile: Expo / React Native / TypeScript scaffold.
- Package management: `uv.lock` for Python; no mobile lockfile.
- Approximate inventory: 83 backend source files, 43 Python test files, 61 mobile files, and 1,835 planning files.
- Largest modules: `production_pilot_service.py` 6,359 lines, `routers/admin.py` 3,678, `subscription_service.py` 3,121, `adaptive_learning_service.py` 1,978.
- No executable CDK/Terraform/CloudFormation stack, DynamoDB schema initializer, or migration framework is present in this repository.

### Commands and results

| Check | Command | Result |
| --- | --- | --- |
| Remote refresh | `git fetch --prune origin` | Pass; local and remote SHA identical |
| Local Python version | `.venv/bin/python --version` | Python 3.14.5; target mismatch |
| Existing-env tests | `.venv/bin/pytest -q` | Fail: 12 failed, 640 passed |
| Target env creation | `uv sync --python 3.12 --frozen --extra dev` into `/tmp/stoa-audit-py312` | Pass |
| Target-runtime tests | `/tmp/stoa-audit-py312/bin/pytest -q` | Fail: same 12 failed, 640 passed in 23.99s |
| Lint | `ruff check src tests scripts --output-format=concise` | Fail: 5 errors in `scripts/seed_practice.py` |
| Types | `mypy src --no-pretty` | Fail: 136 errors in 48 of 83 files |
| Bytecode compile | `python -m compileall ...` | Pass |
| OpenAPI import | local Python probe | Pass: 203 paths, 216 method/path operations, no duplicates |
| Local health smoke | FastAPI `TestClient` GET `/health` | Pass: 200 and static payload |
| Python lock | `uv lock --check --offline` | Pass |
| Installed packages | `uv pip check --python .venv/bin/python` | Pass: 58 packages compatible |
| Existing Lambda manifest | `python scripts/build_lambda_dist.py --verify-only` | Fail: stale source hash in local `dist/` |
| Fresh source-only package | build to `/tmp` with `--skip-install` | Pass |
| Fresh full Lambda package | Python 3.12, manylinux2014 arm64 build to `/tmp` | Pass: 94 MB unpacked, 35 MB zip; handler inventory pass |
| Python dependency audit | `pip-audit -r requirements.txt` | Fail: 8 advisories in 5 packages |
| Mobile contract script | `npm run test:contracts --prefix mobile` | Pass, but only checks source strings |
| Mobile typecheck | `npm run typecheck --prefix mobile` | Could not start: `tsc` absent |
| Isolated mobile install | `npm install --no-package-lock --ignore-scripts` in `/tmp` copy | Fail reproducibly: `ETARGET`, no `expo-constants@~19.0.0` |
| Current-tree secret scan | repository pattern search | Pass for current tree; only explicit fake test values found |

The fresh Lambda package contains Linux arm64 binary wheels and therefore cannot be imported directly on the macOS audit host. Package construction and handler inventory passed; native import still requires a Linux arm64 container or Lambda smoke.

### Checks not completed

- No production AWS, Cognito, Stripe, SES, S3, DynamoDB, API Gateway, browser, or mobile-device mutation was attempted. Current live configuration and data cannot be inferred from source alone.
- No real iOS/Android build, simulator test, or device end-to-end test was possible because the mobile dependency manifest is not installable and there is no lockfile.
- `npm audit` could not run because dependency resolution fails before a dependency tree exists.
- No migration/restore test could run because no migration, schema bootstrap, IaC, or backup restore implementation exists in the repository.
- The current-tree secret search did not scan complete Git history; a dedicated history scanner remains required.
- No load test or profiler run was performed. Performance findings below are labeled as code-path risks, not measured latency claims.

## 3. Development Progress Matrix

| Module | Actual status | Completion judgment | Test status | Production usability | Main blockers |
| --- | --- | --- | --- | --- | --- |
| Account registration and login | Integrated with known critical defects | Core Cognito/profile flow exists; privileged self-registration is open; passwordless code is deferred | Unit coverage exists, no negative privileged-registration regression | Not usable safely | SEC-001, FEATURE-003 |
| Authentication token validation | Integrated but insufficiently tested | Signature, issuer, and token-use checks exist; client binding and JWKS rotation are incomplete | Mock-heavy tests; no multi-client/JWKS-rotation integration | Restricted use only | SEC-004 |
| Parent/student authorization | Partially implemented | Parent-specific helpers enforce bindings, but parallel student/question routes do not | Missing systematic authorization matrix | Not usable safely | SEC-002 |
| Student questions, AI, OCR | Integrated with known risks | Submit, AI response, escalation, and redaction exist | Good happy-path coverage; multi-write and object-ownership failures missing | Not release-ready | SEC-003, DATA-001 |
| Practice and adaptive learning | Integrated but failing tests | Broad curriculum/adaptive behavior exists; answer keys leak and mistake answers are not stored | 11 current failures, clock-dependent fixtures, accidental AWS calls | Not release-ready | BUG-001, BUG-004, TEST-001 |
| Teacher/tutor workflows | Partially implemented | Dispatch, takeover, response, sessions, and capability checks exist | Sequential behavior covered; concurrency not covered | Pilot only | BUG-002 |
| Parent billing and entitlements | Integrated but insufficiently tested | Plans, entitlements, Stripe checkout/webhooks, overrides, ledger behavior exist | Webhook transaction tests exist; provider/local partial failures absent | Sandbox/pilot only | DATA-002, SEC-008 |
| Usage ledger and quotas | Integrated with known consistency defects | Counters and ledgers exist but write order is non-atomic | One current failure exposes a new unmocked side effect | Not trustworthy for billing decisions | DATA-001, BUG-006 |
| Email/push notifications | Implemented but live providers gated | Local records, preferences, delivery gates, and provider contracts exist | Focused local tests; no provider-backed evidence in this audit | Not proven live | Provider live evidence absent; OPS-004 |
| WebSocket real-time notifications | Implemented but not integrated | Connection repository and fanout service exist; no deployed route handlers/mobile client | Service tests only | Not live | FEATURE-002, PERF-001 |
| Admin/report/audit tools | Integrated but insufficiently reverified | Large admin/report surface and prior smoke evidence exist | Extensive focused tests; no current live smoke was performed | Requires new release gate | OPS-001, OPS-003 |
| Curriculum editor/content migration | Functionally implemented locally with capability gating | Editing is not granted to every teacher; service-level capabilities provide the special authorization boundary | Focused contract tests; no current live end-to-end evidence | Controlled internal use | OPS-003, ARCH-002 |
| Mobile application | Skeleton only and currently non-buildable | Routes and service adapters exist, most screens are `StateCard` placeholders, auth/API contracts conflict | Source-string script passes; dependency install/typecheck/native build fail or cannot start | Not usable | FEATURE-001, BUG-003, BUG-005, TEST-002 |
| CI/CD and release | Partially implemented | Lambda packaging and direct code deployment exist | CI does not run tests/lint/types/security checks | Unsafe release path | OPS-001, OPS-002 |
| Infrastructure and data bootstrap | Not present in this repository | Runtime assumes external tables, indexes, buckets, groups, routes, queues, and functions | No zero-to-live or restore test | Not reproducible | OPS-003 |
| Observability and operations | Partially implemented | Domain audit records exist; global health/readiness/tracing/metrics are incomplete | No failure-mode operational smoke | Not production-ready | OPS-004 |

## 4. Findings Summary

| ID | Severity | Confidence | Title | Release blocker |
| --- | --- | --- | --- | --- |
| SEC-001 | P0 | Confirmed | Public registration can create admin or teacher group members | Yes |
| SEC-002 | P0 | Confirmed | Parent and teacher routes permit horizontal access to unrelated student data | Yes |
| SEC-003 | P1 | Confirmed | Question OCR accepts another user's S3 object key | Yes |
| BUG-001 | P1 | Confirmed | Legacy practice responses expose correct answers before submission | Yes |
| DATA-001 | P1 | Confirmed | Question quota, ledger, and question writes are non-atomic | Yes |
| DATA-002 | P1 | Highly likely | Stripe checkout creation can orphan or duplicate provider sessions | Yes |
| BUG-002 | P1 | Highly likely | Teacher takeover uses a read-then-write race | Yes |
| OPS-001 | P1 | Confirmed | Every main push deploys production Lambda code without quality gates | Yes |
| FEATURE-001 | P1 | Confirmed | Mobile app is a non-buildable placeholder skeleton | Yes |
| BUG-003 | P1 | Confirmed | Mobile Cognito flow bypasses backend identity provisioning and reads incompatible roles | Yes |
| TEST-001 | P1 | Confirmed | Full Python suite is red, time-dependent, and leaks into real AWS clients | Yes |
| SEC-004 | P2 | Highly likely | JWT validation does not bind access tokens to allowed app clients; JWKS cache cannot rotate | Yes |
| SEC-005 | P2 | Confirmed | Upload size/type/ownership controls and error handling are incomplete | Yes |
| SEC-006 | P2 | Confirmed | Student and model content can enter application logs | Yes |
| SEC-007 | P2 | Confirmed | Locked Python dependencies contain eight published advisories | Yes |
| SEC-008 | P2 | Confirmed | Checkout return URL validation accepts arbitrary HTTPS and localhost-prefix lookalikes | Yes |
| BUG-004 | P2 | Confirmed | Practice mistake records discard the student's submitted answer | No |
| BUG-005 | P2 | Confirmed | Mobile request field names do not match backend Pydantic aliases | Yes |
| FEATURE-002 | P2 | Confirmed | WebSocket service has no live route integration or mobile consumer | No |
| FEATURE-003 | P2 | Confirmed | Login-code flow always reports deferred instead of authenticating | Scope-dependent |
| PERF-001 | P2 | Highly likely | DynamoDB reads use scans, first-page filtering, and hard limits | No |
| OPS-002 | P2 | Confirmed | Local runtime and Lambda artifact provenance drift from the target | Yes |
| OPS-003 | P2 | Confirmed | Infrastructure, schema, and recovery are not reproducible from the repository | Yes |
| OPS-004 | P2 | Confirmed | Health, request correlation, metrics, and dependency readiness are incomplete | Yes |
| ARCH-001 | P2 | Confirmed | Planning completion materially overstates live product completion | No |
| ARCH-002 | P2 | Confirmed | Oversized modules mix routing, policy, persistence, and provider concerns | No |
| TEST-002 | P2 | Confirmed | Mobile tests validate strings, not runtime behavior | Yes |
| DATA-003 | P2 | Highly likely | Parent/student forward and reverse bindings can diverge | Yes |
| BUG-006 | P2 | Confirmed | Rejected rate-limit attempts continue increasing counters | No |
| DOC-001 | P3 | Confirmed | README, environment template, and codebase maps are stale | No |
| QUALITY-001 | P3 | Confirmed | Lint and typing have no enforced baseline | No |

## 5. Detailed Findings

### SEC-001 - Public registration can create admin or teacher group members

- **Severity / confidence:** P0 Critical / Confirmed.
- **Location:** `src/stoa/routers/auth.py:29-36`, `365-405`, `484-490`, `763-775`; symbols `RegisterRequest`, `register`, email confirmation.
- **Evidence and trigger:** `/auth/register` has no authentication dependency, accepts any string role, chooses the role-specific Cognito client, writes `custom:role`, and calls `admin_add_user_to_group` for `admins` or `teachers`. Teacher `pending_review` is response metadata only. A local TestClient reproduction with mocked Cognito submitted `role=admin` and received 201 while recording the `admins` group assignment.
- **Impact:** Unauthenticated vertical privilege escalation to administrative data and mutations; the same path can create unapproved teachers with access to minors' learning records.
- **Recommended fix:** Public registration must allow only approved public roles. Provision admins only through the audited production-admin script; create teachers through an authenticated invitation/approval workflow with a one-time token and explicit capability assignment. Remove authorization-changing group writes from public confirmation.
- **Required regression tests / dependencies:** Negative tests for `admin`, `teacher`, `tutor`, unknown and case-variant roles; Cognito group assertions; invitation replay/expiry tests. Blocks every external release and depends on an authoritative role-provisioning policy.

### SEC-002 - Horizontal access to unrelated student data

- **Severity / confidence:** P0 Critical / Confirmed.
- **Location:** `src/stoa/routers/students.py:211-284`, `src/stoa/routers/questions.py:241-255`, `src/stoa/routers/practice.py:105-113`; compare the owned-child helper in `src/stoa/routers/parents.py:434-443`.
- **Evidence and trigger:** The affected routes restrict students to themselves but allow any parent, teacher, or admin by role. They do not verify a parent-child binding or teacher assignment. A local unrelated-parent request to `/students/arbitrary-child/summary` returned 200.
- **Impact:** Disclosure of minors' question history, learning profile, weak topics, progress, and individual question records across family/teacher boundaries.
- **Recommended fix:** Introduce one central `authorize_student_access(actor, student_id, purpose)` policy backed by active parent bindings, active teacher assignment/session, and explicit admin permission. Apply it to every route accepting a student/question identifier.
- **Required regression tests / dependencies:** Role-resource authorization matrix with unrelated parent, stale binding, unassigned teacher, assigned teacher, owner student, and admin; enumerate all OpenAPI routes containing student/question IDs. Blocks release; depends on binding and teacher-assignment truth sources.

### SEC-003 - Cross-user S3 object key can be submitted for OCR

- **Severity / confidence:** P1 High / Confirmed.
- **Location:** `src/stoa/models/question.py:23-28`, `src/stoa/routers/questions.py:84-110`, `src/stoa/routers/files.py:53-81`.
- **Evidence and trigger:** Presign issuance creates `uploads/{user_id}/...`, but question submission accepts an arbitrary `image_s3_key` and invokes Rekognition without checking that prefix or an upload ownership record. Trigger requires an authenticated student and knowledge of another key.
- **Impact:** Cross-user extraction and persistence of OCR text, violating object and student data isolation.
- **Recommended fix:** Persist upload intent/owner/status, require exact owner prefix plus an existing unconsumed upload record, validate S3 metadata after upload, and consume the reference atomically with question creation.
- **Required regression tests / dependencies:** Own-key success, foreign-key denial, malformed prefix, missing object, reused key, content mismatch. Depends on upload lifecycle design and DATA-001 transaction work.

### BUG-001 - Practice answer keys are returned before submission

- **Severity / confidence:** P1 High / Confirmed.
- **Location:** `src/stoa/routers/practice.py:49-66`, `208-212`, `446-480`.
- **Evidence and trigger:** `_build_challenge` always emits `correctAnswer`; student overview, path, and lesson endpoints all use it. A direct function/route probe returns the field before any attempt.
- **Impact:** Students can bypass exercises, corrupting mastery, adaptive learning, teacher review, and outcome analytics.
- **Recommended fix:** Separate preview and result schemas. Omit answer, explanation, and answer-derived feedback until a recorded submission; keep author/admin views explicit.
- **Required regression tests / dependencies:** Snapshot/contract tests asserting absence before answer and presence only after authorized result retrieval. Coordinate with mobile curriculum consumers.

### DATA-001 - Question counter, ledger, and question persistence are non-atomic

- **Severity / confidence:** P1 High / Confirmed.
- **Location:** `src/stoa/routers/questions.py:168-207`, `src/stoa/db/repositories/question_repo.py:31-55`, `src/stoa/services/usage_ledger_service.py:356-397`.
- **Evidence and trigger:** The code explicitly uses `counter_then_ledger`, followed by a separate question `put_item`. Ledger failure consumes quota without a question; question failure leaves ledger/counter state and causes retries to consume again or return conflict. The current failing learning-expansion test exposes the new unmocked ledger side effect.
- **Impact:** Incorrect paid usage, lost submissions, permanent retry conflicts, and irreconcilable quota/customer-support records.
- **Recommended fix:** Use a DynamoDB transaction for conditional quota update, idempotent ledger put, and question put, or an outbox/state machine with explicit compensation and reconciliation.
- **Required regression tests / dependencies:** Failure injection at each write, duplicate/reordered retries, timeout after commit, concurrent identical idempotency keys, reconciliation. Depends on a documented transaction/idempotency contract.

### DATA-002 - Stripe checkout provider/local partial failure

- **Severity / confidence:** P1 High / Highly likely.
- **Location:** `src/stoa/services/subscription_service.py:133-227`, `1730-1778`.
- **Evidence and trigger:** Live Stripe checkout is created before several independent DynamoDB writes; no Stripe idempotency key is supplied. A local write failure or Lambda timeout after provider success can orphan a checkout; retry can create another provider session. This was not exercised against Stripe.
- **Impact:** Duplicate checkout sessions, support ambiguity, inconsistent billing UI, and possible duplicate customer action.
- **Recommended fix:** Require a client/business idempotency key, pass a deterministic provider idempotency key, persist a pending command before provider invocation, and reconcile provider objects after ambiguous failures.
- **Required regression tests / dependencies:** Stripe test-mode failure injection before/after provider response, Lambda retry, duplicate requests, local transaction failure, reconciliation. Depends on billing command state design.

### BUG-002 - Teacher takeover race

- **Severity / confidence:** P1 High / Highly likely.
- **Location:** `src/stoa/routers/teachers.py:129-174`, especially `get_question`, unconditional `update_status`, then session `put_item`.
- **Evidence and trigger:** Two teachers can both read `escalated`, pass checks, then write `teacher_active` and separate sessions. Sequential tests do not model concurrent claims.
- **Impact:** Multiple teachers receive success, duplicate sessions/notifications are created, and last write wins ownership.
- **Recommended fix:** Use a conditional update on expected status/dispatch owner and atomically create the session; map conditional failure to 409.
- **Required regression tests / dependencies:** Barrier-based concurrent takeover test, stale dispatch owner, retry by winner, losing writer has no session/notification. Depends on repository conditional-write support.

### OPS-001 - Main deploys without quality or release gates

- **Severity / confidence:** P1 High / Confirmed.
- **Location:** `.github/workflows/deploy.yml:3-75`.
- **Evidence and trigger:** Every push to `main` packages and updates `stoa-api` and `stoa-weekly-report`. The workflow does not run pytest, Ruff, mypy, dependency/security scans, mobile checks, staging smoke, approval, alias/canary promotion, or rollback. The audited main currently has 12 test failures and known vulnerable dependencies.
- **Impact:** Known-bad code can reach production automatically; both Lambda functions are updated together without behavioral verification.
- **Recommended fix:** Split verify/build/deploy; require protected checks and immutable artifact provenance; deploy to staging/version, run smoke, then promote an alias with approval and rollback metadata. Pin actions to immutable SHAs.
- **Required regression tests / dependencies:** CI fixture that intentionally fails each gate; deployment dry run; staging API smoke; rollback drill. Depends on branch protection and AWS environment separation.

### FEATURE-001 - Mobile app is a non-buildable placeholder skeleton

- **Severity / confidence:** P1 High / Confirmed.
- **Location:** `mobile/app/auth/sign-in.tsx:1-19`, most files under `mobile/app/`, `mobile/package.json:14-40`, `mobile/app.json:20-25`.
- **Evidence and trigger:** Most routes render a short scaffold/`StateCard`; sign-in claims controls are implemented but renders only text. There is no lockfile. A clean `/tmp` install fails with `ETARGET` for `expo-constants@~19.0.0`; `app.json` references a missing `assets/notification-icon.png`.
- **Impact:** No reproducible TypeScript check, native build, or usable student/parent journey; planning status does not represent a shippable iOS or Android app.
- **Recommended fix:** Select a supported Expo SDK matrix using `expo install`, commit a lockfile, make typecheck/native prebuild green, then implement screens against tested backend contracts.
- **Required regression tests / dependencies:** Clean install, `expo-doctor`, typecheck, iOS/Android build, navigation smoke, sign-in and core journey E2E. Depends on BUG-003/BUG-005 contract decisions.

### BUG-003 - Mobile identity provisioning conflicts with backend authentication

- **Severity / confidence:** P1 High / Confirmed.
- **Location:** `mobile/src/services/auth/amplifyAuth.ts:45-89`, `src/stoa/routers/auth.py:365-490`, `src/stoa/deps.py:104-117`.
- **Evidence and trigger:** Mobile calls Cognito `signUp` directly, bypassing backend profile/group/binding creation. Restore reads `custom:roles` plural and accepts only singular `student|parent`, while backend writes `custom:role` and access tokens normally carry plural groups `students|parents`. Mobile also configures one client while backend registration selects role-specific clients.
- **Impact:** Registration can create orphan Cognito identities, restored sessions can have an empty role set, and backend authorization/onboarding fails.
- **Recommended fix:** Make the backend registration/verification/session contract authoritative, or implement a Cognito trigger that atomically provisions the same domain records. Publish one role normalization contract and one allowed client map.
- **Required regression tests / dependencies:** Real Cognito sandbox registration, verification, token restore, backend `/me`, student and parent navigation, orphan repair. Must follow SEC-001 role policy.

### TEST-001 - Full Python suite is red and not isolated

- **Severity / confidence:** P1 High / Confirmed.
- **Location:** `tests/test_adaptive_learning.py:83-100`, `155-180`, `tests/test_learning_expansion.py:43-74`, `src/stoa/services/adaptive_learning_service.py:666-674`, `1892-1905`.
- **Evidence and trigger:** Both Python 3.14 and clean 3.12 runs produce 12 failures/640 passes. Eleven adaptive tests miss practice repository patches because those patches were accidentally placed inside one test, causing real DynamoDB client attempts. Fixed June 2026 fixtures age against `datetime.now()`. One question test omits the newer usage-ledger side effect.
- **Impact:** The suite is date-dependent, can attempt ambient AWS access, and cannot protect deployment changes.
- **Recommended fix:** Centralize AWS-deny fixtures, inject/freeze a clock, move all source patches into helpers/fixtures, update behavior mocks without weakening assertions, and make tests a required CI gate.
- **Required regression tests / dependencies:** Run twice with no AWS credentials and with a future frozen date; assert no network/AWS client invocation; target Python 3.12. Blocks release and CI restructuring.

### SEC-004 - JWT client binding and JWKS rotation are incomplete

- **Severity / confidence:** P2 Medium / Highly likely.
- **Location:** `src/stoa/deps.py:50-91`, `93-117`, `119-157`.
- **Evidence and trigger:** JWT verification disables audience validation and never validates Cognito access-token `client_id` against an allowed app-client set. The global JWKS cache is not keyed by pool/settings and does not refresh on unknown `kid`; synchronous `httpx.get` runs in an async dependency. Role fallback mutates Cognito groups during authentication and swallows broad exceptions.
- **Impact:** Tokens from unintended clients in the same pool may be accepted; signing-key rotation can cause persistent 401s until cold start; auth latency blocks the event loop.
- **Recommended fix:** Validate issuer, token use, and allowed `client_id`; cache per issuer with TTL and one refresh on unknown key; use async HTTP or cold-start initialization; move group repair to an explicit job.
- **Required regression tests / dependencies:** Wrong client, wrong pool, ID token, expired token, unknown-key refresh, multi-settings isolation, Cognito outage. Depends on authoritative client inventory.

### SEC-005 - Upload controls and error handling are incomplete

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/routers/files.py:12-76`, plus `src/stoa/routers/questions.py:84-110`.
- **Evidence and trigger:** `_MAX_FILE_SIZE` is unused; presigned PUT cannot enforce length; broad `image/*` is accepted for any listed image extension; no post-upload sniffing/scanning/lifecycle state exists; raw S3 exception text is returned. Ownership consumption is absent as described in SEC-003.
- **Impact:** Oversized or mislabeled objects, storage abuse, unsafe downstream processing, and internal error disclosure.
- **Recommended fix:** Prefer presigned POST with exact size/type conditions, verify object metadata/magic bytes before use, quarantine/scan, add lifecycle expiry, and return a stable redacted error.
- **Required regression tests / dependencies:** Oversize, MIME mismatch, polyglot, absent object, expired upload, S3 error redaction. Depends on upload lifecycle and bucket policy/IaC.

### SEC-006 - Sensitive learning content is logged

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/services/ai_service.py:70-80`, `130-141`, `src/stoa/routers/conversations.py:456-458`.
- **Evidence and trigger:** Prompt-injection logging includes the first 120 characters of a student's message; JSON parse failure logs 200 characters of model output; provider exceptions are logged verbatim.
- **Impact:** Minors' educational content or provider identifiers can enter centralized logs with longer retention and broader operator access.
- **Recommended fix:** Log event IDs, lengths, policy categories, request IDs, and exception classes only; centralize structured redaction.
- **Required regression tests / dependencies:** Capture logs with seeded secrets/student text and assert absence; verify useful correlation fields remain. Depends on OPS-004 request correlation.

### SEC-007 - Published dependency vulnerabilities

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `requirements.txt`, `uv.lock` resolved versions: `cryptography 48.0.0`, `ecdsa 0.19.2`, `pydantic-settings 2.14.1`, `python-multipart 0.0.29`, `starlette 1.1.0`.
- **Evidence and trigger:** `pip-audit` reports 8 advisories in 5 packages. Fixes are available for cryptography, pydantic-settings, python-multipart, and Starlette. The ecdsa timing advisory has no listed fix. Current route inspection found no form/file parsing and the app uses RSA JWT verification, reducing reachability for some advisories but not eliminating upgrade work.
- **Impact:** Availability, request-host validation, multipart parsing, or cryptographic side-channel risk depending on reachable code paths.
- **Recommended fix:** Upgrade within tested constraints, remove unused `ecdsa`/multipart dependencies if possible, document temporary applicability decisions with expiry, and gate CI on new high/critical findings.
- **Required regression tests / dependencies:** Full backend suite, auth/JWT tests, request-host/proxy tests, package build/import in Linux arm64. Advisory references: [cryptography](https://github.com/advisories/GHSA-537c-gmf6-5ccf), [pydantic-settings](https://github.com/advisories/GHSA-4xgf-cpjx-pc3j), [python-multipart](https://github.com/Kludex/python-multipart/security/advisories/GHSA-6jv3-5f52-599m), [Starlette](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq).

### SEC-008 - Checkout return URL allowlist is ineffective

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/services/subscription_service.py:153-160`, `1818-1826`.
- **Evidence and trigger:** Any `https://` URL is accepted, and prefix matching accepts values such as `http://localhost.evil.example`. An authenticated parent can supply these values when creating checkout.
- **Impact:** Post-checkout phishing/open-redirect behavior and inconsistent callback handling.
- **Recommended fix:** Parse URLs structurally and allow only configured exact origins/paths per environment; disallow user-controlled production origins.
- **Required regression tests / dependencies:** Lookalike hosts, credentials, ports, encoded host/path, scheme variants, allowed app URL. Depends on deployment origin configuration.

### BUG-004 - Student answer is not persisted for mistake review

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/routers/practice.py:525-567`, `600-618`, `src/stoa/db/repositories/practice_repo.py:148-168`.
- **Evidence and trigger:** The route reads `student_answer` but `record_attempt` has no such parameter or field; mistake response reads `attempt.get("student_answer", "")`, so `yourAnswer` is always empty.
- **Impact:** Mistake review loses the key comparison context and weakens learning analytics.
- **Recommended fix:** Store a normalized/display-safe answer with schema version and content limits; preserve historical rows as unknown rather than empty input.
- **Required regression tests / dependencies:** Wrong scalar/list answer round trip, legacy row, Unicode/long answer, correct answer not stored as mistake.

### BUG-005 - Mobile/backend field alias mismatches

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `mobile/src/features/student/studentApi.ts:46-56`, `src/stoa/models/question.py:23-28`, `mobile/src/services/notifications/notificationApi.ts:18-28`, `src/stoa/routers/notifications.py:61-66`.
- **Evidence and trigger:** Mobile sends `idempotency_key` while the model accepts only alias `idempotencyKey`; a direct Pydantic probe sets the snake-case value to `None`. Mobile sends `device_id` while backend expects `deviceId`, so device identity is silently ignored. Additional response types do not match backend fields.
- **Impact:** Question retries are not idempotent and push-token device metadata is lost; typed mobile code gives false contract confidence.
- **Recommended fix:** Generate or share an OpenAPI client, select one casing convention, reject unexpected fields on write models, and add contract compatibility tests.
- **Required regression tests / dependencies:** Serialize every mobile request and validate against FastAPI models/OpenAPI; real local API tests for question and push registration. Depends on mobile dependency repair.

### FEATURE-002 - WebSocket implementation is not integrated

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/services/websocket_service.py`, `src/stoa/db/repositories/websocket_repo.py`, `src/stoa/config.py:99-108`.
- **Evidence and trigger:** Registration, refresh, subscription, disconnect, and fanout functions are referenced by tests and notification service, but there is no `$connect`, `$disconnect`, or message Lambda handler/router/IaC and no mobile WebSocket client. Deploy/smoke flags default false.
- **Impact:** The advertised full real-time path cannot operate end to end; clients must poll or receive no live update.
- **Recommended fix:** Either complete API Gateway route handlers, authorizer, deployment, mobile reconnect/dedupe, and read-only smoke, or explicitly remove WebSocket from the current milestone and use polling.
- **Required regression tests / dependencies:** Local handler contract, deployed connect/subscribe/fanout/disconnect, expired connection cleanup, duplicate/out-of-order event handling, mobile background/foreground. Depends on OPS-003 infrastructure.

### FEATURE-003 - Passwordless login code is deferred

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/routers/auth.py:792-805` and its existing tests.
- **Evidence and trigger:** The endpoint consistently returns a deferred state and no authentication tokens; tests encode that behavior.
- **Impact:** Any UI or planning claim of login-code authentication is incomplete; users cannot complete that login route.
- **Recommended fix:** Make a product decision: implement Cognito custom auth/OTP with expiry, attempt limits, anti-enumeration, and delivery evidence, or remove the endpoint/UI/roadmap claim until scheduled.
- **Required regression tests / dependencies:** Request/verify/resend, expiry, replay, brute force, account enumeration, SES failure, rate limiting. Depends on approved email provider and auth policy.

### PERF-001 - DynamoDB first-page scans and filters

- **Severity / confidence:** P2 Medium / Highly likely.
- **Location:** `src/stoa/db/repositories/practice_repo.py:18-28`, `37-49`, `69-115`, `171-178`; `src/stoa/db/repositories/websocket_repo.py:51-56`; `src/stoa/services/websocket_service.py:194-208`.
- **Evidence and trigger:** Practice reads query broad `PRACTICE` partitions and filter in Python without pagination; challenge lookup uses a FilterExpression over a broad prefix and only the first page. WebSocket fanout scans at most 500 connections. The repository contains 28 `.scan` call sites.
- **Impact:** Records can be silently omitted after DynamoDB's page boundary; latency and read cost grow with shared partitions. No measured production latency was collected.
- **Recommended fix:** Define access-pattern-specific keys/GSIs, paginate all reads, use exact keys for challenge lookup, and index recipient/channel connections.
- **Required regression tests / dependencies:** More-than-1MB/page fixtures, >500 connections, pagination token stability, load/cost benchmark. Do after correctness baseline and schema/IaC ownership.

### OPS-002 - Runtime and build artifact drift

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `pyproject.toml`, local `.venv`, `scripts/build_lambda_dist.py`, ignored local `dist/.stoa-build-manifest.json`.
- **Evidence and trigger:** Local `.venv` is Python 3.14.5 while deployment targets 3.12. Existing `dist` verification failed because manifest source hash `6383fe...` did not match current `99192ca...`. A clean 3.12 arm64 build passed, showing the script works but provenance is not continuously enforced before development/testing.
- **Impact:** Developers can test a different runtime or inspect/deploy a stale artifact; native-wheel behavior is not proven on the host.
- **Recommended fix:** Pin project Python, create environments from lock, build once in CI, sign/store the manifest and artifact, then deploy that exact artifact through stages.
- **Required regression tests / dependencies:** Clean 3.12 setup, Linux arm64 import smoke, manifest tamper/stale-source test, artifact digest equality across promotion.

### OPS-003 - Infrastructure and data lifecycle are not reproducible

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** repository-wide absence; runtime assumptions in `src/stoa/config.py`, repository GSI queries, WebSocket/provider code, and `.github/workflows/deploy.yml`.
- **Evidence and trigger:** No CDK/Terraform/CloudFormation source, DynamoDB bootstrap/migration, Cognito group/client setup, API Gateway route definition, bucket policy, queue definition, alarm, backup, or restore script is present. Planning references external CDK evidence, but this checkout cannot create or verify an environment.
- **Impact:** New environments, disaster recovery, index changes, and configuration review depend on undocumented external state; code/data compatibility cannot be gated.
- **Recommended fix:** Bring authoritative IaC and schema contracts into a versioned repository, add additive migrations/backfills with checkpoints, and automate backup/restore verification.
- **Required regression tests / dependencies:** Empty-account synth/deploy, drift detection, table/index contract test, fixture restore, rollback rehearsal. Requires ownership and import of existing live resources.

### OPS-004 - Operational health and observability are incomplete

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/main.py:54-60`, sparse logging across routers/services, configuration provider flags.
- **Evidence and trigger:** `/health` always returns static `ok` and version `0.1.0`; there is no dependency readiness, global request/trace ID middleware, consistent structured logs, application metrics, or repository-owned alarms. Most external calls rely on SDK defaults.
- **Impact:** Operators cannot distinguish process liveness from DynamoDB/S3/Cognito/queue/provider failure or correlate a user request across Lambda and provider events.
- **Recommended fix:** Add separate liveness/readiness, correlation IDs, structured redacted logs, latency/error/business metrics, explicit timeouts, and actionable alarms/runbooks.
- **Required regression tests / dependencies:** Dependency degradation smoke, request-ID propagation, log redaction, alarm synthetic, timeout/retry tests. Coordinate with release pipeline and IaC.

### ARCH-001 - Planning completion overstates product completion

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `.planning/STATE.md:28-50`, `.planning/ROADMAP.md`, `.planning/milestones/v8.4-MILESTONE-AUDIT.md:9-27`, `src/stoa/services/production_pilot_service.py`.
- **Evidence and trigger:** v8.4 is marked complete based on one 6,359-line local gate service and 83 focused tests, while the audit says real rollout and provider writes remain blocked. The repository has 1,835 planning files versus 83 backend source files; mobile and WebSocket realities remain unresolved.
- **Impact:** Stakeholders may select the wrong next work, infer live validation that never occurred, and continue adding milestones over broken core journeys.
- **Recommended fix:** Separate `contract complete`, `integrated`, `live verified`, and `product complete`; require executable evidence for each user journey and reconcile roadmap status from this audit.
- **Required regression tests / dependencies:** Milestone evidence schema validating build SHA, environment, API/browser/device result, and unresolved blockers. No production code dependency.

### ARCH-002 - Oversized modules and mixed boundaries

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/services/production_pilot_service.py` (6,359 lines), `src/stoa/routers/admin.py` (3,678), `src/stoa/services/subscription_service.py` (3,121), `src/stoa/services/adaptive_learning_service.py` (1,978), and direct repository/provider calls in routers.
- **Evidence and trigger:** Routing, policy, persistence, provider invocation, response construction, and audit behavior are frequently combined; 46 broad `except Exception` sites make failure ownership harder to reason about.
- **Impact:** High change blast radius, difficult failure injection, duplicated authorization/rules, and slow review.
- **Recommended fix:** Do not rewrite now. After Phase 1, extract tested policy/use-case boundaries around authorization, billing commands, adaptive evidence, and admin reporting, preserving APIs.
- **Required regression tests / dependencies:** Characterization tests before each extraction, repository/provider ports, behavior parity. Depends on a green suite and stable contracts.

### TEST-002 - Mobile tests are source-string checks

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `mobile/scripts/validate-mobile-contracts.mjs:1-55`, Python tests under `tests/mobile`.
- **Evidence and trigger:** The passing script checks dependency names, route-group text, and environment-variable text. It does not import the app, typecheck, render a screen, call an API, restore a session, or build native projects.
- **Impact:** A passing test can coexist with an unresolvable dependency tree, placeholder UI, and incompatible API payloads, as observed in this audit.
- **Recommended fix:** Retain cheap manifest checks but add TypeScript, component, adapter contract, navigation, native build, and device E2E layers.
- **Required regression tests / dependencies:** Clean install and typecheck first; then React Native Testing Library, mock-server/OpenAPI contract tests, Maestro/Detox or equivalent core-journey tests.

### DATA-003 - Parent/student binding can be half-written

- **Severity / confidence:** P2 Medium / Highly likely.
- **Location:** `src/stoa/db/repositories/user_repo.py:113-150`, registration calls in `src/stoa/routers/auth.py:350-358`, `473-482`.
- **Evidence and trigger:** Forward `CHILD#` and reverse `PARENT#` rows are two independent `put_item` calls; a timeout/error between them creates divergent relationship truth. Registration profile updates add another independent write.
- **Impact:** Authorization, parent dashboards, reconciliation, and deletion can disagree about ownership.
- **Recommended fix:** Use `TransactWriteItems` with idempotent conditions and a reconciliation job for historical asymmetry.
- **Required regression tests / dependencies:** Fail between writes, duplicate registration, conflicting parent, repair idempotency, authorization behavior with one-sided legacy rows. Coordinate with SEC-002 policy.

### BUG-006 - Rate-limit failures inflate counters

- **Severity / confidence:** P2 Medium / Confirmed.
- **Location:** `src/stoa/services/rate_limit.py:12-39`, chat/hint call sites.
- **Evidence and trigger:** `_increment_and_check` increments first and raises when `new_count > limit`; every rejected retry increments again. Downstream provider failure also leaves consumed chat/hint quota with no compensation or idempotency.
- **Impact:** Misleading usage records, lockout amplification, and avoidable support/reconciliation work.
- **Recommended fix:** Use a conditional increment capped at limit and define whether quota is consumed on accepted request or successful result; add operation idempotency and explicit failure records.
- **Required regression tests / dependencies:** Repeated 429 leaves count at limit, concurrent final slot, provider failure/retry, next-day boundary. Align with DATA-001 ledger semantics.

### DOC-001 - Operational documentation and environment template are stale

- **Severity / confidence:** P3 Low / Confirmed.
- **Location:** `README.md:1-35`, `.env.example:1-34`, `.planning/codebase/STRUCTURE.md:174`, `.planning/codebase/CONCERNS.md:12-21`, `.planning/codebase/TESTING.md:12-16`, and mobile release/planning documents.
- **Evidence and trigger:** README is minimal, `.env.example` omits many active provider/WebSocket/audit settings, and codebase maps claim test gaps that no longer match the 43 test files. Some mobile text states controls are implemented when the route is a placeholder.
- **Impact:** Setup failures, configuration drift, and inaccurate milestone decisions.
- **Recommended fix:** Regenerate factual setup/config/module documentation after Phase 1; distinguish defaults, required production values, secret sources, and live evidence.
- **Required regression tests / dependencies:** Environment-key coverage check and command smoke from a clean checkout. Depends on final runtime/IaC decisions.

### QUALITY-001 - Lint and typing lack an enforceable baseline

- **Severity / confidence:** P3 Low / Confirmed.
- **Location:** `scripts/seed_practice.py:17-21`, `734`; type errors across 48 backend files; `.github/workflows/deploy.yml`.
- **Evidence and trigger:** Ruff reports 5 errors. Mypy reports 136 errors, including missing third-party stubs and real optional/type contract issues. Neither runs in CI.
- **Impact:** New regressions cannot be separated from existing debt and interface drift remains hidden.
- **Recommended fix:** Fix Ruff immediately; classify mypy errors, add required stubs, establish a checked-module baseline, and expand strictness without `Any`-based suppression.
- **Required regression tests / dependencies:** CI Ruff zero-error and non-increasing mypy baseline, then module-by-module strict checks. Depends on TEST-001 baseline work.

## 6. Test and Verification Gaps

The following areas currently cannot be claimed correct:

1. **Authorization matrix:** no exhaustive route/resource tests for unrelated parents, unassigned teachers, disabled/stale relationships, special curriculum capabilities, or group/profile disagreement.
2. **Concurrency and idempotency:** no concurrent teacher takeover, final-quota slot, duplicate checkout, duplicate webhook timing, or timeout-after-commit tests.
3. **Multi-write failure recovery:** no failure injection between quota/ledger/question, parent binding rows, provider/local billing, or session/question writes.
4. **Clock/timezone behavior:** adaptive tests use wall-clock time and fixed dates; billing periods, TTLs, DST, month-end, and token expiry need injected-clock tests.
5. **AWS isolation:** unit tests can instantiate real DynamoDB clients; a global deny-network/deny-AWS fixture is required.
6. **Live provider integration:** Stripe test mode, Cognito clients/groups, SES delivery, S3 metadata, Bedrock/Rekognition, SQS, and API Gateway WebSocket are not proven by this audit.
7. **Mobile runtime:** no installable dependency graph, typecheck, render test, native build, device journey, offline/reconnect, or push notification evidence.
8. **Data lifecycle:** no schema bootstrap, migration compatibility, backfill checkpoint/replay, backup restore, or disaster-recovery proof.
9. **Release behavior:** no staging deployment, version/alias promotion, post-deploy smoke, rollback, or artifact-to-SHA attestation.
10. **Security regression:** no automated privileged registration denial, IDOR matrix, upload ownership, log redaction, dependency policy, secret-history scan, or rate-limit abuse suite.

## 7. Security Assessment

### Confirmed controls

- Cognito JWT signature, issuer, expiry, and `token_use=access` checks exist.
- Most route families use role dependencies; parent-owned child helpers demonstrate a correct pattern.
- Curriculum editing includes service-level capability checks rather than granting every teacher edit rights.
- Stripe webhook signature/timestamp validation exists and production rejects missing secrets.
- Stripe webhook state updates use DynamoDB transactions and event deduplication.
- Question responses redact raw S3 keys and OCR text from normal API output.
- CORS defaults are limited to localhost and the STOA app origin.

### Confirmed/high-risk gaps

- SEC-001 privileged self-registration and SEC-002 horizontal student-data access are immediate release blockers.
- Object ownership, upload validation, answer-key exposure, JWT client binding, sensitive logging, dependency advisories, and checkout redirect validation require remediation.
- CI/CD currently provides no security or quality gate before production deployment.

### Production security gates

Before external beta or user expansion, require: SEC-001/002/003 and BUG-001 fixed; all P0/P1 authorization regression tests green; dependency upgrades assessed; current-tree plus history secret scan; role/resource API matrix; upload ownership/size/type tests; log-redaction tests; Stripe/Cognito sandbox evidence; staging smoke; and a documented rollback. Broad speculative hardening should not displace these reachable defects.

## 8. Technical Debt and Architecture

### Must be handled before more feature breadth

- Central resource authorization and authoritative identity provisioning.
- Green, isolated Python 3.12 tests and gated CI.
- Transaction/idempotency boundaries for quota, relationships, teacher claims, and billing commands.
- Reproducible mobile dependency/build baseline.
- Versioned infrastructure/schema ownership.

### Can be repaid while features continue

- Pagination/index corrections per touched access pattern.
- Structured logging/request IDs and explicit provider timeouts.
- Incremental mypy coverage and response/request schema convergence.
- Extraction of policy/use-case boundaries from large modules after characterization tests.

### Not worth doing now

- Framework rewrite, database replacement, wholesale microservice split, or broad design-system rewrite.
- Large speculative scale architecture before real core journeys and measured load exist.
- Replacing all broad modules solely to improve file size metrics.

## 9. Prioritized Roadmap: v9.0 Product Reality, Authorization And Core Journey Completion

### Phase 0 - Immediate blockers

**V9-P0-01: Lock privileged identity provisioning**

Goal/modules: restrict public auth roles; add invite/admin provisioning in `auth`, Cognito integration, and capability records. Dependencies: role policy and existing production group inventory. Acceptance: public admin/teacher/tutor registration always fails; approved provisioning is audited and replay-safe. Tests: role variants, invite expiry/replay, confirmation, group/profile consistency. Risk: existing privileged accounts may need reconciliation. Effort: M. **Blocks all later release work: yes.**

**V9-P0-02: Central student-resource authorization**

Goal/modules: one policy used by students, questions, practice, adaptive, parent, teacher, report, and admin routes. Dependencies: parent bindings and teacher assignment/session truth. Acceptance: only owner/bound parent/assigned teacher/authorized admin can access each resource. Tests: generated OpenAPI authorization matrix and stale/disabled relationship cases. Risk: undocumented legitimate teacher workflows may surface. Effort: L. **Blocks release: yes.**

**V9-P0-03: Close object and exercise disclosure**

Goal/modules: enforce upload ownership/lifecycle and remove pre-answer keys. Dependencies: V9-P0-02 policy and upload record design. Acceptance: foreign keys are denied; no student preview response contains an answer. Tests: ownership, reuse, MIME/size, preview/result schemas. Risk: frontend compatibility. Effort: M. **Blocks release: yes.**

**V9-P0-04: Restore trustworthy verification**

Goal/modules: fix 12 tests without weakening assertions; deny ambient AWS; freeze/inject clock; require pytest/Ruff in CI before deploy. Dependencies: none. Acceptance: repeatable Python 3.12 green runs with no cloud credentials/network. Tests: run twice, future date, network denial, intentional CI failure. Risk: tests may reveal additional real defects. Effort: M. **Blocks release and all safe refactoring: yes.**

### Phase 1 - Correctness baseline

**V9-P1-01: Transactional usage and question submission**

Goal/modules: atomic quota, ledger, idempotency, question state, and reconciliation. Dependencies: V9-P0-04. Acceptance: every ambiguous retry converges to one question and one usage event. Tests: write-step failure injection and concurrency. Risk: historical ledger repair. Effort: L. **Blocks paid access release: yes.**

**V9-P1-02: Conditional teacher claims and relationship writes**

Goal/modules: transactional takeover/session and parent forward/reverse binding. Dependencies: V9-P0-02. Acceptance: one winner per claim and symmetric relationship state. Tests: concurrent writers, timeout, reconciliation. Risk: legacy asymmetric data. Effort: M. **Blocks teacher beta: yes.**

**V9-P1-03: Idempotent billing command boundary**

Goal/modules: Stripe checkout command, exact return-origin allowlist, provider reconciliation. Dependencies: V9-P0-04 and configured Stripe test mode. Acceptance: one business request creates at most one provider session; ambiguous failures recover. Tests: provider/local failures and retries. Risk: provider semantics and historical sessions. Effort: L. **Blocks paid beta: yes.**

**V9-P1-04: Reproducible runtime and dependency baseline**

Goal/modules: Python 3.12 pin, clean Lambda Linux-arm64 import, dependency upgrades, Ruff zero, staged mypy baseline. Dependencies: green tests. Acceptance: clean checkout reproduces artifact and no unaccepted high/critical advisory. Tests: artifact hash/provenance, package import, dependency scan. Risk: framework upgrade behavior. Effort: M. **Blocks release: yes.**

**V9-P1-05: Gated deployment pipeline**

Goal/modules: GitHub Actions, branch protection, staging/version/alias promotion, smoke and rollback. Dependencies: V9-P0-04 and V9-P1-04. Acceptance: failed gates cannot deploy; promoted artifact digest matches tested artifact. Tests: staging smoke and rollback drill. Risk: AWS role/alias migration. Effort: L. **Blocks release: yes.**

### Phase 2 - Complete core product journeys

**V9-P2-01: Authoritative mobile auth and account journey**

Goal/modules: repair Expo dependency matrix/lockfile; backend-led registration, verification, sign-in, restore, sign-out, role navigation. Dependencies: V9-P0-01 and V9-P1-04. Acceptance: new student and parent complete the journey on iOS and Android with real sandbox accounts. Tests: typecheck, component, Cognito sandbox, device E2E. Risk: Cognito client migration. Effort: XL. **Blocks mobile beta: yes.**

**V9-P2-02: Student learning journey**

Goal/modules: functional dashboard, question upload/submit/idempotency, AI answer, escalation, practice lesson/answer/mistakes. Dependencies: V9-P0-03, V9-P1-01, BUG-005 contract fix. Acceptance: no placeholder screen in the core journey and state survives restart/retry. Tests: API contract, component, offline/error, device E2E. Risk: backend response convergence. Effort: XL. **Blocks mobile beta: yes.**

**V9-P2-03: Parent payment and visibility journey**

Goal/modules: bound children, usage, entitlements, checkout, billing status, notifications. Dependencies: V9-P0-02, V9-P1-03. Acceptance: parent sees only bound children and paid entitlement changes follow signed provider events. Tests: Stripe test mode plus device E2E. Risk: historical profile/entitlement drift. Effort: L. **Blocks paid beta: yes.**

**V9-P2-04: Decide and complete communication delivery**

Goal/modules: either integrate WebSocket routes/mobile reconnect and approved push/email providers, or adopt documented polling for v9.0; implement or explicitly remove passwordless login claims. Dependencies: IaC ownership and provider approvals. Acceptance: one selected communication path has live evidence and fallback behavior. Tests: reconnect/dedupe/background/provider failure. Risk: external approvals. Effort: L/XL. **Blocks only the advertised real-time/passwordless scope.**

### Phase 3 - Security and production hardening

**V9-P3-01: Automated security regression suite**

Goal/modules: auth matrix, JWT client/rotation, object isolation, redirects, rate limits, webhook replay, log redaction. Dependencies: Phase 0/1 fixes. Acceptance: tests fail on reintroduced vulnerabilities and run in CI. Tests: all named negative cases plus history secret scan and dependency policy. Risk: test-environment fidelity. Effort: L. **Blocks external beta: yes.**

**V9-P3-02: Versioned infrastructure, schema, backup, and restore**

Goal/modules: import/create AWS resources in IaC; document indexes and additive migrations; automate backup/restore. Dependencies: infrastructure ownership. Acceptance: clean staging deploy and sampled restore from versioned definitions. Tests: synth/diff/deploy, drift, restore, rollback. Risk: importing live resources. Effort: XL. **Blocks production readiness: yes.**

**V9-P3-03: Operational observability and resilience**

Goal/modules: readiness, correlation, redacted structured logs, metrics, alarms, timeout/retry policy, runbooks. Dependencies: V9-P1-05 and IaC. Acceptance: synthetic failures produce actionable signals and request correlation. Tests: dependency outage, timeout, alarm, runbook exercise. Risk: noisy alarms/cost. Effort: L. **Blocks production readiness: yes.**

**V9-P3-04: Live release evidence gate**

Goal/modules: backend/mobile artifacts, admin-only API checks, read-only browser/device smoke, provider sandbox, rollback evidence. Dependencies: all release blockers. Acceptance: evidence ties timestamp, environment, SHA, artifact digest, request IDs, and redacted result to an approval. Tests: full staging candidate and controlled production read-only smoke. Risk: credential/provider access. Effort: M. **Blocks production release: yes.**

### Phase 4 - Architecture and performance

**V9-P4-01: DynamoDB access-pattern correction**

Goal/modules: exact keys/GSIs and complete pagination for practice, WebSocket, admin, tutor, and report paths. Dependencies: versioned schema/IaC and measured data shapes. Acceptance: no first-page omission; documented capacity/latency target met. Tests: multi-page fixtures and load/cost benchmark. Risk: backfill/index cost. Effort: XL. **Blocks scale, not internal development.**

**V9-P4-02: Incremental domain boundary extraction**

Goal/modules: split authorization, billing command, adaptive evidence, admin/report use cases from large files. Dependencies: green characterization tests and stable APIs. Acceptance: reduced change blast radius with behavior parity. Tests: existing suite plus characterization/failure injection. Risk: regression from premature abstraction. Effort: XL, incremental. **Does not block initial beta after earlier gates.**

**V9-P4-03: Documentation and milestone truth reconciliation**

Goal/modules: README, `.env.example`, architecture maps, release evidence, roadmap status vocabulary. Dependencies: prior decisions. Acceptance: clean-checkout instructions pass and every milestone distinguishes contract/integration/live/product completion. Tests: doc command smoke and environment-key coverage. Risk: documentation drift if done early. Effort: M. **Does not block core development but is required for closeout.**

## 10. Top 10 Next Actions

1. Disable public creation/confirmation of `admin`, `teacher`, and `tutor` roles; audit existing Cognito privileged group membership.
2. Apply one parent/teacher/student resource-authorization policy to every affected route and add the negative matrix.
3. Remove pre-answer `correctAnswer` fields and enforce uploaded-object ownership before OCR.
4. Fix the 12 failing tests, block ambient AWS access, inject time, and make Python 3.12 pytest/Ruff mandatory before deployment.
5. Make question quota, usage ledger, idempotency record, and question creation one recoverable transaction.
6. Replace teacher read-then-write takeover and parent binding writes with conditional/transactional operations.
7. Add Stripe checkout idempotency/reconciliation and exact callback-origin allowlisting; verify in Stripe test mode.
8. Repair and lock the Expo dependency matrix, then implement backend-authoritative mobile registration/sign-in/session behavior.
9. Add staging/versioned deployment, artifact provenance, dependency scanning, smoke, and rollback before production alias promotion.
10. Bring infrastructure/schema/backup ownership into version control, then finish real mobile journeys and one selected real-time notification path.

## 11. Audit Change Scope

This audit changes documentation only:

- `docs/audit/full-project-audit.md`
- `docs/audit/findings.json`

No application behavior, API, database schema, cloud resource, production data, or test assertion was changed. Findings remain open until separately implemented and verified.
