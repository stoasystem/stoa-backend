# Phase 473 Research: Student Content Privacy And Practice Integrity

**Researched:** 2026-07-16  
**Phase:** 473  
**Requirements:** V9PRIV-01, V9PRIV-02, V9PRIV-03  
**Audit findings:** SEC-003, SEC-005, BUG-001

## Executive Summary

Phase 473 needs two explicit resource lifecycles, not a stronger S3-key prefix check:

1. A short-lived, single-consumption **upload intent** owned by the verified student Actor. It issues a constrained presigned POST, records the server-generated object key privately, validates the completed object, and can be consumed exactly once by an atomic association.
2. A durable, immutable **saved attachment** owned by the student. It remains available with conversation history, is charged once against 5 GB/15 GB storage quota, and can be reused through an opaque attachment ID without exposing or duplicating the stored object.

The current `files.py` route cannot enforce `_MAX_FILE_SIZE`, accepts broad `image/*`, returns raw S3 errors and object keys, and never records ownership or lifecycle state. `questions.py` accepts any `image_s3_key` and sends it directly to Rekognition. `conversations.py` accepts `attachmentIds` but ignores them. The safest migration is to make all client contracts use opaque upload/attachment IDs, keep bucket/key coordinates repository-private, and validate server-side before any OCR, document parsing, AI request, or durable association.

Practice integrity requires a structural contract split. `_build_challenge` currently emits `correctAnswer`, `explanation`, and answer-derived feedback into overview/path/lesson responses. `curriculum_service._build_exercise` omits `answerKey` conditionally but still always emits `explanation`. A field blacklist is too fragile. Define typed answer-free preview models and typed attempt-result/privileged-answer models, then make every student-facing route serialize only the preview models.

Recommended delivery order:

1. Lock attachment/error/preview/result contracts and adversarial test fixtures.
2. Add upload-intent, saved-attachment, storage-usage and association repository operations plus content validators.
3. Replace presigned PUT/key responses with constrained presigned POST and a post-upload finalize/validate endpoint.
4. Integrate durable attachments into conversation messages and question OCR with conditional transactions.
5. Split practice previews from recorded-attempt results and enforce scoped teacher/global admin answer reads.
6. Run ownership/type/lifecycle matrices, OpenAPI response assertions, cleanup tests and source-bound evidence.

## Current-State Findings

### Upload issuance is declaration-only

`src/stoa/routers/files.py`:

- allows JPEG, PNG, GIF, WebP, HEIC and PDF even though the locked photo/OCR contract is JPEG/PNG;
- accepts any declared `image/*` for an image extension;
- defines but never uses `_MAX_FILE_SIZE`;
- uses presigned PUT, whose policy does not contain `content-length-range`;
- returns both the presigned URL and raw `s3_key`;
- sets the URL lifetime from the current 300-second setting rather than the locked 30-minute intent lifetime;
- embeds raw provider exception text in an HTTP 500 response.

AWS presigned POST policies support exact fields and `content-length-range`, so they are a better first boundary than presigned PUT. They do not replace post-upload validation: the server must still `HeadObject` for authoritative length/metadata and inspect bounded bytes before marking an intent valid.

### Question OCR trusts arbitrary object coordinates

`SubmitQuestionRequest.image_s3_key` is a caller-controlled string. `_build_question_content` passes it directly to `ocr_service.extract_text_from_s3`. A foreign key therefore becomes an OCR exfiltration primitive. `_question_response` hides the key after the effect, but hiding the response does not repair the missing authorization.

The question flow also performs daily counter, ledger, OCR, question put and AI work separately. Phase 475 owns the broader counter/ledger/question convergence. Phase 473 should not absorb that entire transaction, but it must make the upload-intent consumption and durable question/attachment association atomic. A transaction can conditionally update the upload intent and write the question/association while leaving broader quota-ledger reconciliation to Phase 475.

### Conversation attachment fields are currently inert

`SendMessageRequest.attachmentIds` exists, but `send_message`, streaming, `_send_message_impl`, `ChatMessage`, and stored message items ignore it. Conversation history therefore cannot faithfully retain or render uploaded files. The durable model needs safe attachment summaries (`id`, original filename, detected media type, size, status) while object keys and extracted text remain private.

Because a saved attachment may be reused, association rows must be separate from blob ownership. Reuse creates a new logical link to the same immutable attachment and must not increment storage bytes again.

### Entitlement resolution is the correct tier source

`entitlement_service.resolve_student_entitlement` already produces the authoritative `effectivePlan`. Treat `standard` and `premium` as paid for attachment storage. Add a stable `attachmentStorageBytes` limit or an equivalent central helper: free = 5 GiB, standard/premium = 15 GiB. Do not infer paid access from request fields or add billing provider calls to upload routes.

### Practice previews leak through two builders

`practice._build_challenge` always includes:

