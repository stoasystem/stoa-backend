---
last_mapped_commit: 2026-06-02
---

# Architecture

**Mapped:** 2026-06-02
**Scope:** Full repository

## Summary

The service is a modular FastAPI backend organized around route modules, small service modules, Pydantic schemas, and DynamoDB repository helpers. It uses AWS Lambda as the production compute boundary and DynamoDB as the primary persistence layer.

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
- `/tutors` from `src/stoa/routers/tutors.py`
- `/parents` from `src/stoa/routers/parents.py`
- `/admin` from `src/stoa/routers/admin.py`
- `/files` from `src/stoa/routers/files.py`

## Layering

Observed layers:

- **Config:** `src/stoa/config.py`
- **Dependency injection/auth:** `src/stoa/deps.py`
- **HTTP routes:** `src/stoa/routers/*.py`
- **Pydantic models:** `src/stoa/models/*.py`, plus route-local request/response models.
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
2. The route normalizes `tutor` to backend role `teacher`.
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

There are two related help flows:

- Question escalation via `src/stoa/routers/questions.py`, `src/stoa/routers/teachers.py`, and `src/stoa/services/notify_service.py`.
- Conversation/tutor escalation via `src/stoa/routers/conversations.py` and `src/stoa/routers/tutors.py`.

Question escalation:

1. Student calls `/questions/{question_id}/request-teacher`.
2. Question status changes to `escalated`.
3. SQS receives a teacher request message.
4. Teacher route scans escalated questions, allows takeover, reply, and resolve.

Conversation escalation:

1. Student calls `/teacher-help/request`.
2. Conversation record is marked escalated.
3. A system message is stored in the conversation.
4. Tutor routes scan escalated conversations, expose request details, status updates, and notes.

## Data Model Shape

The data model is single-table DynamoDB with mixed direct lookup, GSI lookup, and scan access patterns.

Repository-backed entities:

- Users in `src/stoa/db/repositories/user_repo.py`
- Questions in `src/stoa/db/repositories/question_repo.py`
- Practice content/progress in `src/stoa/db/repositories/practice_repo.py`
- Reports in `src/stoa/db/repositories/report_repo.py`

Route-local direct table use:

- Conversations and tutor notes in `src/stoa/routers/conversations.py` and `src/stoa/routers/tutors.py`
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
