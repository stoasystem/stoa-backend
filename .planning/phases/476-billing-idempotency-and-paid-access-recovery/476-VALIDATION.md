---
phase: 476
slug: billing-idempotency-and-paid-access-recovery
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-24
---

# Phase 476 — Validation Strategy

> Per-phase validation contract for task feedback, external preflight, ASVS L1 closure, Stripe sandbox acceptance, and final source-bound evidence.

## Test Infrastructure

| Property | Backend | Web / Provider |
|----------|---------|----------------|
| **Framework** | pytest 9.0.3, pytest-asyncio 1.4.0, moto 5.2.1, time-machine 3.2.0, Ruff | TypeScript 5.9.3, Playwright 1.60.0, existing npm scripts, Stripe Python SDK 15.2.0 |
| **Config file** | `pyproject.toml`, `tests/conftest.py`, Phase 474 formal gate | `/Users/zhdeng/stoa-frontend/playwright.config.ts`, Phase 474 Web verifier |
| **Quick run command** | `PYTHONPATH=. .venv/bin/pytest -q -x tests/test_billing_checkout_commands.py tests/test_billing_webhook_convergence.py tests/test_token_allowances.py` | `cd /Users/zhdeng/stoa-frontend && npm run typecheck` |
| **Focused task target** | One named test file or bounded pair from the task map, then Ruff on changed Python files | One named Playwright spec plus typecheck; lint when the plan modifies linted source |
| **Phase full command** | Phase 474 authoritative backend/Web gate, then `PYTHONPATH=. .venv/bin/pytest -q tests/test_phase476_security_gate.py tests/test_phase476_evidence.py` | `cd /Users/zhdeng/stoa-frontend && npm run test:e2e -- billing-paid-access.spec.ts --project=stripe-sandbox` after Plan 27 preflight |
| **Feedback latency target** | ≤60 seconds for focused unit/repository/API tasks | ≤180 seconds for focused typecheck/mock-independent browser tasks; ≤900 seconds for the one external sandbox candidate |

The Phase 474 command remains the authoritative full-suite/build-once gate. Phase 476 adds focused behavior, provider, threat, and evidence selectors; it does not invent a competing global release gate.

## Sampling Rate And Continuity