- `correctAnswer`;
- `explanation`;
- `correctFeedback` and `incorrectFeedback`, which may reveal answer-derived content.

Overview, roadmap/path and lesson routes all call this builder before a recorded attempt. `curriculum_service._build_exercise` conditionally includes `answerKey` but always includes `explanation`. Both families need explicit preview projections.

`practice_repo.record_attempt` currently writes only wrong attempts, omits the student's answer, and returns no durable receipt. The answer route computes the result before the write and can return feedback even if the write contract is incomplete. Phase 473 needs a minimal immutable attempt receipt written for every answer and must return answer-bearing result content only after that write succeeds. Phase 475 can later make attempt analytics/usage writes fully transactional and idempotent across all side effects.

### Teacher answer scope lacks a curriculum-specific resolver

`curriculum_service.can_view_answer_keys` currently returns true for any teacher or admin role. This is broader than D-21. Phase 472 already has current teacher assignment facts and a central policy. Reuse that spine:

- admin role may have the narrow automatic `curriculum_answer_read` decision for all curriculum answer resources, per the locked Phase 473 decision;
- teacher reads require an active assignment whose scope covers the requested course/class/subject/grade/lesson context;
- student/parent/unassigned teacher requests use the answer-free contract or a safe denial;
- answer read access never grants curriculum mutation.

Where today's assignment rows do not carry curriculum scope, introduce a bounded curriculum-scope projection on the existing assignment record rather than inventing a second role or trusting query parameters. Phase 475 still owns assignment-write transactional consistency.

## Recommended Architecture

### 1. Separate upload intent, saved attachment, and association records

Recommended single-table shapes:

```text
PK=UPLOAD#{upload_id}       SK=META
  owner_id, object_key(private), original_filename, declared_type,
  expected_kind, max_bytes, status, created_at, expires_at,
  detected_type, content_length, etag/version, validation_failure

PK=ATTACHMENT#{attachment_id} SK=META
  owner_id, object_key(private), original_filename, detected_type,
  content_length, image_width/image_height?, status=active|deleted,
  created_at, source_upload_id

PK=STORAGE#{student_id}     SK=USAGE
  used_bytes, limit_bytes, version, updated_at

PK={RESOURCE}#{resource_id} SK=ATTACHMENT#{attachment_id}
  attachment_id, owner_id, created_at, association_type
```

Never expose `object_key`. The key can use a server-owned prefix such as `uploads/{owner_fingerprint}/{upload_id}` for defense in depth, but authorization comes from the upload/attachment record loaded by opaque ID.

Use statuses with closed transitions, for example:

```text
pending_upload -> validating -> validated -> consumed
pending_upload/validating -> invalid
pending_upload/validated -> expired
```

A failed dependency validation may return to `pending_upload` within the original expiry. A file/type/size/integrity failure becomes terminal `invalid`.

### 2. Use constrained presigned POST plus authoritative finalize

`POST /files/presign` should accept a strict file purpose and declared metadata, create the intent first, and return:

```text
uploadId, url, fields, expiresAt, maxBytes, acceptedTypes
```

Do not return bucket/key. Presigned POST conditions should include exact key, exact `Content-Type`, private encryption/storage fields as applicable, and `content-length-range` (10 MiB image, 50 MiB supported document). The intent and POST should expire after 30 minutes.

`POST /files/{upload_id}/finalize` should:

1. load the intent by opaque ID;
2. require owner Actor, nonterminal status, and unexpired time;
3. call `HeadObject` for existence, content length, declared type, ETag/version and metadata;
4. read a bounded object stream and validate detected type/integrity;
5. mark `validated` only with a conditional status/version update;
6. map missing/foreign alike to redacted not-found, owner expiry to `upload_expired`, and provider outages to a retryable safe code.

### 3. Validate bytes, containers, and dimensions, not filenames alone

Recommended validation matrix:

| Extension | Declared MIME | Required content evidence | Limit |
|-----------|---------------|---------------------------|-------|
| jpg/jpeg | image/jpeg | JPEG signature, Pillow identify/verify, width/height <= 4096 | 10 MiB |
| png | image/png | PNG signature, Pillow identify/verify, width/height <= 4096 | 10 MiB |
| pdf | application/pdf | `%PDF-` header, bounded full-file structure check | 50 MiB |
| docx | OOXML Word MIME | ZIP, `[Content_Types].xml`, `word/` members | 50 MiB |
| pptx | OOXML Presentation MIME | ZIP, `[Content_Types].xml`, `ppt/` members | 50 MiB |
| xlsx | OOXML Spreadsheet MIME | ZIP, `[Content_Types].xml`, `xl/` members | 50 MiB |
| txt | text/plain | strict UTF-8, reject NUL/control-heavy binary | 50 MiB |
| md | text/markdown or text/plain | strict UTF-8, reject NUL/control-heavy binary | 50 MiB |

