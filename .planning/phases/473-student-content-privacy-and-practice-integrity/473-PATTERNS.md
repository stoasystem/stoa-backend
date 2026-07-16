# Phase 473 Pattern Map

**Mapped:** 2026-07-16  
**Inputs:** `473-CONTEXT.md`, `473-RESEARCH.md`

## Data Flow

```text
verified Actor
  -> create owner upload intent
  -> constrained S3 POST
  -> finalize: head + bounded byte validation
  -> validated upload intent
       -> atomic question/message association + durable attachment + quota
       -> OCR/document extraction through private server coordinates
  -> safe attachment summary in API history

practice content
  -> answer-free preview projection -> student overview/path/lesson/catalog
student answer
  -> durable attempt receipt -> answer-bearing result projection
teacher/admin
  -> scoped privileged answer projection
```

## Files and Closest Existing Analogs

| Planned file | Role | Closest analog | Pattern to preserve |
|--------------|------|----------------|---------------------|
| `src/stoa/models/attachment.py` | Upload/attachment request and response allowlists | `src/stoa/models/question.py` | Pydantic `extra="forbid"`, bounded fields, explicit response models |
| `src/stoa/security/attachment_errors.py` | Structured safe upload errors/actions | `src/stoa/security/errors.py`, `client_error_actions.py` | Stable code/message/correlation shape, no sensitive detail, exhaustive mapping |
| `src/stoa/db/repositories/attachment_repo.py` | Single-table records and transactions | `question_repo.py`, `capability_repo.py`, `subscription_service.py` transaction helper | Consistent reads, conditional expressions, `TypeSerializer`, safe cancellation mapping |
| `src/stoa/services/file_validation_service.py` | Signature/container/image validation | No direct analog; follow bounded parser style in report services | Pure functions, explicit limits, category-only failures |
| `src/stoa/services/attachment_service.py` | Lifecycle/quota/association orchestration | `teacher_application_service.py`, `usage_ledger_service.py` | Closed state transitions, injected time/client boundaries, idempotent retries |
| `src/stoa/jobs/upload_cleanup.py` | Scheduled bounded cleanup | `src/stoa/jobs/weekly_reports.py` | Thin handler, service delegation, bounded result summary |
| `src/stoa/models/practice.py` | Preview/result/privileged answer models | `src/stoa/models/question.py` | Separate allowlist schemas rather than field stripping |
| `src/stoa/services/practice_projection_service.py` | Answer-safe projections | `curriculum_service.py` builders | Central deterministic builders shared by route families |
| `tests/test_attachment_security.py` | Adversarial upload matrix | `tests/test_authorization_audit.py`, `tests/test_files.py` | Fake provider/table, mutation sentinels, redaction canaries |
| `tests/test_practice_privacy.py` | Recursive answer-leak and scope matrix | `tests/test_student_authorization_matrix.py`, `tests/test_practice.py` | Positive/negative Actor matrix and exact structured responses |

## Existing Patterns to Reuse

### Verified Actor as the only owner identity

Question and conversation routes already depend on Phase 472 Actor/resource dependencies. New upload routes should use `get_actor` or a dedicated student-Actor dependency and derive `owner_id = actor.user_id`. Do not restore `get_current_user` dictionaries or accept `studentId` for ownership.

### Load once, authorize, pass resolved value

`authorized_question_dependency` and `authorized_conversation_dependency` return `AuthorizedResource` containing both the `ResourceRef` and resolved value. Attachment dependencies should follow the same shape so handlers do not reload or authorize one record and act on another.

### Safe structured errors

`SecurityDecisionError.public_body()` returns exactly `code`, `message`, and `correlationId`; route adapters attach `X-Correlation-ID`. Attachment errors should preserve this transport shape and discard provider exception messages.

### Conditional single-table writes

`question_repo.record_daily_question_usage` uses conditional updates; `capability_repo` and `subscription_service` already serialize DynamoDB transaction items and call `table.meta.client.transact_write_items`. Reuse those transaction mechanics instead of hand-encoding attribute values differently.

### Route inventory metadata

Phase 472 route dependencies attach `authorization_specs` and explicit route classifications. New identifier-bearing upload/attachment/answer routes need executable metadata so `test_route_authorization_inventory.py` continues to fail closed.

### Test isolation

Existing focused tests build small FastAPI apps, override Actor/settings/audit dependencies, and monkeypatch repositories/providers. New tests should use the same pattern and must never reach ambient S3, DynamoDB, Rekognition or Bedrock.

## Key Integration Edits

### `src/stoa/routers/files.py`

Replace inline extension/MIME validation, UUID key construction and raw S3 exception handling with typed models and `attachment_service.create_upload_intent` / `finalize_upload`. Return opaque IDs plus POST fields, never `s3_key`.

### `src/stoa/models/question.py`

Replace `image_s3_key` with an opaque attachment reference contract. `QuestionResponse` should expose `has_image` and a safe attachment summary only.

### `src/stoa/routers/questions.py`

Resolve/consume the upload before OCR. Pass server-loaded object coordinates to `ocr_service`. Preserve response redaction and idempotent retry matching using attachment identity, not object key.

### `src/stoa/routers/conversations.py`

Thread `attachmentIds` through both normal and streaming paths, persist them on the student message, and include safe summaries in `ChatMessage`. Bind before AI invocation; never log extracted content or provider detail.

### `src/stoa/routers/practice.py`

Delete answer-bearing `_build_challenge` use from every student preview path. Submit answer by recording an attempt receipt first, then return a typed result. Add a separately authorized privileged answer route/model.

### `src/stoa/services/curriculum_service.py`

Split `_build_exercise` into answer-free preview and answer-bearing privileged projection. `explanation` must not remain in the preview projection merely because `answerKey` is omitted.

### `src/stoa/db/repositories/practice_repo.py`

Make attempt persistence record every attempt with `attempt_id`, owner, submitted answer, correctness and timestamp, and return/load the receipt. Phase 475 may later combine this with usage/analytics transactions.

## Naming and Contract Constraints

- Roles remain exactly `student|parent|teacher|admin`; never introduce `tutor`.
- External identifiers are `uploadId`, `attachmentId`, `attemptId`; S3 keys are internal only.
- “Upload intent” means short-lived and single-consumption. “Saved attachment” means durable and owner-reusable.
- Preview schemas never contain `correctAnswer`, `answerKey`, `explanation`, `correctFeedback`, or `incorrectFeedback`.
- Result/privileged schemas are explicit and never selected by an untrusted student boolean.
- Missing and foreign attachments have indistinguishable external responses.

## Patterns to Avoid

- Router-local string prefix authorization.
- `dict.pop("correctAnswer")` redaction after building an answer-bearing object.
- Direct `includeAnswers` on student routes.
- Quota checks followed by unconditional puts outside a transaction.
- Reusing the transient upload ID as a permanent attachment ID.
- Storing raw OCR/document extraction in API-facing message/question models.
