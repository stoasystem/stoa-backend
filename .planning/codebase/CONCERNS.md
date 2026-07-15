---
last_mapped_commit: ddd2a559cb3f5c82345252fdef0d4c948f0c2155
last_mapped_date: 2026-07-15
---

# Concerns

**Mapped:** 2026-07-15
**Scope:** Whole-repository reference, incrementally refreshed from `.gitignore`, `.planning/`, `docs/`, and `mobile/`

## Current Release Posture

The backend has substantial locally tested behavior, but the repository does not yet support an honest beta or production-readiness claim. Phase 472 is complete and locally closes its privileged-identity and horizontal student-resource authorization findings; the remaining release risk is concentrated in later v9 phases, unavailable external evidence, a red full-suite baseline, an unsafe delivery path, non-atomic business writes, incomplete infrastructure/operations evidence, and a non-buildable placeholder mobile client.

Use `.planning/STATE.md` as the current status source and `.planning/ROADMAP.md` for ownership. Do not infer product or rollout readiness from historical milestone completion language in `.planning/PROJECT.md` or from the pre-Phase-472 inventory in `docs/audit/full-project-audit.md`.

## Closed Phase 472 Findings — Do Not Reopen As Active

The following concerns are locally closed and must not be reported as current implementation defects:

- Public self-registration no longer creates `admin` or `teacher` authority.
- Student-resource access now uses central actor/resource/action/purpose authorization instead of role-only parent or teacher access.
- Cognito token validation, issuer/client binding, JWKS isolation/rotation behavior, immutable subject binding, privileged grant lifecycle, route inventory, authorization evidence, and public provider-error projection have deterministic local closure evidence.
- `teacher` is the only active role/API term. Historical `tutor` occurrences are limited to exact rejected-input, negative-test, or controlled-reconciliation evidence and are not a compatibility role.

The current source-bound evidence is recorded in `docs/security/phase-472-evidence.md`, `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-22-SUMMARY.md`, and `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-VERIFICATION.md`. Those records separate local closure from external rollout and from later-phase ownership.

## External Security Evidence Is Still Unavailable

Phase 472's local controls do not prove real Cognito behavior. All six sandbox/provider rows in `docs/security/phase-472-evidence.md` remain `NOT RUN — approval/configuration unavailable`, including real app-client/group inventory, allowed-versus-wrong-client tokens, teacher invitation activation/replay, suspension with an old token, JWKS rotation, and provider-backed reconciliation.

Risk:

- Local doubles can prove fail-closed application logic but cannot establish deployed pool/client/group configuration or provider convergence.
- Beta or production rollout must not treat these rows as passed, and no production/provider mutation is implied by the local evidence.

Required direction:

- Preserve the explicit `NOT RUN` boundary until a separately approved non-production environment is configured.
- Bind any future external result to redacted request/build identifiers, cleanup evidence, source SHA, and the exact tested client configuration.

## Full Test Suite Remains Red — Phase 474 Ownership

The source-bound Phase 472 full-suite observation in `docs/security/phase-472-evidence.md` is **1106 tests: 1083 passed, 23 failed, 0 errors, 0 skips**. The same 23 failures are strict production `Settings` fixtures and are explicitly owned by Phase 474:

- 2 failures in `tests/test_external_activation_smoke.py`
- 3 failures in `tests/test_report_service.py`
- 18 failures in `tests/test_subscription_operations.py`

The fixtures construct production settings without the now-required Cognito issuer and access-client allowlists. They must be modernized without weakening production validation or reclassifying the failures as Phase 472 regressions.

Additional Phase 474 release concerns are recorded in `.planning/ROADMAP.md` and `.planning/STATE.md`:

- The target Python 3.12 verification baseline is not yet the repeatable default.
- Ruff, mypy, dependency, Linux-arm64 import, and artifact-provenance gates are not yet one protected delivery chain.
- The current main-to-Lambda workflow can deploy without first proving the exact source/artifact through required quality gates.
- Stale local artifact/runtime state can diverge from the source under review.

Until Phase 474 closes, a focused green security gate is not a green repository or a trustworthy release candidate.

## Student Content And Practice Privacy Remain Open

Phase 473 owns the still-open privacy/integrity concerns from `docs/audit/full-project-audit.md` and `.planning/ROADMAP.md`:

