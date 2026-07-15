---
last_mapped_commit: ddd2a559cb3f5c82345252fdef0d4c948f0c2155
last_mapped_date: 2026-07-15
---

# Architecture

**Mapped:** 2026-07-15
**Scope:** Full repository

## Summary

The product combines a modular FastAPI backend with a separate Expo/React Native client under `mobile/`. The backend is organized around route modules, small service modules, Pydantic schemas, security-policy contracts, and DynamoDB repository helpers. It uses AWS Lambda as the production compute boundary and DynamoDB as the primary persistence layer; the mobile client consumes the same authenticated HTTP API rather than introducing another backend.

The dominant architecture is request/response HTTP API with synchronous AWS calls. There is no separate worker process in this repo; asynchronous-looking flows such as teacher escalation are represented by SQS messages or DynamoDB state transitions.

## Application Composition

`src/stoa/main.py` is the central composition root.

Responsibilities:

- Create `FastAPI(title="STOA API", ...)`.
- Disable `/docs` in production.
- Add CORS middleware using `settings.cors_origins`.
- Include all API routers under explicit prefixes.
- Expose `/health`.
- Export `handler = Mangum(app, lifespan="off")`.

Registered routers:

- `/auth` from `src/stoa/routers/auth.py`
- `/conversations` from `src/stoa/routers/conversations.py`
- `/teacher-help` from `src/stoa/routers/conversations.py`
- `/practice` from `src/stoa/routers/practice.py`
- `/questions` from `src/stoa/routers/questions.py`
- `/students` from `src/stoa/routers/students.py`
- `/teachers` from `src/stoa/routers/teachers.py`
- `/parents` from `src/stoa/routers/parents.py`
- `/admin` from `src/stoa/routers/admin.py`
- `/files` from `src/stoa/routers/files.py`

## Layering

Observed layers:

- **Config:** `src/stoa/config.py`
- **Dependency injection/auth:** `src/stoa/deps.py`
- **HTTP routes:** `src/stoa/routers/*.py`
- **Pydantic models:** `src/stoa/models/*.py`, plus route-local request/response models.
- **Authorization/security contracts:** `src/stoa/security/`
- **Repository helpers:** `src/stoa/db/repositories/*.py`
- **AWS service helpers:** `src/stoa/services/*.py`
- **Seed script:** `scripts/seed_practice.py`

The layering is pragmatic rather than strict. Some routers call repositories; others call DynamoDB directly through `get_table()`. Some services use dependency-provided AWS clients; others construct `boto3` clients directly.

## Data Flow: Authentication

Key files:

- `src/stoa/routers/auth.py`
- `src/stoa/deps.py`
- `src/stoa/db/repositories/user_repo.py`

Registration flow:

1. `POST /auth/register` receives frontend-shaped payloads, including camelCase fields.
2. The route accepts only canonical public roles; privileged teacher onboarding is outside public registration.
3. Cognito user is created and password is made permanent.
4. User is added to a role group.
5. A DynamoDB user profile is stored through `user_repo.put_user`.
6. Cognito login is attempted immediately and an access token is returned when successful.

Request auth flow:

1. FastAPI dependency `get_current_user` reads bearer token credentials.
2. JWKS is fetched and cached in `src/stoa/deps.py`.
3. The JWT is verified for issuer and `token_use=access`.
4. Role is resolved from Cognito groups, custom claim, or a best-effort DynamoDB/Cognito lookup.
5. Role-specific routes use `require_role(...)`.

## Data Flow: AI Question Answering

Key files:

- `src/stoa/routers/questions.py`
- `src/stoa/services/ocr_service.py`
- `src/stoa/services/ai_service.py`
- `src/stoa/db/repositories/question_repo.py`

Flow:

1. Student submits a question via `POST /questions`.
2. Daily question count is checked by listing the student's recent questions.
3. Optional uploaded image text is extracted with Rekognition.
4. A pending question item is written to DynamoDB.
5. Bedrock is called synchronously for an AI response.
6. If successful, the question status becomes `ai_answered`; if not, the question remains `pending`.
7. The route returns the question item shape as `QuestionResponse`.

## Data Flow: Multi-Turn Conversations

Key file:

- `src/stoa/routers/conversations.py`

Flow:

1. Student creates or opens a conversation.
2. Message sends are rate-limited with `check_and_record_chat`.
3. Prior messages are read from DynamoDB before persisting the new message.
4. The student message is saved.
5. Bedrock is called with recent student/assistant history.
6. The assistant message is saved.
7. The conversation summary is updated with `updated_at`, preview text, and optionally an AI-generated title.

The streaming endpoint uses Server-Sent Events formatting but still performs the AI call before returning. The code notes that API Gateway buffers the response.

## Data Flow: Practice

Key files:

- `src/stoa/routers/practice.py`
- `src/stoa/db/repositories/practice_repo.py`
- `scripts/seed_practice.py`

Practice content is pre-seeded under `PK=PRACTICE` and read by subject/topic/unit/lesson/challenge prefixes. Student progress, attempts, mistakes, hints, and dashboard projections are built from DynamoDB records.

The practice router transforms DynamoDB records into frontend contract fields, especially camelCase response keys such as `gradeLevel`, `currentLessonId`, `estimatedMinutes`, and `canAskLearningAssistant`.

## Data Flow: Human Help

There are two related teacher-help flows:

- Question escalation via `src/stoa/routers/questions.py`, `src/stoa/routers/teachers.py`, and `src/stoa/services/notify_service.py`.
- Conversation escalation through the conversation and teacher route boundaries.

Question escalation:

1. Student calls `/questions/{question_id}/request-teacher`.
2. Question status changes to `escalated`.
3. SQS receives a teacher request message.
4. Teacher route scans escalated questions, allows takeover, reply, and resolve.

