---
last_mapped_commit: 2026-06-02
---

# Testing

**Mapped:** 2026-06-02
**Scope:** Full repository

## Current Test State

No test files were found in the repository during mapping.

The project has testing dependencies and configuration, but there is no `tests/` directory currently present.

## Configured Test Tooling

`pyproject.toml` declares:

- `pytest>=8.2.0`
- `pytest-asyncio>=0.23.0`
- `moto[dynamodb,s3,sqs,ses,rekognition]>=5.0.0`

Pytest config:

- `asyncio_mode = "auto"`
- `testpaths = ["tests"]`

## Other Quality Tooling

`pyproject.toml` declares:

- `ruff>=0.4.0`
- `mypy>=1.10.0`

Ruff config:

- `line-length = 100`
- `target-version = "py312"`

No explicit mypy options are configured.

## Testable Units

Good candidates for unit tests:

- Role normalization and display mapping in `src/stoa/routers/auth.py`.
- Client ID selection in `src/stoa/routers/auth.py`.
- User output construction in `src/stoa/routers/auth.py`.
- JWT role resolution branches in `src/stoa/deps.py`.
- Prompt-injection sanitization in `src/stoa/services/ai_service.py`.
- AI response parsing and validation in `src/stoa/services/ai_service.py`.
- Message history formatting in `src/stoa/services/ai_service.py`.
- Practice response builders in `src/stoa/routers/practice.py`.
- Daily rate-limit counter behavior in `src/stoa/services/rate_limit.py`.
- Presign request validation in `src/stoa/routers/files.py`.

## Integration Test Targets

The declared `moto` extras suggest intended AWS integration tests.

Useful integration test targets:

- DynamoDB repository functions in `src/stoa/db/repositories/user_repo.py`.
- Question creation and status update in `src/stoa/db/repositories/question_repo.py`.
- Practice content reads and progress writes in `src/stoa/db/repositories/practice_repo.py`.
- Report lookup in `src/stoa/db/repositories/report_repo.py`.
- S3 presigned URL route in `src/stoa/routers/files.py`.
- SQS enqueue path in `src/stoa/services/notify_service.py`.
- Rekognition wrapper behavior in `src/stoa/services/ocr_service.py`, with mocked client responses.

## API Test Targets

FastAPI route tests should use `TestClient` or `httpx.AsyncClient` with dependency overrides.

High-value API tests:

- `/health` returns status/version.
- Auth registration handles duplicate Cognito users and role aliases.
- Protected routes reject missing/invalid credentials.
- Student-only routes reject non-student roles.
- Question submission stores pending questions and updates successful AI answers.
- Conversation message send stores both student and assistant messages.
- Practice challenge answer records mistakes only for incorrect answers.
- File presign rejects non-image content types and unsupported extensions.
- Teacher/tutor/admin routes enforce role boundaries.

## Testability Concerns

- Several modules import global `settings`, making environment changes and client injection harder in tests.
- Many modules instantiate `boto3.client` directly, making dependency override less consistent.
- Some route helpers are private but still directly testable.
- Broad exception handling can hide failures in tests unless assertions inspect side effects and logs.
- The lack of infrastructure definitions means DynamoDB table schema/index assumptions must be recreated in test fixtures.

## Suggested Baseline

A practical first test suite would include:

- `tests/test_health.py` for app boot and `/health`.
- `tests/test_ai_service.py` for parsing/sanitization without AWS.
- `tests/test_files.py` for presign validation with dependency overrides.
- `tests/test_rate_limit.py` for DynamoDB counter behavior with Moto.
- `tests/test_practice_builders.py` for frontend response shape stability.
- `tests/test_auth_roles.py` for role alias and role guard behavior.

## Verification Commands

Expected local commands once tests exist:

- `uv run pytest`
- `uv run ruff check src tests`
- `uv run mypy src`

At mapping time, tests were not run because there are no test files to execute.