- **After every task commit:** run the exact `<automated>` command in the task map. A task is not complete on typecheck/lint alone when it owns behavior tests.
- **After every backend wave:** run all Phase 476 backend tests introduced or modified through that wave, with `-q -x`, then Ruff on changed Python files.
- **After every Web wave:** run `npm run typecheck`, the focused Playwright specs introduced or modified through that wave, and lint for changed Web source.
- **After Plans 04 and 16:** verify the source-bound non-production migration preview and Bedrock count-capability receipt; missing external authority is a blocking authentication checkpoint, not a passing mock.
- **After Plan 27:** run all sandbox-preflight negative controls. Do not run Plan 28 until approved non-production origins, test Prices, signed destination/version/method set, and test credentials pass.
- **Once per immutable provider candidate:** run Plan 28's `stripe-sandbox` project and capture one source/config/run-bound receipt. Do not repeatedly create provider Sessions merely to sample local changes.
- **Before Plan 29 publication:** run the Phase 474 authoritative gate, all Phase 476 focused backend/Web selectors, Plan 28 receipt verifier, and the ASVS L1 security gate.
- **Before `$gsd-verify-work`:** Plan 29 evidence verification is green, `openHighCount=0`, and production charge/mutation/smoke remain exact `NOT RUN`.
- **Sampling continuity:** every implementation task has an automated selector; there are zero consecutive unverified tasks.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior / Required Fixtures | Test Type | Automated Command | File Exists / Wave 0 | Feedback Latency | Status |
|---------|------|------|-------------|------------|-------------------------------------|-----------|-------------------|----------------------|------------------|--------|
| 476-01-01 | 01 | 1 | V9BILL-01..04 | T-476-01-H | Closed billing/allowance DTO fixtures; no legacy aliases or payment-proof hint | contract/unit | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_contracts.py && .venv/bin/ruff check src/stoa/models/billing.py src/stoa/models/allowance.py tests/test_billing_contracts.py` | ❌ W0 creates `tests/test_billing_contracts.py` | ≤60s | ⬜ pending |
| 476-02-01 | 02 | 1 | V9BILL-03 | T-476-02-H | Production/staging/local exact-origin positives plus lookalike/userinfo/encoded/backslash/wrong-port/wildcard negatives | parameterized unit | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_callback_urls.py && .venv/bin/ruff check src/stoa/config.py src/stoa/services/billing_callback_service.py tests/test_billing_callback_urls.py` | ❌ W0 creates exact-origin matrix | ≤60s | ⬜ pending |
| 476-03-01 | 03 | 2 | V9BILL-01,04 | T-476-03-H | Four-plan Settings/profile/default fixtures; distinct test Prices; live-key refusal | contract/config | `PYTHONPATH=. .venv/bin/pytest -q tests/test_plan_identity_contract.py && .venv/bin/ruff check src/stoa/models/user.py src/stoa/config.py src/stoa/routers/auth.py tests/test_plan_identity_contract.py` | ❌ W0 creates semantic identity fixture | ≤60s | ⬜ pending |
| 476-04-01 | 04 | 3 | V9BILL-02,04 | T-476-04-H | Canonical/unambiguous/ambiguous/malformed/changed rows and historical-trial evidence; redacted non-production preview receipt | migration/failure injection | `PYTHONPATH=. .venv/bin/pytest -q tests/test_plan_identity_migration.py tests/test_plan_identity_contract.py && PYTHONPATH=. .venv/bin/python -m stoa.jobs.migrate_billing_plan_identity verify-preview --results docs/security/phase-476-plan-migration-preview.json` | ❌ W0 creates test and authorized preview schema; external receipt required | ≤60s local; ≤300s preview | ⬜ pending |
| 476-05-01 | 05 | 2 | V9BILL-01,02 | T-476-05-H | Dynamo command/guard/public-ref transaction, 20-caller barrier, lease/ambiguous-commit fixtures | repository/concurrency | `PYTHONPATH=. .venv/bin/pytest -q tests/test_checkout_command_repo.py && .venv/bin/ruff check src/stoa/db/repositories/checkout_command_repo.py tests/test_checkout_command_repo.py` | ❌ W0 creates repository fixture | ≤60s | ⬜ pending |
| 476-06-01 | 06 | 3 | V9BILL-01,03 | T-476-06-H | Ordered fake Stripe create, response-loss, binding/cardinality, server callback, test/live matrix | service/API integration | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_checkout_commands.py && .venv/bin/ruff check src/stoa/services/subscription_service.py src/stoa/routers/parents.py tests/test_billing_checkout_commands.py` | ❌ W0 creates provider fake; exact origin config required | ≤60s | ⬜ pending |
| 476-07-01 | 07 | 4 | V9BILL-01,02 | T-476-07-H | Open/complete/already-expired/unknown/concurrent supersession and prior-entitlement byte stability | service/race | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_checkout_supersession.py tests/test_billing_checkout_commands.py && .venv/bin/ruff check src/stoa/services/subscription_service.py src/stoa/db/repositories/checkout_command_repo.py tests/test_billing_checkout_supersession.py` | ❌ W0 creates supersession matrix | ≤60s | ⬜ pending |
| 476-08-01 | 08 | 4 | V9BILL-02 | T-476-08-H | Required partial-failure matrix, fail-if-create sentinel, exact object mismatch, lease recovery | service/failure injection | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_reconciliation.py && .venv/bin/ruff check src/stoa/services/billing_reconciliation_service.py tests/test_billing_reconciliation.py` | ❌ W0 creates reconciliation matrix | ≤60s | ⬜ pending |
| 476-09-01 | 09 | 5 | V9BILL-02,04 | T-476-09-H | Parent/admin ownership/capability, closed schemas, same-ref recheck, no-manual-success OpenAPI | API/authorization | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_recheck_apis.py tests/test_route_authorization_inventory.py && .venv/bin/ruff check src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_billing_recheck_apis.py` | ❌ W0 creates API fixture; route inventory exists | ≤60s | ⬜ pending |
| 476-10-01 | 10 | 2 | V9BILL-02,04 | T-476-10-H | Same/different Event IDs, reverse/equal-time facts, CAS and transaction-failure fixtures | repository/state machine | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_fact_repo.py && .venv/bin/ruff check src/stoa/db/repositories/billing_fact_repo.py tests/test_billing_fact_repo.py` | ❌ W0 creates fact fixtures | ≤60s | ⬜ pending |
| 476-11-01 | 11 | 5 | V9BILL-02,04 | T-476-11-H | Unsigned/wrong-secret/mutated/live events; legacy/Basil Invoice; duplicate/order/concurrency joint predicate | webhook integration | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_webhook_convergence.py && .venv/bin/ruff check src/stoa/routers/billing.py src/stoa/services/subscription_service.py src/stoa/services/billing_reconciliation_service.py tests/test_billing_webhook_convergence.py` | ❌ W0 creates signed event fixtures | ≤60s | ⬜ pending |
| 476-12-01 | 12 | 6 | V9BILL-02,04 | T-476-12-H | One/three beneficiary, zero/four, relationship race, future-child, duplicate, upgrade-preservation fixtures | service/transaction | `PYTHONPATH=. .venv/bin/pytest -q tests/test_paid_entitlement_grants.py && .venv/bin/ruff check src/stoa/services/paid_entitlement_service.py src/stoa/services/entitlement_service.py tests/test_paid_entitlement_grants.py` | ❌ W0 creates grant fixtures | ≤60s | ⬜ pending |
| 476-13-01 | 13 | 7 | V9BILL-02,04 | T-476-13-H | Before/at/after period and grace boundaries, recovery, replay, no-delete and failed-upgrade fixtures | time travel/integration | `PYTHONPATH=. .venv/bin/pytest -q tests/test_paid_entitlement_transitions.py && .venv/bin/ruff check src/stoa/services/paid_entitlement_service.py src/stoa/services/entitlement_service.py src/stoa/services/attachment_service.py tests/test_paid_entitlement_transitions.py` | ❌ W0 creates time-machine fixture | ≤60s | ⬜ pending |
| 476-14-01 | 14 | 8 | V9BILL-04 | T-476-14-H | First-activation race, missing historical evidence, one-microsecond boundary, preserved-read fixture | time travel/concurrency | `PYTHONPATH=. .venv/bin/pytest -q tests/test_free_trial_window.py && .venv/bin/ruff check src/stoa/services/free_trial_service.py src/stoa/services/entitlement_service.py src/stoa/routers/auth.py tests/test_free_trial_window.py` | ❌ W0 creates trial fixture; Plan 04 preview required | ≤60s | ⬜ pending |
| 476-15-01 | 15 | 3 | V9BILL-04 | T-476-15-H | Exact budget table, Zurich DST windows, counter barriers, replay/restoration/redaction | repository/time/concurrency | `PYTHONPATH=. .venv/bin/pytest -q tests/test_token_allowances.py && .venv/bin/ruff check src/stoa/db/repositories/allowance_repo.py src/stoa/services/allowance_service.py tests/test_token_allowances.py` | ❌ W0 creates allowance fixtures | ≤60s | ⬜ pending |
| 476-16-01 | 16 | 4 | V9BILL-04 | T-476-16-H | Exact-model CountTokens/usage shapes, caller inventory, generation fail-if-called, source/config/IAM-bound redacted receipt | provider contract/preflight | `PYTHONPATH=. .venv/bin/pytest -q tests/test_bedrock_usage_evidence.py && PYTHONPATH=. .venv/bin/python scripts/probe_bedrock_token_count.py verify --results docs/security/phase-476-bedrock-token-count-preflight.json` | ❌ W0 creates provider fakes and receipt schema; approved AWS test access required | ≤60s local; ≤300s preflight | ⬜ pending |
| 476-17-01 | 17 | 5 | V9BILL-04 | T-476-17-H | Reserve/provider/validation/store/finalize/restore/disconnect/replay failure matrix | route/failure injection | `PYTHONPATH=. .venv/bin/pytest -q tests/test_question_token_finalization.py tests/test_phase475_question_effect_recovery.py && .venv/bin/ruff check src/stoa/routers/questions.py tests/test_question_token_finalization.py` | ❌ W0 creates question allowance fixture; passing Plan 16 receipt required | ≤60s | ⬜ pending |
| 476-18-01 | 18 | 5 | V9BILL-04 | T-476-18-H | Regular/SSE/hint/title/retry/validation/store/timeout/disconnect/replay matrix | route/failure injection | `PYTHONPATH=. .venv/bin/pytest -q tests/test_conversation_token_finalization.py tests/test_phase473_message_command.py && .venv/bin/ruff check src/stoa/routers/conversations.py tests/test_conversation_token_finalization.py` | ❌ W0 creates conversation fixture; passing Plan 16 receipt required | ≤60s | ⬜ pending |
| 476-19-01 | 19 | 8 | V9BILL-04 | T-476-19-H | Question/conversation admission, messages/replies, per-beneficiary/shared-family limits, final-slot barrier, denial/DST | service/concurrency | `PYTHONPATH=. .venv/bin/pytest -q tests/test_teacher_support_allowances.py && .venv/bin/ruff check src/stoa/services/teacher_support_allowance_service.py src/stoa/routers/questions.py src/stoa/routers/conversations.py tests/test_teacher_support_allowances.py` | ❌ W0 creates support-case fixture | ≤60s | ⬜ pending |
| 476-20-01 | 20 | 8 | V9BILL-04 | T-476-20-H | Month-end/DST, method replacement, recipient/channel dedupe, conservative email eligibility, partial failure, card canaries | notification/time/integration | `PYTHONPATH=. .venv/bin/pytest -q tests/test_payment_method_expiry_reminders.py && .venv/bin/ruff check src/stoa/services/payment_reminder_service.py src/stoa/services/notification_service.py src/stoa/db/repositories/notification_repo.py tests/test_payment_method_expiry_reminders.py` | ❌ W0 creates reminder fixtures | ≤60s | ⬜ pending |
| 476-21-01 | 21 | 9 | V9BILL-02,04 | T-476-21-H | Role-safe arithmetic/lifecycle/beneficiary/reminder/provider-evidence projections and canaries | API/projection | `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_allowance_projections.py && .venv/bin/ruff check src/stoa/routers/parents.py src/stoa/routers/admin.py src/stoa/services/subscription_service.py tests/test_billing_allowance_projections.py` | ❌ W0 creates projection fixture | ≤60s | ⬜ pending |
| 476-22-01 | 22 | 4 | V9BILL-01,04 | T-476-22-H | Exact four Web literals, CHF catalog, locale keys, non-purchasable trial, masked billing type | frontend contract | `cd /Users/zhdeng/stoa-frontend && npm run typecheck && npm run lint -- --quiet` | Existing type/catalog/locales become contract fixtures | ≤180s | ⬜ pending |
| 476-23-01 | 23 | 10 | V9BILL-01,02,04 | T-476-23-H | Repeat/refresh/timeout key/ref, request body, beneficiary/cardinality, supersession confirmation, no-demo production config | browser contract | `cd /Users/zhdeng/stoa-frontend && npm run typecheck && npm run test:e2e -- billing-command-ui.spec.ts --project=chromium` | ❌ W0 creates `billing-command-ui.spec.ts` | ≤180s | ⬜ pending |
| 476-24-01 | 24 | 11 | V9BILL-02,04 | T-476-24-H | Four-state authoritative result, query/path/foreign-ref negatives, same-ref recheck, bounded polling, accessibility | browser state | `cd /Users/zhdeng/stoa-frontend && npm run typecheck && npm run test:e2e -- billing-result-states.spec.ts --project=chromium` | ❌ W0 creates result-state fixture | ≤180s | ⬜ pending |
| 476-25-01 | 25 | 11 | V9BILL-04 | T-476-25-H | Parent/selected/unselected student, allowance boundaries, in-app-only/email-failed/resolved reminder, DOM/storage/trace canaries | browser role/accessibility | `cd /Users/zhdeng/stoa-frontend && npm run typecheck && npm run test:e2e -- billing-allowance-reminder.spec.ts --project=chromium` | ❌ W0 creates allowance/reminder fixture | ≤180s | ⬜ pending |
| 476-26-01 | 26 | 11 | V9BILL-02,04 | T-476-26-H | Admin capability, same-ref recheck, no manual success, dependency state, DOM/storage/trace redaction | browser authorization | `cd /Users/zhdeng/stoa-frontend && npm run typecheck && npm run test:e2e -- admin-billing-recovery.spec.ts --project=chromium` | ❌ W0 creates admin recovery fixture | ≤180s | ⬜ pending |
| 476-27-01 | 27 | 12 | V9BILL-04 | T-476-27-H | Negative controls for mock/interception/live/missing/production/secret-artifact inputs; positive redacted metadata receipt | browser preflight | `cd /Users/zhdeng/stoa-frontend && npm run typecheck && npm run test:e2e -- stripe-sandbox-preflight.spec.ts --project=chromium` | ❌ W0 creates preflight script/spec; no real credential required for negative controls | ≤180s | ⬜ pending |
| 476-28-01 | 28 | 13 | V9BILL-01..04 | T-476-28-H | Hosted Stripe domain, one command/Session, signed event order/replay, exact grants/allowance, parent/admin state, no-live-charge receipt | real sandbox E2E | `PYTHONPATH=. .venv/bin/pytest -q tests/test_phase476_sandbox_evidence.py && cd /Users/zhdeng/stoa-frontend && npm run test:e2e -- billing-paid-access.spec.ts --project=stripe-sandbox` | ❌ W0 creates E2E/evidence verifier; approved sandbox setup required | ≤900s | ⬜ pending |
| 476-29-01 | 29 | 14 | V9BILL-01..04 | T-476-29-H | Exactly 29 structured ASVS L1 models; unique threats; source-bound selectors; nonzero on open/unproved High; redacted receipt | security gate | `PYTHONPATH=. .venv/bin/pytest -q tests/test_phase476_security_gate.py && PYTHONPATH=. .venv/bin/python scripts/verify_phase476_security_gate.py verify --plans-dir .planning/phases/476-billing-idempotency-and-paid-access-recovery --results docs/security/phase-476-threat-gate.json` | ❌ W0 creates security-gate fixtures; all prior receipts required | ≤180s | ⬜ pending |
| 476-29-02 | 29 | 14 | V9BILL-01..04 | T-476-29-H | Exact GOAL/REQ/RESEARCH/CONTEXT/threat coverage, semantic plan identity, sandbox/source binding, privacy and NOT RUN semantics | evidence gate | `PYTHONPATH=. .venv/bin/pytest -q tests/test_phase476_security_gate.py tests/test_phase476_evidence.py && PYTHONPATH=. .venv/bin/python scripts/capture_phase476_evidence.py verify --threat-gate docs/security/phase-476-threat-gate.json --results docs/security/phase-476-evidence-results.json --markdown docs/security/phase-476-evidence.md` | ❌ W0 creates evidence fixtures; Plan 28 and threat-gate receipts required | ≤300s | ⬜ pending |

