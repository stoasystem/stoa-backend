---
last_mapped_commit: 2026-06-02
---

# Concerns

**Mapped:** 2026-06-02
**Scope:** Full repository

## Summary

The codebase is compact and readable, but it has several production-readiness concerns: no tests, broad/silent exception handling, scan-heavy DynamoDB access paths, inconsistent AWS client injection, and identity/profile mismatches between Cognito `sub` and locally generated user IDs.

## No Current Tests

No `tests/` directory or test files were found.

Risk:

- Auth, role boundaries, AWS integrations, AI output parsing, and DynamoDB update expressions can regress without fast feedback.
- `pyproject.toml` declares testing dependencies, so the project appears intended to have tests.

Relevant files:

- `pyproject.toml`
- All route and service modules under `src/stoa/`

## Scan-Heavy DynamoDB Access

Several production routes use DynamoDB scans or broad queries with filters.

Examples:

- `src/stoa/routers/teachers.py` scans questions by `status`.
- `src/stoa/routers/tutors.py` scans conversations with `entity_type=conversation` and `escalated=True`.
- `src/stoa/routers/parents.py` scans users for children by `parent_id`.
- `src/stoa/routers/admin.py` scans user profiles and question records for stats.
- `src/stoa/db/repositories/practice_repo.py` queries all challenges then filters by `challenge_id`.

Risk:

- These paths are acceptable at small scale but can become slow, expensive, or incomplete as the table grows.
- Some scans do not paginate beyond the first page.

## Broad and Silent Exception Handling

Broad catches often keep flows resilient but can hide real failures.

Examples:

- `src/stoa/routers/questions.py` ignores OCR errors and AI call errors.
- `src/stoa/deps.py` suppresses failures during fallback Cognito/DynamoDB role lookup.
- `src/stoa/routers/conversations.py` suppresses title generation and conversation metadata update failures.
- `src/stoa/routers/tutors.py` suppresses first teacher access timestamp update failures.

Risk:

- Operational failures may not be visible.
- User-facing state can become inconsistent without logs or metrics.

## Cognito User ID vs Local User ID Mismatch

Registration creates a local UUID as `user_id` in `src/stoa/routers/auth.py`, while authenticated requests usually use Cognito `sub` from access tokens.

Related mitigation:

- `src/stoa/routers/students.py` tries direct lookup by `user["sub"]`, then falls back to Cognito email lookup.
- `src/stoa/deps.py` has a role fallback that can resolve by email.

Risk:

- Student-owned records may be keyed by Cognito `sub`, while profile records may be keyed by local UUID.
- Authorization checks using `user["sub"]` can disagree with profile IDs or parent/child links.
- Progress and question data may not line up with profile lookup if IDs differ.

## Inconsistent AWS Client Injection

`src/stoa/deps.py` provides cached AWS client dependencies, but many modules instantiate clients directly.

Examples:

- `src/stoa/services/ai_service.py`
- `src/stoa/services/ocr_service.py`
- `src/stoa/services/notify_service.py`
- Cognito client creation in `src/stoa/routers/auth.py`, `src/stoa/deps.py`, and `src/stoa/routers/students.py`.

Risk:

- Harder to mock in tests.
- Less consistent caching behavior.
- More duplicated region/client setup.

## AI Calls Are Synchronous in Request Path

Question submission and conversation message send call Bedrock during the HTTP request.

Relevant files:

- `src/stoa/routers/questions.py`
- `src/stoa/routers/conversations.py`
- `src/stoa/services/ai_service.py`

Risk:

- Lambda/API Gateway timeout budgets limit model latency.
- User experience depends directly on Bedrock availability.
- Retries and partial failure handling are limited.

## Pseudo-Streaming Limitation

`src/stoa/routers/conversations.py` exposes `/messages/stream`, but the code notes that API Gateway buffers full responses.

Risk:

- Clients may treat this as true streaming even though production behavior is buffered.
- Long model responses still complete before events are sent to the client.

## Input and File Upload Limits

`src/stoa/routers/files.py` defines `_MAX_FILE_SIZE = 10 * 1024 * 1024`, but the size limit is not enforced in the presign request or upload constraints.

Risk:

- Clients may upload objects larger than intended unless S3 bucket policy or frontend checks enforce limits.

## Challenge Answer Recording Drops Student Answer

`src/stoa/routers/practice.py` reads `student_answer`, but `src/stoa/db/repositories/practice_repo.py` `record_attempt` does not store it.

Risk:

- `GET /practice/mistakes` returns `yourAnswer` from `attempt.get("student_answer", "")`, which will be empty for recorded mistakes.

## Daily Question Limit Is Read-Based

`src/stoa/routers/questions.py` checks daily question limits by listing up to 200 questions and filtering dates.

Risk:

- This can miss questions beyond the limit window if more than 200 records exist or pagination is needed.
- It is less robust than the atomic counter pattern already used in `src/stoa/services/rate_limit.py`.

## Deployment Has No Tests or Static Checks

`.github/workflows/deploy.yml` builds and deploys on `main`, but does not run tests, Ruff, or mypy first.

Risk:

- Broken code can be packaged and deployed if import errors or runtime issues are introduced.

## Infrastructure Is External to Repo

The repo references existing AWS resources but does not define them.

Risk:

- DynamoDB table indexes, Cognito groups/clients, SQS FIFO queue, S3 buckets, IAM role, and Lambda settings must be managed elsewhere.
- Planning and testing need to account for hidden infrastructure contracts.