- Upload presigning and question association need authoritative owner, status, size/type, expiry, single-use, and post-upload validation boundaries.
- Foreign, reused, malformed, missing, oversized, or mismatched upload objects must fail with redacted errors.
- Student-facing practice preview/overview/path/lesson responses must not expose `correctAnswer` or answer-derived explanations before submission.

These concerns block safe implementation of the mobile question-upload and practice journeys even though Phase 472 now protects resource identity and access.

## Non-Atomic Core Writes Remain Deferred

Phase 475 retains the data-consistency concerns; Phase 472 did not close them:

- Question quota, ledger, upload, and question creation can diverge across retries or partial failures.
- Concurrent teacher takeover can still create competing ownership/session/notification outcomes. `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-REVIEW.md` explicitly keeps this race open.
- Parent/child forward and reverse relationship writes need atomic convergence and repair behavior.
- Rate-limit counters need capped/idempotent semantics under repeated rejection and provider failure.
- Practice attempt persistence must retain the submitted wrong answer so mistake review is truthful.

Required direction:

- Use conditional/transactional writes, stable idempotency identities, failure-injection tests, concurrency barriers, and dry-run/replay-safe repair tools.
- Keep the authorization decisions from Phase 472 intact while changing write convergence.

## Billing Recovery And Idempotency Are Not Proven

Phase 476 owns the paid-access consistency boundary described in `.planning/ROADMAP.md` and `docs/audit/full-project-audit.md`:

- A provider checkout can be created before all local billing/entitlement writes converge.
- Timeout or local-write failure can orphan provider state, and retry can create duplicate checkout outcomes without one durable command/idempotency identity.
- Webhook ordering, duplicate delivery, refund/recovery behavior, and provider/local reconciliation still require failure-injection and Stripe test-mode evidence.

Do not use local billing route breadth or historical readiness labels as proof of a recoverable paid journey.

## Mobile Foundation Is Not Build-Ready

The current mobile workspace is a source/readiness contract, not an installable product:

- `mobile/package.json` declares an Expo/React Native matrix but has no lockfile; `.planning/STATE.md` says the manifest is unresolvable.
- `mobile/docs/STACK.md` and `mobile/docs/RELEASE_EVIDENCE.md` state that dependencies were not installed and verification was limited to static/source contracts.
- `mobile/app.json` references `mobile/assets/notification-icon.png`, but no `mobile/assets/` directory exists.
- `mobile/docs/RELEASE_EVIDENCE.md` records no Expo native build, EAS build, physical-device QA, or live push smoke.
- `mobile/docs/NATIVE_DISTRIBUTION.md` keeps Expo project ownership, Apple/APNs, Android/FCM, device QA, monitoring, rollback, and rollout approval blocked or out of scope.

Phase 477 must lock a supported version matrix, commit a lockfile, pass clean install/doctor/typecheck/native builds, and capture internal build evidence before screen work is considered reliable.

## Mobile Auth And API Contracts Diverge From The Backend

`mobile/src/services/auth/amplifyAuth.ts` still signs users up directly with Cognito, bypassing the backend-authoritative registration command/profile/binding lifecycle established by Phase 472. Session restore reads `custom:roles` or `cognito:groups`, then accepts only singular `student`/`parent` values; this does not by itself prove convergence with the backend's canonical role and configured-client contract.

`mobile/scripts/validate-mobile-contracts.mjs` checks dependency names, route-group strings, and environment-variable strings. It does not install dependencies, execute the TypeScript adapters, validate payloads against OpenAPI, or prove a real student/parent register/verify/sign-in/restore flow.

Phase 477 owns backend-authoritative auth, normalized role/client behavior, generated/validated client types, casing convergence, and executable adapter tests. The external Cognito evidence boundary still applies after local contract repair.

## Core Mobile Routes Are Placeholder UI

Most user-facing routes render explanatory `StateCard` or `Text` content instead of executing their declared adapters and state models. Examples include:

- `mobile/app/auth/sign-in.tsx` and `mobile/app/auth/register.tsx`
- `mobile/app/student/index.tsx`, `mobile/app/student/practice.tsx`, `mobile/app/student/questions.tsx`, and `mobile/app/student/history.tsx`
- `mobile/app/parent/index.tsx`, `mobile/app/parent/billing.tsx`, and `mobile/app/parent/children/[childId].tsx`
- `mobile/app/notifications/index.tsx` and `mobile/app/notifications/[eventId].tsx`

