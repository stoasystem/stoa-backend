---
last_mapped_commit: 2026-06-02
---

# Conventions

**Mapped:** 2026-06-02
**Scope:** Full repository

## Code Style

- Python code is formatted in a conventional FastAPI style with route decorators and route-local request/response models.
- Ruff is configured in `pyproject.toml` with line length `100` and target `py312`.
- Imports are mostly grouped as standard library, third-party, then local package imports.
- Module docstrings are used across most source files to explain route or service purpose.

## Typing

- Modern Python union syntax is used, for example `str | None` in `src/stoa/routers/auth.py` and `src/stoa/config.py`.
- Pydantic models define most API request and response schemas.
- Some endpoints accept or return raw `dict`, especially where the frontend contract is broad or still evolving, such as `src/stoa/routers/practice.py` and `src/stoa/routers/tutors.py`.
- Repository helpers return `dict | None` or `list[dict]`.

## FastAPI Patterns

- Each route module owns an `APIRouter`.
- Routers are attached centrally in `src/stoa/main.py`.
- Auth-protected endpoints use `Depends(get_current_user)` or `Depends(require_role(...))`.
- Settings are injected with `Depends(get_settings)` when route code needs config.
- AWS clients are sometimes injected through dependencies, as in `src/stoa/routers/files.py`; elsewhere they are created directly with `boto3.client`.

## Role Pattern

- `src/stoa/deps.py` provides `require_role(*roles)` as a dependency factory.
- Roles are resolved on the JWT claims dictionary and stored as `claims["role"]`.
- Group names map to roles in `src/stoa/deps.py`: `students`, `parents`, `teachers`, and `admins`.
- Frontend `tutor` maps to backend `teacher` in `src/stoa/routers/auth.py`.
- Some tutor routes accept both `teacher` and `tutor`, for example `src/stoa/routers/tutors.py`.

## Configuration Pattern

- `src/stoa/config.py` uses `BaseSettings` with `.env` loading.
- `get_settings()` is `lru_cache`-decorated.
- The module also creates a global `settings = get_settings()`.
- Several modules import the global `settings` directly, for example `src/stoa/db/dynamodb.py`, `src/stoa/services/ai_service.py`, and `src/stoa/services/rate_limit.py`.

## AWS Client Pattern

- `src/stoa/deps.py` defines cached client/resource factories: DynamoDB, S3, Bedrock, Rekognition, and SQS.
- Some modules bypass those factories and instantiate clients inline with `boto3.client`, including `src/stoa/services/ai_service.py`, `src/stoa/services/ocr_service.py`, `src/stoa/services/notify_service.py`, and Cognito helpers.
- DynamoDB table access is centralized in `src/stoa/db/dynamodb.py`, but many routers use `get_table()` directly rather than repository abstractions.

## DynamoDB Pattern

- The table is single-table style with manually composed `PK` and `SK` values.
- Repositories use `boto3.dynamodb.conditions.Key` and `Attr`.
- Updates are usually hand-built `UpdateExpression` strings.
- Reserved attribute names are handled selectively through `ExpressionAttributeNames`, such as `#s` for status and `#n` for name.
- Query-based access is preferred where keys or GSIs exist; scans are used for admin, parent, teacher, and tutor aggregate/listing flows.

## Error Handling

- Route-level validation and authorization failures use `HTTPException`.
- Cognito `ClientError` is mapped to specific HTTP status codes in `src/stoa/routers/auth.py`.
- Non-critical AWS/AI side effects often use broad `except Exception` and continue:
  - OCR in `src/stoa/routers/questions.py`
  - AI answer generation in `src/stoa/routers/questions.py`
  - Role self-healing in `src/stoa/deps.py`
  - Title generation and metadata updates in `src/stoa/routers/conversations.py`
  - Tutor first-action updates in `src/stoa/routers/tutors.py`
- Logging exists in AI service, practice router, auth group-add fallback, and conversations; some broad catches are silent.

## Frontend Contract Style

- Several route modules explicitly mention alignment with frontend API contracts.
- API responses often use camelCase even though internal Python data is snake_case.
- Auth registration accepts extra onboarding fields with `model_config = {"extra": "allow"}` in `src/stoa/routers/auth.py`.
- Practice responses translate DynamoDB fields into frontend keys with helpers like `_build_challenge`, `_build_lesson`, and `_build_unit`.

## AI Harness Pattern

- `src/stoa/services/ai_service.py` constrains Bedrock calls through a fixed system prompt.
- Student input is sanitized for prompt-injection patterns before model invocation.
- The main answer path asks for strict JSON and uses repair/fallback parsing.
- Output validation checks for trivial output and leaked internal terms.
- History inclusion filters to student/assistant messages and merges consecutive same-role messages.

## Date and Time Pattern

- Most timestamps are ISO strings.
- Some files use `datetime.utcnow()`, while others use timezone-aware `datetime.now(timezone.utc)`.
- Daily limits use UTC calendar dates.

## Comments

- Comments are generally purposeful and explain integration quirks, frontend contract alignment, or AWS/Lambda behavior.
- `src/stoa/routers/conversations.py` documents the API Gateway buffering limitation for the SSE endpoint.
