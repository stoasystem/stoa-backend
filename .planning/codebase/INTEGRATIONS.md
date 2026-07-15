---
last_mapped_commit: ddd2a559cb3f5c82345252fdef0d4c948f0c2155
last_mapped_date: 2026-07-15
---

# Integrations

**Mapped:** 2026-07-15
**Scope:** Full repository, incrementally refreshed from `.gitignore`, `.planning`, `docs`, and `mobile`

## Summary

The backend integrates with AWS Cognito, DynamoDB, S3, Bedrock, Rekognition, SQS, SES, Lambda, and API Gateway, with additional billing/provider surfaces documented by the repository audit. The mobile scaffold integrates with the backend HTTP API, Cognito through AWS Amplify, Expo push services, SQLite, SecureStore, and EAS distribution contracts.

Repository planning distinguishes declared/local integration contracts from live provider evidence. `.planning/STATE.md` and `docs/audit/full-project-audit.md` currently block broad rollout on mobile buildability, infrastructure ownership, provider verification, and end-to-end journey evidence.

## AWS Cognito

Backend authentication and user identity are implemented with Cognito.

Relevant backend files:

- `src/stoa/config.py`
- `src/stoa/deps.py`
- `src/stoa/routers/auth.py`
- `src/stoa/routers/students.py`

Key backend behaviors:

- `src/stoa/deps.py` validates Cognito access tokens against JWKS from the configured user pool.
- Role and identity resolution use Cognito claims plus backend-owned identity data and authorization policy.
- `.planning/STATE.md` records the canonical active role set as `student|parent|teacher|admin` and says historical aliases are rejection/reconciliation inputs only.
- Rejected legacy evidence: the former `tutor` label and compatibility route are not active product vocabulary; `teacher` is the sole current teacher-role/API term.

Mobile Cognito integration is implemented in `mobile/src/services/auth/amplifyAuth.ts`:

- `configureAmplifyAuth` configures a user-pool client from `mobile/src/config/mobileConfig.ts`.
- Sign-in, sign-up, email confirmation, resend, session restore, access-token retrieval, and sign-out use Amplify Auth APIs.
- `mobile/src/services/api/mobileApiClient.ts` obtains a fresh session access token and attaches it to backend requests.
- `mobile/src/services/auth/secureSessionMetadata.ts` limits SecureStore use to session-adjacent metadata.

This mobile path is not currently authoritative or integration-safe. `docs/audit/full-project-audit.md` reports that direct mobile Cognito sign-up bypasses backend identity provisioning, role claim handling is incompatible, and the single mobile client contract conflicts with backend role-aware clients. Backend-led registration/session behavior and sandbox evidence are required before the mobile auth integration is considered complete.

## DynamoDB

The backend uses a single-table DynamoDB design configured by backend settings.

Relevant files include:

- `src/stoa/db/dynamodb.py`
- `src/stoa/db/repositories/user_repo.py`
- `src/stoa/db/repositories/question_repo.py`
- `src/stoa/db/repositories/practice_repo.py`
- `src/stoa/db/repositories/report_repo.py`
- Direct access in backend routers for administration, conversations, parents, students, teachers, and historical compatibility paths.

Observed entity patterns preserved from the full-repository map include users, questions, reports, practice content, student progress, mistakes, usage counters, conversations/messages/notes, and teacher sessions. Observed secondary-index use includes email, student, and parent lookup indexes.

Observed key patterns:

- Users: `PK=USER#{user_id}`, `SK=PROFILE`.
- Questions: `PK=QUESTION#{question_id}`, `SK=META`.
- Reports: `PK=REPORT#{report_id}`, `SK=SUMMARY`.
- Practice content: `PK=PRACTICE`, with `SK` prefixes for subjects, topics, units, lessons, and challenges.
- Student progress: `PK=PROGRESS#{user_id}`, `SK=LESSON#{lesson_id}`.
- Mistakes: `PK=MISTAKES#{user_id}`, `SK=ATTEMPT#{uuid}`.
- Usage counters: `PK=USAGE#{student_id}`, with date-scoped chat or hint sort keys.
- Conversations: `PK=CONV#{conversation_id}`, with conversation, message, and note sort keys.
- Teacher sessions: `PK=SESSION#{session_id}`, `SK=META`.