Conversation teacher escalation:

1. Student calls `/teacher-help/request`.
2. Conversation record is marked escalated.
3. A system message is stored in the conversation.
4. Teacher routes expose authorized request details, status updates, and notes.

## Authorization Architecture

Phase 472 establishes a deny-first authorization boundary around the request handlers. The canonical inputs are actor, resource, action, and purpose contracts in `src/stoa/security/`; executable FastAPI dependency metadata is the source for both runtime decisions and generated route evidence.

The checked artifacts in `docs/security/` are architectural projections rather than hand-maintained API definitions:

- `docs/security/route-authorization-inventory.json` is a deterministic inventory of registered method/path operations and their executable authorization metadata.
- `docs/security/client-error-actions.json` is the generated client recovery-action contract.
- `docs/security/phase-472-evidence.md` binds verification results and artifact hashes to the tested source while explicitly separating local evidence from unavailable external checks.
- `docs/security/tutor-term-allowlist.json` is negative historical evidence used by the terminology gate; `teacher` is the only active role and API term.

Authorization-sensitive decisions are evidence-before-effect. Public identity-provider failures are projected through a closed, redacted error boundary, and audit identities use bounded fingerprints rather than raw resource or actor identifiers.

## Mobile Client Boundary

`mobile/` is an Expo Router application and independent package boundary whose runtime entry point is `expo-router/entry` from `mobile/package.json`.

Composition and flow:

1. `mobile/app/_layout.tsx` creates the root stack and installs `mobile/src/providers/AppProviders.tsx`.
2. `mobile/app/index.tsx` redirects into the public sign-in route.
3. Files under `mobile/app/` are route entry points for auth, student, parent, notification, and blocked-account screens.
4. Route entries delegate journey rendering and data contracts to `mobile/src/features/` and shared state components in `mobile/src/ui/`.
5. `mobile/src/services/api/mobileApiClient.ts` is the authenticated API boundary and obtains a current Cognito access token from `mobile/src/services/auth/amplifyAuth.ts` for each request.

The mobile client recognizes only `student` and `parent` product roles. `mobile/src/navigation/routes.ts` holds the route/guard/deep-link contract, while notification targets are translated and revalidated after sign-in, account readiness, and role checks in `mobile/src/services/notifications/deepLinks.ts`. Deep links are navigation hints, never authorization.

Mobile data is intentionally split by authority:

- Online mutations, including question submission, teacher help, billing, subscription actions, and challenge answers, remain server-authoritative.
- Approved read-only summaries may use the SQLite read-through boundary in `mobile/src/services/offline/` and must expose stale state.
- Auth tokens stay under Amplify session management; local secure storage is restricted to non-token session metadata and is cleared with cached state during sign-out.
- Push registration uses Expo notification tokens and the backend notification endpoints; provider credentials and physical-device evidence remain release prerequisites rather than source-code fallbacks.

The mobile configuration root is `mobile/src/config/mobileConfig.ts`. It reads only public runtime coordinates, distinguishes development/preview/production channels, and enforces no-demo-fallback behavior for release builds.

## Planning And Evidence Boundary

`.planning/` is a versioned engineering-control plane, not application runtime input. Top-level `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, and `config.json` describe the active milestone and workflow state. Historical milestone records live under `.planning/milestones/`; active or retained phase workspaces live under `.planning/phases/<phase-number>-<slug>/`.

Phase workspaces use numbered plans and summaries plus lifecycle evidence such as `*-CONTEXT.md`, `*-RESEARCH.md`, `*-VALIDATION.md`, `*-VERIFICATION.md`, and `*-REVIEW.md`. Exact artifact names vary when a phase needs a domain-specific audit, runbook, release gate, or evidence ledger. `.planning/codebase/` contains the current whole-repository maps, while `.planning/research/` and `.planning/debug/` retain cross-phase research and resolved diagnostic narratives.

`docs/audit/` is the durable full-project audit boundary. `docs/security/` contains generated or source-bound security evidence intended for deterministic checks and review. Neither directory should contain secrets, raw credentials, tokens, or private provider payloads.

## Terminology Boundary

`teacher` is the sole active human-help role and API term. The older role label appears only in rejected historical evidence and the exact semantic allowlist at `docs/security/tutor-term-allowlist.json`; it must not name current routes, request fields, capabilities, or product behavior.

## Data Model Shape

The data model is single-table DynamoDB with mixed direct lookup, GSI lookup, and scan access patterns.

Repository-backed entities:

- Users in `src/stoa/db/repositories/user_repo.py`
- Questions in `src/stoa/db/repositories/question_repo.py`
- Practice content/progress in `src/stoa/db/repositories/practice_repo.py`
- Reports in `src/stoa/db/repositories/report_repo.py`

Route-local direct table use:

- Conversations and teacher-help notes in `src/stoa/routers/conversations.py` and the teacher route boundary.
- Student profile updates in `src/stoa/routers/students.py`
- Admin scans in `src/stoa/routers/admin.py`
- Parent child lookups in `src/stoa/routers/parents.py`
- Teacher sessions in `src/stoa/routers/teachers.py`

## Error Handling Pattern

Error handling is a mix of:

- Explicit `HTTPException` with FastAPI status codes.
- AWS `ClientError` mapping in auth and some Cognito/profile code.
- Broad `except Exception` fallbacks for non-fatal AI, OCR, title generation, role self-healing, and DynamoDB metadata updates.

This keeps user flows resilient but can hide operational failures unless logging exists at the catch site.

## Deployment Architecture

The app is packaged as code plus dependencies and updated into an existing Lambda function. Infrastructure definitions are not present in this repo; AWS resources are expected to exist externally.
