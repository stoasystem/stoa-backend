---
last_mapped_commit: 2026-06-02
---

# Structure

**Mapped:** 2026-06-02
**Scope:** Full repository

## Top-Level Layout

- `README.md` — concise project overview, local setup, stack, and source layout.
- `pyproject.toml` — package metadata, direct dependencies, optional dev dependencies, Ruff and Pytest config.
- `requirements.txt` — production requirements exported by `uv`.
- `uv.lock` — lockfile for Python dependencies.
- `.env.example` — local environment variable template.
- `.github/workflows/deploy.yml` — production Lambda deployment workflow.
- `scripts/seed_practice.py` — DynamoDB seed script for ZAP Langgymnasium Zürich practice content.
- `src/stoa/` — Python package for the FastAPI backend.

## Source Package Layout

`src/stoa/` contains:

- `main.py` — app composition and Lambda handler.
- `config.py` — settings model and cached settings accessor.
- `deps.py` — FastAPI dependencies, auth validation, role guards, and AWS client factories.
- `routers/` — HTTP route modules.
- `models/` — shared Pydantic models.
- `services/` — AI/OCR/notification/rate-limit service helpers.
- `db/` — DynamoDB table wrapper and repository helpers.

## Routers

`src/stoa/routers/auth.py`

- Cognito registration, login, refresh, logout, and `/me`.
- Contains route-local request/response models.
- Normalizes frontend role `tutor` to backend role `teacher`.

`src/stoa/routers/conversations.py`

- Student AI conversation list/detail/create/send/stream.
- Conversation teacher-help request router.
- Contains direct DynamoDB helper functions and route-local Pydantic models.

`src/stoa/routers/practice.py`

- Practice subjects, overview, roadmaps, paths, lessons, challenge answers, mistakes, hints, and teacher-help placeholder.
- Contains response builder helpers for frontend contract shaping.

`src/stoa/routers/questions.py`

- One-off question submission, question retrieval, teacher escalation, and feedback.
- Uses question repository, user repository, OCR service, AI service, and notification service.

`src/stoa/routers/students.py`

- Student profile get/update.
- Student summary and question history.
- Resolves profiles by direct DynamoDB lookup or Cognito email lookup.

`src/stoa/routers/teachers.py`

- Escalated question queue, takeover, reply, and resolve endpoints.
- Persists teacher sessions directly in DynamoDB.

`src/stoa/routers/tutors.py`

- Tutor/teacher help-request queue, detail, status updates, notes, and stats.
- Scans escalated conversations and stores notes under conversation partitions.

`src/stoa/routers/parents.py`

- Parent child listing and weekly report lookup.
- Uses direct DynamoDB scan for child lookup and report repository for reports.

`src/stoa/routers/admin.py`

- Admin user listing, user update, and platform stats.
- Uses full-table scans for aggregate metrics.

`src/stoa/routers/files.py`

- S3 presigned PUT URL endpoint for direct image uploads.

## Models

`src/stoa/models/question.py`

- `QuestionStatus`
- `AIResponse`
- `SubmitQuestionRequest`
- `QuestionResponse`
- `FeedbackRequest`

`src/stoa/models/report.py`

- `WeeklyReportResponse`

`src/stoa/models/user.py`

- User-related enums and schemas; imported by admin routes for `SubscriptionTier`.

Many route modules define additional local request/response schemas close to the endpoint that uses them.

## Database Helpers

`src/stoa/db/dynamodb.py`

- Cached DynamoDB table accessor.

`src/stoa/db/repositories/user_repo.py`

- `put_user`
- `get_user`
- `get_user_by_email`

`src/stoa/db/repositories/question_repo.py`

- `put_question`
- `get_question`
- `list_by_student`
- `update_status`

`src/stoa/db/repositories/practice_repo.py`

- Practice content reads for subjects, topics, units, lessons, and challenges.
- Student progress and mistake writes/reads.

`src/stoa/db/repositories/report_repo.py`

- Weekly report put and GSI lookup by parent/week.

## Services

`src/stoa/services/ai_service.py`

- Bedrock AI tutoring prompt harness.
- Prompt injection sanitization.
- JSON parsing and output validation.
- Main answer generation and hint generation.

`src/stoa/services/ocr_service.py`

- Rekognition text extraction from S3 objects.

`src/stoa/services/notify_service.py`

- SQS teacher escalation enqueue.
- SES weekly report email send.

`src/stoa/services/rate_limit.py`

- DynamoDB atomic daily counters for chat messages and practice hints.

## Security Contracts

`src/stoa/security/`

- Immutable canonical Actor, account-status, and capability-grant contracts.
- Typed resource/action/purpose authorization inputs and repository protocols.
- Stable safe error taxonomy, allowlisted security-event projection, and generated client recovery actions.
- Policy evaluation, token verification, route inventory, onboarding, and reconciliation are implemented by later Phase 472 plans.

## Scripts

`scripts/seed_practice.py`

- Seeds mathematics practice content for ZAP Langgymnasium Zürich.
- Writes subject/topic/unit/lesson/challenge records to DynamoDB.
- Content is structured as Python data factory functions.

## Naming Conventions

- Python modules use snake_case.
- API responses often use frontend-facing camelCase, especially in route-local Pydantic models and response dictionaries.
- DynamoDB keys use uppercase entity prefixes: `USER#`, `QUESTION#`, `PRACTICE`, `CONV#`, `PROGRESS#`, `MISTAKES#`, `USAGE#`, `SESSION#`.
- Backend role names use `teacher`; frontend-facing display role maps that to `tutor`.

## Missing or Sparse Areas

- No `tests/` directory currently exists despite Pytest configuration.
- No infrastructure-as-code directory exists in the repository.
- No explicit OpenAPI contract artifact exists outside FastAPI route definitions.