*Status for all rows: ⬜ pending until execution. `❌ W0` means the plan's TDD RED step must create the named test/fixture before production changes.*

## Wave 0 Requirements

### Test and fixture scaffolds

- [ ] Plan 01: `tests/test_billing_contracts.py`
- [ ] Plan 02: `tests/test_billing_callback_urls.py`
- [ ] Plans 03–05: `tests/test_plan_identity_contract.py`, `tests/test_plan_identity_migration.py`, `tests/test_checkout_command_repo.py`
- [ ] Plans 06–11: checkout-command, supersession, reconciliation, recheck API, billing-fact, and webhook-convergence fixtures
- [ ] Plans 12–16: grant, transition, free-trial, token-allowance, and Bedrock usage/preflight fixtures
- [ ] Plans 17–21: question/conversation finalization, support-case, reminder, and role-projection fixtures
- [ ] Plans 23–28: six focused Playwright specs plus sandbox evidence verifier; Plan 22 uses existing type/catalog/locale surfaces
- [ ] Plan 29: `tests/test_phase476_security_gate.py`, `tests/test_phase476_evidence.py`, threat/evidence receipt schemas

### External preflight dependencies

- [ ] Plan 02 exact-origin configuration rejects missing environment values; Plan 27 records only approved non-production origin digests.
- [ ] Plan 04 runs the read-only non-production legacy plan/trial preview. Any unavailable authority or unresolved evidence stays blocking.
- [ ] Plan 16 runs the exact configured Bedrock count-capability probe. Mocks and character estimates cannot satisfy it.
- [ ] Plan 20's email resolver treats absent/unknown deliverability as in-app-only; no external guess is required.
- [ ] Plan 27 verifies sandbox destination API version, enabled payment methods, three test Prices, signed destination, exact origins, and mock/live refusal.
- [ ] Plan 28 receives approved Stripe sandbox secrets/config through `user_setup`; it may not run on production or fall back to intercepted routes.

