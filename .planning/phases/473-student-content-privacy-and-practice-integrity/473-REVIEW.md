---
phase: 473-student-content-privacy-and-practice-integrity
review_depth: standard
status: issues_found
files_reviewed: 34
severity:
  critical: 1
  warning: 5
  info: 0
  total: 6
reviewed_at: 2026-07-16
---

# Phase 473 Code Review

## Scope and verification

Reviewed the 34 requested implementation, contract, evidence, inventory, and test files against V9PRIV-01/02/03 and decisions D-01 through D-22. The review traced upload issuance through finalize, durable association, OCR/document reads and cleanup; practice preview through attempt persistence/result reads; and privileged answer resolution through current assignment facts.

Focused regression command:

```text
.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py tests/test_questions.py tests/test_conversations.py tests/test_practice_privacy.py tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py
```

Result: **217 passed**. The findings below are gaps in behavior and negative coverage that the passing suite does not exercise.

## Findings

### CR-001 — Validated uploads remain replaceable before OCR or document extraction

**Severity:** Critical  
**Evidence:** `src/stoa/services/attachment_service.py:151-160`, `src/stoa/services/attachment_service.py:711-721`, `src/stoa/services/attachment_service.py:483-489`, `src/stoa/services/ocr_service.py:47-52`, `tests/test_attachment_security.py:394-405`, `tests/test_attachment_security.py:921-937`

The presigned POST remains valid for the full 30-minute intent TTL. Finalize records an ETag, but later document reads call `get_object` with only bucket/key and validate only the byte length, while Rekognition receives only bucket/key. A client can therefore finalize a valid object, overwrite the same key with different same-length bytes while the original POST is still valid, and have the replacement reach extraction or OCR without passing Phase 473 validation. This defeats the claimed immutable-byte boundary and can bypass MIME/container/image validation after approval.

Bind every durable attachment to an immutable S3 version (capture `VersionId`, use it for `GetObject` and Rekognition) or copy finalized bytes to a new non-client-writable key. At minimum use an `IfMatch` ETag condition for every byte read, though version binding is stronger. Add a negative test that overwrites the object after finalize and proves OCR, extraction, association, and AI effects are all rejected.

### WR-001 — The opaque presign response exposes the private object key inside `fields`

**Severity:** Warning  
**Evidence:** `src/stoa/services/attachment_service.py:134-165`, `src/stoa/models/attachment.py:46-53`, `tests/test_attachment_security.py:312-350`, `tests/test_files.py:34-61`, `docs/security/phase-473-evidence.md:53-55`

`create_upload_intent` returns `post["fields"]`; the test double accurately places the generated object key in `fields["key"]`. The tests only assert that the literal schema name `object_key` is absent, so the private key value itself is still returned. This contradicts D-17 and the evidence claim that public responses exclude raw storage coordinates.

Either revise the architecture so the client does not receive a storage coordinate (for example, an application upload proxy or a provider abstraction that does not expose the final durable key), or explicitly reclassify the randomized transient POST key as a client upload capability and remove the stronger no-key claim. Whichever contract is chosen, test the actual generated key value as a canary rather than checking only field names.

### WR-002 — Content and provider diagnostics are still written verbatim to logs

**Severity:** Warning  
**Evidence:** `src/stoa/services/ai_service.py:70-80`, `src/stoa/services/ai_service.py:124-146`, `src/stoa/services/ai_service.py:246-267`, `src/stoa/routers/conversations.py:243-273`, `src/stoa/routers/conversations.py:616-620`, `docs/security/phase-473-evidence.md:55-66`

Prompt-injection handling logs the first 120 characters of student/OCR input, JSON parse fallback logs the first 200 characters of the model response, and conversation/title failures interpolate raw provider exceptions. OCR text is appended to question AI input, so the first path can log OCR-derived student content. These paths violate D-17 even though attachment-specific sanitization tests pass; the evidence statement that captured logs exclude content/provider payloads is too broad.

Log only event category, exception class, sizes, and correlation identifiers. Add `caplog` tests that drive the question OCR input path, malformed model output, Bedrock failure, and title failure with distinct private canaries and assert absence from all log records.

### WR-003 — Transaction cancellation mapping loses quota and dependency semantics

**Severity:** Warning  
**Evidence:** `src/stoa/db/repositories/attachment_repo.py:362-383`, `src/stoa/db/repositories/attachment_repo.py:520-535`, `src/stoa/db/repositories/attachment_repo.py:856-875`, `src/stoa/services/attachment_service.py:352-370`, `src/stoa/services/attachment_service.py:451-469`

Every DynamoDB `TransactionCanceledException` is classified as a generic conditional conflict. The service then returns `upload_not_found`. This includes an atomic storage-limit condition losing a race, which should return `storage_quota_exceeded`, and transaction throttling/conflict/dependency cancellation, which should return `upload_service_unavailable`. Atomicity is preserved, but the stable error/action contract is wrong and can tell a user to reselect a valid file instead of deleting/upgrading or retrying.

Inspect redacted cancellation reason categories by operation index (without retaining provider text) or split quota into a distinguishable precondition/transaction outcome. Add race tests for quota exhaustion and retryable transaction conflict that assert both zero effects and the correct stable public code.

### WR-004 — Presign dependency failures bypass the stable attachment error contract

**Severity:** Warning  
**Evidence:** `src/stoa/services/attachment_service.py:136-161`, `src/stoa/routers/files.py:55-67`, `src/stoa/security/attachment_errors.py:63-70`, `tests/test_files.py:65-91`

The upload intent is persisted and `generate_presigned_post` is called without translating repository, credential, or signing failures. The route catches only `AttachmentDecisionError`, so these failures bypass `upload_service_unavailable` and its bounded retry contract; a stored pending intent may also be left behind without the client ever receiving its ID. Existing route tests invoke the safe-error helper directly rather than causing the presign service dependency to fail.

Translate repository/signing failures to `upload_service_unavailable`, and either generate the policy before persisting or mark/clean up a persisted intent when issuance fails. Add route tests that fail each dependency and assert a stable redacted 503 plus no usable orphan intent.

### WR-005 — Conversation attachment submission has no idempotent replay contract

**Severity:** Warning  
**Evidence:** `src/stoa/routers/conversations.py:125-138`, `src/stoa/routers/conversations.py:542-589`, `src/stoa/services/attachment_service.py:405-424`, `src/stoa/db/repositories/attachment_repo.py:301-383`

`SendMessageRequest` has no idempotency key, and every attempt generates new message and attachment IDs. If the transaction succeeds but the response is lost, retrying a fresh-upload reference cannot return the original message; it encounters the now-consumed upload and fails. Retrying a saved attachment instead creates a second message/reference and increments its ref count. This does not satisfy D-07's replay rule and makes timeout retries non-convergent.

Require a bounded client idempotency key, persist its request fingerprint (content plus ordered attachment identities), and return the original message/result for an exact replay while rejecting a mismatched reuse. Add lost-response and concurrent-duplicate tests that assert one message, one association/ref increment, one quota charge, and one AI invocation.

## Overall assessment

The answer-free preview schemas, write-before-reveal ordering, owner-scoped attempt lookup, teacher/admin answer-read separation, conditional quota updates, and cleanup state exclusions are materially sound in the reviewed paths. Phase 473 should not be considered clean, however: CR-001 breaks the core post-upload validation invariant, and the warning findings leave documented privacy, stable-error, and retry guarantees stronger than the actual behavior and test coverage.