For OOXML, reject path traversal names, excessive member counts, encrypted archives, suspicious compression ratios and uncompressed totals above a bounded ceiling. For images, convert Pillow decompression-bomb warnings to errors and enforce the explicit 4096-pixel edge even though the pixel-count guard is broader. Add Pillow as a locked runtime dependency and regenerate `uv.lock`/`requirements.txt` through the existing `uv` workflow.

### 4. Make quota charging conditional and deduplicated

Charge bytes only when a validated upload first becomes a durable saved attachment. Use an atomic update condition such as `used_bytes + :size <= :limit` in the same transaction that creates the attachment/association and consumes the intent. A historical saved attachment reuse creates only an association and does not update `STORAGE#.../USAGE`.

At quota exhaustion return a stable `storage_quota_exceeded` client action. Existing attachments remain readable/downloadable/deletable. Deletion should decrement storage only when the last durable reference or the attachment itself is actually deleted; automatic deletion of history is forbidden.

### 5. Integrate through repository/service boundaries

Recommended modules:

- `src/stoa/models/attachment.py` — typed request/response/status contracts.
- `src/stoa/security/attachment_errors.py` — stable codes, safe messages and client actions.
- `src/stoa/db/repositories/attachment_repo.py` — load, condition, transaction, query and usage operations.
- `src/stoa/services/file_validation_service.py` — bounded type/integrity/container/image validation.
- `src/stoa/services/attachment_service.py` — intent issuance/finalization, owner checks, quota, associations and reuse.
- `src/stoa/jobs/upload_cleanup.py` — bounded expired/invalid upload cleanup handler with idempotent deletion.

Routers should orchestrate typed services, not implement S3/Dynamo state transitions inline.

### 6. Question OCR consumes only a validated owner resource

Replace `image_s3_key` with mutually exclusive opaque `uploadId`/`attachmentId` inputs (or one typed attachment reference). For a fresh upload, transactionally:

- condition owner/status/expiry;
- update the upload to `consumed`;
- create the durable attachment and quota usage if it does not exist;
- create the question attachment link and question item.

For saved attachment reuse, condition owner/active/image-type and create only the question link/question item. OCR receives a server-loaded private object coordinate after authorization. The question response exposes `attachment` summary/`hasImage`, never key or raw OCR text.

Idempotent replay must bind the same request key to the same attachment and question. A different attachment under the same idempotency key is a safe 409. Phase 475 remains responsible for combining daily quota/ledger with this boundary.

### 7. Conversation history uses durable attachment summaries

Both regular and streaming message paths must consume/reuse attachments before invoking AI and store attachment IDs on the student message. `ChatMessage` should expose a list of safe summaries. The assistant can receive extracted content through an internal bounded projection, but message/history API responses and logs must never expose extraction text, provider payload or object keys.

Document extraction needs explicit resource limits. Parse only the supported formats, cap extracted text/pages/slides/cells, reject active content/macros/encrypted containers, and treat parsing failure as a file action rather than silently sending opaque bytes to the model.

### 8. Practice preview and result contracts are allowlists

Create typed projections such as:

```text
PracticeChallengePreview
  id, lessonId, prompt, type, choices, safeHint?

PracticeAttemptResult
  attemptId, challengeId, correct, standardAnswer,
  explanation, feedback, nextChallengeId, attemptsRemaining

PrivilegedPracticeAnswer
  challengeId, standardAnswer, explanation, feedback fields
```

Preview builders must not accept an `include_answers` boolean. Student overview/path/lesson/catalog endpoints always return preview models. The answer submission route must write an immutable attempt first; only then may it build `PracticeAttemptResult`. A dedicated attempt result read must load the attempt owned by the Actor before returning answer-bearing data.

Privileged answer routes use explicit answer-bearing response models and central authorization. Teacher scope must be assignment-bound; admin scope is global for this narrow read contract. Parents never inherit answer access.

## Stable Error Contract

Recommended API codes/actions:

| Code | HTTP | Client action | External meaning |
|------|------|---------------|------------------|
| `upload_not_found` | 404 | select/upload again | missing and foreign are indistinguishable |
| `upload_expired` | 409 | select/upload again | owner-visible transient expiry |
| `upload_too_large` | 422 | choose a smaller file | authoritative size exceeded |
| `upload_type_not_supported` | 422 | choose a supported file | extension/declared type not supported |
| `upload_content_mismatch` | 422 | reselect file | declared/type/magic/container mismatch |
| `upload_invalid` | 422 | reselect file | corrupt, encrypted, bomb-like or unsafe container |
| `storage_quota_exceeded` | 409 | delete attachments or upgrade | history remains accessible |
| `upload_service_unavailable` | 503 | retry later | bounded retry; no provider detail |