## Stripe Sandbox Manual / External Checkpoints

| Checkpoint | Owner action or external state | Automated fail-closed test | Required evidence | Downstream block |
|------------|--------------------------------|----------------------------|-------------------|------------------|
| Exact origins | Supply approved non-production Web/API origins outside git | Plan 02 structural matrix; Plan 27 origin/config preflight | Origin/environment digests only | Plan 06 provider create on invalid config; Plan 28 acceptance |
| Sandbox catalog | Supply `sk_test_` access and three recurring CHF test Price IDs | Plan 27 rejects live/missing/duplicate/mismatched Price modes | Test-mode Price digests and `livemode=false` | Plan 28 |
| Signed destination | Configure reachable sandbox event destination, pinned API version, required event set, signing secret | Plan 27 destination/version/method preflight; Plan 28 real signed delivery | Destination/version/method-set digests and signed Event receipt | Plan 28 and 29 |
| Test payment method | Use only Stripe-documented sandbox/test payment data in hosted Checkout | Plan 28 asserts Stripe-hosted test domain and test-mode objects | Hosted Session/Invoice/Subscription/Event redacted IDs | Plan 29 |
| Duplicate/order exercise | Resend/reorder through authorized Workbench/API or public signed destination, never handcrafted unsigned HTTP | Plan 28 evidence verifier requires signed delivery and one activation/grant/allowance version | Event-order/dedupe dispositions | Plan 29 |
| Candidate binding | Freeze exact backend/frontend source SHAs before provider run | Plans 28/29 reject source mismatch | Source SHAs, config digest, run ID | Final publication |