`mobile/src/features/student/studentScreens.ts` and `mobile/src/features/parent/parentScreens.ts` define desired endpoint/state contracts, but those contracts are not the same as implemented journeys. Phase 478 owns replacing placeholders with real loading, empty, blocked, stale, error, retry, session-expiry, question/practice, parent-child, and paid-access flows after Phases 473, 475, 476, and 477 close.

Generated recovery actions in `docs/security/client-error-actions.json` are locally validated, but their web/mobile rendering and integration are also explicitly deferred to Phase 478.

## Infrastructure And Real-Time Delivery Are Not Reproducible

Authoritative infrastructure is not present in this repository according to `.planning/STATE.md` and `docs/audit/full-project-audit.md`. Runtime assumptions for Cognito clients/groups, DynamoDB tables/indexes, S3 lifecycle/policies, queues, API Gateway routes, alarms, backups, and restore behavior therefore cannot be synthesized or verified from this checkout alone.

The WebSocket repository/fanout behavior has local service coverage, but deployed `$connect`, `$disconnect`, subscribe/refresh routing, authorization, scalable pagination/cleanup, and a reconnecting mobile client are not integrated. Phase 479 must either import/version the authoritative resources and prove deployed behavior or keep real-time delivery unclaimed.

## Operational Visibility And Scalability Are Incomplete

The audit and v9 roadmap retain several whole-repository operational concerns:

- Scan-heavy or first-page-only DynamoDB access can become slow, expensive, or incomplete as data grows.
- Health checks and local service tests do not prove DynamoDB, S3, Cognito, queue, payment, email, AI-provider, or WebSocket readiness.
- Correlation, redacted structured logs, latency/error/business metrics, alarms, timeout/retry policy, and exercised runbooks are incomplete.
- Critical reads and fanout need pagination/load evidence; static checks can miss truncation.
- Staged deployment, immutable version/alias promotion, post-deploy smoke, and rollback of the exact tested digest are not yet established.

Phase 480 owns observability, pagination, staged promotion, and rollback evidence. Existing broad/silent exception handling and synchronous provider work remain especially fragile until failures become observable and bounded.

## Documentation, Planning, And Map Drift

Documentation is a current operational risk, not just polish:

- `docs/audit/full-project-audit.md` records stale setup/environment/codebase-map content and mobile text that claims controls are implemented while routes remain placeholders.
- The previous `.planning/codebase/CONCERNS.md` claimed there were no tests and used a date instead of a commit SHA as `last_mapped_commit`, while current evidence records a 1106-test suite.
- `.planning/STATE.md` warns that global GSD progress still scans 55 pre-v9 phase directories; historical phase records can distort current status, so `STATE.md` and roadmap analysis are the authoritative v9 sources until archival is handled safely.
- `.planning/ROADMAP.md` reserves final documentation/evidence reconciliation for later closeout, including README/environment coverage, map accuracy, honest completion vocabulary, and a source/deploy/evidence index.
- `.gitignore` excludes local environments, caches, secrets, and `dist/`; local build/cache state therefore cannot serve as durable shared evidence unless captured through versioned manifests and external CI/provider records.

Required direction:

- Compare each codebase map's `last_mapped_commit` to the source under planning and remap drifted scopes before using it as design evidence.
- Prefer current state/verification documents over historical milestone prose, and preserve historical records rather than deleting them to make progress output look clean.
- Keep secrets and sensitive identifiers out of maps, logs, release evidence, mobile caches, and provider evidence.

## Priority Order

1. Phase 473: student upload/content privacy and practice integrity.
2. Phase 474: repair the 23 strict `Settings` fixtures and establish deterministic gated delivery.
3. Phase 475/476: make learning, relationship, quota, billing, and entitlement writes converge under failure/retry/concurrency.
4. Phase 477: create an installable, contract-correct mobile foundation.
5. Phase 478: implement the real student and parent mobile journeys.
6. Phase 479/480: version infrastructure, integrate real-time delivery, and add operational/pagination/release resilience.
7. Final v9 closeout: reconcile documentation, evidence, accepted/deferred findings, and rollout truth without converting unavailable external checks into passes.