Observed index usage:

- `GSI-Email` in `src/stoa/db/repositories/user_repo.py`.
- `GSI-StudentId` in `src/stoa/db/repositories/question_repo.py` and `src/stoa/routers/conversations.py`.
- `GSI-ParentId` in `src/stoa/db/repositories/report_repo.py`.

The scoped audit in `docs/audit/full-project-audit.md` reports that complete infrastructure/schema bootstrap and zero-to-live reproducibility are not present in this repository, so runtime table/index assumptions remain externally provisioned.

## Amazon S3 and Rekognition

S3 supports direct client image uploads and provider-side OCR input.

Relevant files:

- `src/stoa/routers/files.py`
- `src/stoa/services/ocr_service.py`
- `src/stoa/config.py`

The backend presigns image uploads under user-scoped object paths. `src/stoa/services/ocr_service.py` passes the S3 object reference to Rekognition, keeps line-level detections, sorts them spatially, and treats OCR failure as non-fatal in the question flow.

The presign endpoint accepts common image formats, validates an image content type, and generates an upload key rather than proxying file bytes through FastAPI. Rekognition receives the bucket/key reference and returns line-level text ordered by vertical position.

The mobile student API adapter in `mobile/src/features/student/studentApi.ts` models question submission and teacher-help calls, but the current mobile scaffold does not yet establish a complete image-select/upload/submit journey. `docs/audit/full-project-audit.md` requires contract and device evidence before that path is release-ready.

## Amazon Bedrock

Bedrock provides AI learning answers, hints, conversation titles, and report-related generation through backend services such as:

- `src/stoa/services/ai_service.py`
- `src/stoa/routers/conversations.py`
- `src/stoa/routers/practice.py`

The backend owns model invocation and student-visible output shaping; the mobile client accesses these capabilities only through authenticated backend endpoints. Provider payloads and generated learning content are excluded from mobile persistence by `mobile/docs/ENVIRONMENT.md` and `mobile/docs/PUSH_OFFLINE.md`.

`src/stoa/services/ai_service.py` invokes the Bedrock runtime with Anthropic-style message payloads. Answer generation validates structured output and redacts internal terms; conversation flows include bounded recent history, practice can request a generated hint when static content is absent, and `src/stoa/routers/conversations.py` also generates conversation titles.

## Amazon SQS and SES

SQS supports teacher escalation from question flows through `src/stoa/services/notify_service.py` and `src/stoa/routers/questions.py`. SES supports weekly report email delivery through `src/stoa/services/notify_service.py`.

Teacher escalation sends a deduplicated, subject-grouped message to the configured FIFO queue. Weekly report delivery sends backend-generated HTML email through SES.

These are backend-only provider boundaries. Mobile callers use the HTTP API and do not receive direct provider credentials or payloads.

## Backend HTTP API

`mobile/src/services/api/mobileApiClient.ts` is the mobile-to-backend integration boundary. It:

- Builds requests from the configured API base URL.
- Acquires access tokens through Amplify session APIs.
- Sends JSON with bearer authorization.
- Normalizes non-success responses into `MobileApiError` with support-safe fields.

Feature adapters in `mobile/src/features/student/studentApi.ts`, `mobile/src/features/parent/parentApi.ts`, and `mobile/src/services/notifications/notificationApi.ts` model student, parent, and notification endpoints.

The integration is not contract-complete. `docs/audit/full-project-audit.md` identifies request-field alias mismatches in question idempotency and push device metadata, recommends an OpenAPI-generated/shared client, and requires real schema/API compatibility tests. Most adapter return types are still `unknown`, and most screens under `mobile/app/` do not execute the modeled journeys.

## Expo Notifications and Deep Links

Mobile push integration spans:

- `mobile/app.json` for the Expo Notifications plugin and app deep-link scheme.
- `mobile/src/services/notifications/pushNotifications.ts` for permission state, Expo push-token acquisition, and foreground presentation.
- `mobile/src/services/notifications/notificationApi.ts` for backend token registration/revocation and notification actions.
- `mobile/src/services/notifications/deepLinks.ts` for authenticated, account-ready, role-aware route validation.
- `mobile/docs/PUSH_OFFLINE.md` for privacy and online/offline policy.

Push registration is intended to send the Expo token to backend notification endpoints; notification payload route targets are treated only as navigation hints. Live push delivery is not established. Physical-device smoke, Expo/EAS project setup, Android provider credentials, and iOS notification credentials remain explicit blockers in `mobile/docs/PUSH_OFFLINE.md` and `mobile/docs/NATIVE_DISTRIBUTION.md`.

`docs/audit/full-project-audit.md` also reports that the declared notification icon asset is absent and that backend/mobile payload aliases are mismatched.

## Mobile Local Persistence

- `mobile/src/services/offline/readThroughCache.ts` uses Expo SQLite for approved read-through records.
- `mobile/src/services/offline/cachePolicy.ts` defines approved summary surfaces, TTLs, forbidden categories, and online-only mutation paths.
- `mobile/src/services/auth/secureSessionMetadata.ts` uses Expo SecureStore only for limited metadata.
- `mobile/src/services/auth/signOutCleanup.ts` coordinates local cleanup and optional push-token revocation.
- TanStack Query is configured in `mobile/src/providers/AppProviders.tsx` for in-memory server state.

`mobile/docs/AUTH.md` and `mobile/docs/PUSH_OFFLINE.md` forbid caching raw token material, provider/billing payloads, sensitive learning content, generated report artifacts, secrets, and private object keys. Question submission, teacher help, billing, subscription requests, and challenge answers are online-only.

## EAS, Native Platforms, and App Stores

`mobile/eas.json` defines development, preview, and production profiles. `mobile/src/release/buildDistribution.ts`, `mobile/src/release/credentialReadiness.ts`, `mobile/src/release/deviceQa.ts`, and `mobile/src/release/storeReadiness.ts` model build evidence, credentials, device QA, and store-readiness gates.

These are local contracts, not completed external integrations. `mobile/docs/NATIVE_DISTRIBUTION.md` explicitly records EAS project setup, native signing, platform push configuration, device QA, and public-store launch as blocked or out of scope until approved evidence exists.

## AWS Lambda, API Gateway, and Real-Time Delivery

The FastAPI backend is wrapped by Mangum in `src/stoa/main.py` for Lambda/API Gateway HTTP delivery. Deployment behavior is defined in `.github/workflows/deploy.yml`.

Mangum disables lifespan handling for the Lambda adapter. The deployment workflow packages and updates the API and report-processing Lambda surfaces described by the repository audit.

Existing backend conversation streaming is constrained by API Gateway buffering. Separately, `docs/audit/full-project-audit.md` reports that WebSocket service code has no complete API Gateway route/IaC integration and that `mobile/` has no WebSocket consumer. The current mobile communication path is therefore HTTP plus the incomplete push path; WebSocket delivery must either be completed end to end or explicitly replaced by polling for the target release.

## Billing and Other External Providers

The current repository audit in `docs/audit/full-project-audit.md` identifies Stripe-backed checkout/subscription behavior as an active backend integration and reports unresolved idempotency/reconciliation and callback-origin risks at the audited baseline. Mobile parent adapters expose subscription and billing endpoint shapes in `mobile/src/features/parent/parentApi.ts`, but real payment and lifecycle journeys are not implemented in the placeholder screens.

Other provider, support, analytics, and observability integrations referenced by `.planning/PROJECT.md` remain configuration- or evidence-gated. Planning artifacts must not be interpreted as proof of live provider connectivity.

## External HTTP

Backend external HTTP includes Cognito JWKS retrieval through `httpx` in `src/stoa/deps.py`, with a bounded timeout and cache behavior intended to span a Lambda execution environment. Mobile external HTTP is centralized through the platform `fetch` call in `mobile/src/services/api/mobileApiClient.ts`; direct AWS/business-provider access is intentionally avoided outside Amplify and Expo SDK boundaries.