Authentication failures are dynamic execution checkpoints: the executor attempts the read-only or sandbox command first, pauses only when the provider requires user authentication/configuration, and retries the same command afterward. Missing credentials or external configuration never becomes a passing local placeholder.

## No-Live-Charge Evidence Contract

The following are mandatory for Plan 28 and reverified by Plan 29:

- `STRIPE_SECRET_KEY` mode is test; the receipt records only `keyMode=test`, never the key.
- Every Price, Checkout Session, Invoice, Subscription, PaymentMethod, and Event inspected for acceptance has `livemode=false`.
- Browser traffic reaches a Stripe-hosted sandbox/test Checkout and has zero Playwright route interception.
- The run records exactly one local command and one Stripe Session for each logical purchase fixture; duplicate/retry/recheck creates zero additional payable Session.
- Signed-event evidence is produced by the configured sandbox destination; unsigned handcrafted HTTP cannot satisfy acceptance.
- `realCustomerChargeCount=0`, `liveProviderMutationCount=0`, and `productionMutationCount=0` are explicit machine-verified fields.
- Production checkout, charge, bulk reminder, deployment, smoke, and rollback remain exact `NOT RUN`, not PASS.
- Evidence/privacy scans reject Stripe keys, signing secrets, full provider IDs, checkout URLs, PAN, CVC, PII, prompts, answers, and browser idempotency keys.