All error bodies retain the established `code`, safe `message`, `correlationId` shape. Only retry-safe/idempotent operations may be retried automatically.

## Threat Model

Assets: student files, extracted text, answer keys/explanations, storage quota, conversation/question ownership, attempt receipts, and provider coordinates.

Primary threats:

- foreign upload or saved attachment IDs used for OCR/document extraction;
- raw object key guessing or leakage;
- declared MIME/extension bypass, polyglot content, image/ZIP decompression bomb;
- oversized direct upload or quota race;
- upload replay into a second resource;
- failure after object upload but before state transition;
- answer fields leaking through one legacy preview route, nested explanation or feedback;
- answer returned after request receipt but before durable attempt write;
- unassigned teacher using `includeAnswers=true` or a known challenge ID;
- raw S3/provider/file/OCR content entering responses, logs or evidence.

Mitigations: opaque IDs, Actor-owned repository records, exact presigned POST conditions, authoritative post-upload checks, bounded parsers, conditional transactions, terminal invalid/expired states, explicit preview/result models, central scoped authorization, safe structured errors, redaction canaries and negative matrices.

## Validation Architecture

### Test layers

1. **Pure validators:** byte signatures, MIME matrix, image dimensions/decompression bomb, OOXML member limits/traversal/compression, UTF-8 text checks.
2. **Repository state machines:** owner/status/expiry conditions, transaction cancellation mapping, quota races, idempotent association/reuse and cleanup.
3. **Route contracts:** presign/finalize, missing-vs-foreign equivalence, object-key/OCR redaction, question and conversation attachment summaries.
4. **Practice snapshots:** every student preview/overview/path/lesson/catalog response recursively lacks answer-bearing fields; attempt result contains them only after a successful write.
5. **Role/resource matrix:** owner student, foreign student, parent, assigned teacher, unassigned/stale teacher and admin for preview/result/privileged answer routes.
6. **OpenAPI/generated inventory:** preview and result schemas are distinct and sensitive identifiers remain governed by executable authorization metadata.

### Focused commands

```text
.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py
.venv/bin/python -m pytest -q tests/test_questions.py tests/test_conversations.py
.venv/bin/python -m pytest -q tests/test_practice.py tests/test_practice_privacy.py tests/test_curriculum_rollout.py
.venv/bin/python -m pytest -q tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py
```

The final phase gate should run all Phase 473 files together, then run the established Phase 472 authorization tests that protect Actor/resource semantics. The known 23 Phase 474 strict production-configuration fixture failures must remain classified separately and must not be weakened in this phase.

## Planning Decomposition

Recommended seven-plan structure:

1. Security contracts, models and Wave 0 adversarial fixtures.
2. Upload intent/presigned POST/post-upload validation/quota/lifecycle core.
3. Durable conversation attachment history, reuse and internal extraction boundary.
4. Atomic question attachment consumption and OCR migration.
5. Answer-free practice/curriculum preview schemas and durable attempt-result contract.
6. Assigned-teacher/global-admin privileged answer reads and authorization matrix.
7. Cleanup job, combined regression, OpenAPI/evidence and phase exit gate.

## Pitfalls to Avoid

- Checking `uploads/{user_id}/` prefixes instead of loading an owner record.
- Returning a raw key alongside an opaque ID “for compatibility.”
- Relying on presigned POST conditions without post-upload validation.
- Counting logical associations as additional storage bytes.
- Deleting the oldest attachment automatically at quota limit.
- Adding a boolean `includeAnswers` to a student response model.
- Treating a failed attempt write as sufficient to unlock an answer.
- Letting teacher role alone bypass assignment scope.
- Expanding Phase 473 into Phase 475's full quota/ledger transaction rewrite or Phase 476 billing recovery.

## Primary Sources

- [Amazon S3 presigned POST generation](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/generate_presigned_post.html) — POST fields and conditions, including `content-length-range`.
- [Amazon S3 POST policy conditions](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/sigv4-HTTPPOSTConstructPolicy.html) — exact matches, key constraints and size ranges.
- [Amazon S3 HeadObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html) — authoritative object metadata without returning the body.
- [Amazon S3 GetObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html) — bounded Range reads and response metadata.
- [Amazon DynamoDB TransactWriteItems](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html) — all-or-nothing conditional updates/puts and transaction constraints.
- [Pillow Image documentation](https://pillow.readthedocs.io/en/stable/reference/Image.html) — restricted format opening and decompression-bomb protections.

## RESEARCH COMPLETE

Phase 473 can be planned without unresolved technical blockers. The principal scope boundary is explicit: implement upload/attachment atomicity and minimal durable attempt receipts here; leave broader usage-ledger/question convergence to Phase 475, paid entitlement recovery to Phase 476, mobile UI completion to Phase 478, and deployment/IaC scheduling evidence to Phases 479–480.