## ASVS L1 Security Gate

- Every Plan 01–29 frontmatter contains `threat_model.asvs_level: L1`, nonempty assets/trust boundaries, a unique threat ID, severity, mitigation, automated verification, and `open_high_allowed: false`.
- Every body threat register explicitly states ASVS L1 and High severity.
- Each task acceptance criteria and plan verification block completion on an open, unobserved, or source-unbound High threat.
- Plan 29 Task 01 writes `docs/security/phase-476-threat-gate.json` only when every High/Critical threat is `mitigated_verified` by an observed selector on the exact candidate.
- The gate exits nonzero for `planned`, `open`, `accepted`, `waived`, missing, stale, duplicate, unknown, or unobserved High/Critical entries.
- Plan 29 Task 02 consumes the gate receipt and refuses publication when `openHighCount != 0` or source/selector coverage differs.

## Multi-Source Coverage Audit

| SOURCE | ID | Feature / constraint | Plan(s) | Status | Notes |
|--------|----|----------------------|---------|--------|-------|
| GOAL | — | One parent checkout request produces one recoverable provider/local billing and entitlement outcome | 05–14, 23–29 | COVERED | Plan 29 requires observed source-bound completion |
| REQ | V9BILL-01 | Required Web/backend/Stripe/local idempotency produces at most one active Session | 05–07, 23, 28–29 | COVERED | Command-first and hosted-sandbox proof |
| REQ | V9BILL-02 | All provider/local/browser/webhook partial failures converge to one support state | 05–13, 17–18, 21, 24, 26, 28–29 | COVERED | Required failure-injection matrix mapped above |
| REQ | V9BILL-03 | Exact configured callback origin and approved fixed path | 02, 06, 27–29 | COVERED | SEC-008 negative matrix and external origin preflight |
| REQ | V9BILL-04 | Real Stripe sandbox browser and signed webhook change exact entitlement/quota once and remain explainable | 11–29 | COVERED | Mocks cannot satisfy Plans 28/29 |
| RESEARCH | R-COMMAND | Durable command/open guard/provider-call intent before Stripe | 05–08 | COVERED | Stable key and ambiguity recovery |
| RESEARCH | R-URL | Server-built structurally parsed exact origin plus fixed result path | 02, 06, 27 | COVERED | No request/browser origin authority |
| RESEARCH | R-FACTS | Signed fact-oriented duplicate/out-of-order webhook convergence | 10–11 | COVERED | No global cross-object timestamp order |
| RESEARCH | R-GRANTS | Explicit beneficiary grants and monotonic upgrade/downgrade/grace/storage behavior | 12–14 | COVERED | Includes historical-trial fail-closed migration |
| RESEARCH | R-TOKENS | Provider usage evidence, CountTokens preflight, reservation/finalization/restoration, Zurich weeks | 15–18 | COVERED | Plan 16 external receipt blocks governed use |
| RESEARCH | R-SUPPORT | One durable support case consumes once under beneficiary/family weekly scope | 19 | COVERED | Messages/replies consume zero |
| RESEARCH | R-REMINDER | Safe payment projection, month-end schedule, conservative email eligibility, per-channel fan-out | 20–21, 25 | COVERED | Unknown email remains in-app-only |
| RESEARCH | R-WEB | Authoritative Web command/result/allowance/admin state with no demo success | 22–26 | COVERED | TanStack Query and real backend contracts |
| RESEARCH | R-MIGRATION | Runtime plan/trial migration preview, ambiguity quarantine, build/config identity audit | 03–04, 14, 22, 29 | COVERED | No legacy alias guess |
| RESEARCH | R-SANDBOX | Mock-disabled test-mode preflight, signed hosted journey, no-live-charge evidence | 27–29 | COVERED | External configuration stays fail closed |
| RESEARCH | R-VALIDATION | Nyquist task map, failure injection, full-suite cadence, ASVS L1 source-bound closure | 01–29 | COVERED | This validation contract plus Plan 29 gate |
| CONTEXT | D-01 | Three paid plans; free trial visible but never purchasable | 01, 03, 06, 22–23, 28–29 | COVERED | Exact paid/free CTA and provider refusal |
| CONTEXT | D-02 | One-to-one four-plan identity; remove legacy/tutor active translations | 01, 03–04, 22, 29 | COVERED | Migration inputs only |
| CONTEXT | D-03 | Refresh/timeout/repeat resumes one command/Session | 05–06, 23, 28 | COVERED | Stable browser/local/provider identity |
| CONTEXT | D-04 | Confirmed plan change expires/proves/supersedes before new command | 07, 23, 28 | COVERED | At most one payable Session |
| CONTEXT | D-05 | Return begins confirming and blocks a second checkout | 09, 23–24, 28 | COVERED | Redirect is not proof |
| CONTEXT | D-06 | Recheck original operation only and never create | 08–09, 24, 26, 28 | COVERED | No-create dependency and request assertions |
| CONTEXT | D-07 | Failed/canceled/expired attempt preserves previous active access | 07, 13, 23 | COVERED | Byte-stability tests |
| CONTEXT | D-08 | Redacted admin read/recheck; no manual paid state | 09, 21, 26, 29 | COVERED | Capability and OpenAPI/source gate |
| CONTEXT | D-09 | Backend constructs full URLs from exact environment config | 02, 06, 27 | COVERED | External values are preflight inputs |
| CONTEXT | D-10 | Opaque reference/navigation hint is never payment proof | 01–02, 09, 24 | COVERED | Four-state query-negative matrix |
| CONTEXT | D-11 | Exactly confirming/active/not completed/support needed | 01, 09, 21, 24 | COVERED | Typed backend/Web contract |
| CONTEXT | D-12 | Exact per-environment origins; reject all bypass classes | 02, 27, 29 | COVERED | SEC-008 matrix |
| CONTEXT | D-13 | Signed first-invoice-paid plus active-subscription proof | 10–11, 28 | COVERED | No redirect/session/admin shortcut |
| CONTEXT | D-14 | Explicit one/up-to-three active bound beneficiaries | 01, 06, 12, 23, 28 | COVERED | Revalidated at create and activation |
| CONTEXT | D-15 | Immediate upgrade without counter/storage reset | 12–13, 21 | COVERED | Higher limits, same aggregates |
| CONTEXT | D-16 | Period-end cancel/downgrade, three-day grace, free fallback, no deletion | 13, 21, 25 | COVERED | Exact time-travel and storage proof |
| CONTEXT | D-17 | Monotonic idempotent duplicate/delayed/out-of-order signed events | 10–13, 28–29 | COVERED | One activation/grant/allowance version |
| CONTEXT | D-18 | Actual provider input/output weekly allowances and role projections | 01, 15–18, 21–22, 25 | COVERED | Separate exact dimensions |
| CONTEXT | D-19 | Exact four-plan weekly token budgets | 01, 15, 22, 25 | COVERED | Exact table tests |
| CONTEXT | D-20 | One admitted support case; exact beneficiary/family weekly limits | 01, 19, 21, 25 | COVERED | No per-message/minute debit |
| CONTEXT | D-21 | Europe/Zurich Monday weeks, DST-correct, no rollover | 15, 19–21, 25 | COVERED | Local-calendar boundaries |
| CONTEXT | D-22 | Finalize only durable safe readable result; restore terminal non-delivery, retain provider cost | 15, 17–18, 29 | COVERED | Failure matrices and evidence |
| CONTEXT | D-23 | Immutable 14-day first-activation trial; preserve reads after expiry | 03–04, 14, 19, 25 | COVERED | Missing history fails closed |
| CONTEXT | D-24 | Parent and beneficiaries receive email/in-app/persistent reminder | 20–21, 25, 28 | COVERED | SMS/native push excluded |
| CONTEXT | D-25 | Same safe billing information and masked method only | 20–21, 25–26, 29 | COVERED | Card/secret canaries |
| CONTEXT | D-26 | Zurich month-end minus seven days; replace clears; once per method/month | 20, 25, 29 | COVERED | Calendar/idempotency matrix |
| CONTEXT | D-27 | Verified deliverable email only; in-app fallback; isolated failure | 20–21, 25 | COVERED | Conservative resolver |

Deferred Context ideas—real charging, production mutation/bulk reminders/rollout, native/mobile/push/SMS/app-store billing, broader routes, additional markets/annual billing/coupons/rollover/CRM—are intentionally excluded and are not audit gaps.

## Validation Sign-Off

- [x] All 30 tasks across 29 plans have an automated verification command.
- [x] Every task names required fixtures and a feedback-latency target.
- [x] Sampling continuity has no unverified task gap.
- [x] Wave 0 covers every new test/evidence/preflight fixture.
- [x] External Stripe/AWS/migration state is fail-closed and never replaced by mocks for exit evidence.
- [x] No watch-mode flags appear.
- [x] ASVS L1 and zero-open-High enforcement are source-bound to Plan 29.
- [x] No-live-charge and exact production `NOT RUN` evidence are mandatory.
- [x] `nyquist_compliant: true` is set in frontmatter.
- [ ] `wave_0_complete: true` may be set only after execution creates and runs all Wave 0 fixtures.

**Approval:** planning contract complete; execution evidence pending
