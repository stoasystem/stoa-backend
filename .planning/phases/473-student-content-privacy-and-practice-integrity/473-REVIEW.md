---
phase: 473-student-content-privacy-and-practice-integrity
reviewed: 2026-07-17T09:20:40Z
depth: standard
files_reviewed: 36
files_reviewed_list:
  - docs/security/phase-473-evidence-manifest.json
  - docs/security/phase-473-evidence.md
  - docs/security/route-authorization-inventory.json
  - src/stoa/config.py
  - src/stoa/db/repositories/attachment_repo.py
  - src/stoa/db/repositories/practice_repo.py
  - src/stoa/db/repositories/question_repo.py
  - src/stoa/jobs/__init__.py
  - src/stoa/jobs/upload_cleanup.py
  - src/stoa/models/attachment.py
  - src/stoa/models/practice.py
  - src/stoa/models/question.py
  - src/stoa/routers/conversations.py
  - src/stoa/routers/files.py
  - src/stoa/routers/practice.py
  - src/stoa/routers/questions.py
  - src/stoa/security/attachment_errors.py
  - src/stoa/security/authorization.py
  - src/stoa/security/private_telemetry.py
  - src/stoa/security/route_authorization.py
  - src/stoa/security/route_inventory.py
  - src/stoa/services/ai_service.py
  - src/stoa/services/attachment_service.py
  - src/stoa/services/curriculum_service.py
  - src/stoa/services/document_extraction_service.py
  - src/stoa/services/entitlement_service.py
  - src/stoa/services/file_validation_service.py
  - src/stoa/services/ocr_service.py
  - src/stoa/services/practice_projection_service.py
  - tests/test_attachment_security.py
  - tests/test_conversations.py
  - tests/test_files.py
  - tests/test_practice_privacy.py
  - tests/test_questions.py
  - tests/test_route_authorization_inventory.py
  - tests/test_student_authorization_matrix.py
findings:
  critical: 4
  warning: 2
  info: 0
  total: 6
status: issues_found
---

# Phase 473: Code Review Report

**Reviewed:** 2026-07-17T09:20:40Z
**Depth:** standard
**Files Reviewed:** 36
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

Plans 473-15 and 473-16 close the exact malformed upload-level coordinates, candidate-local cleanup isolation, and malformed attachment-body ownership paths they changed. The review nevertheless found four ship-blocking correctness/privacy gaps and two robustness defects in adjacent phase paths that the source-bound evidence does not exercise.

The most direct regression is another provider-success transition: multipart part completion still accepts an absent, non-string, empty, or whitespace-only ETag, persists the part as completed, and removes its retry lease. Conversation completion transport also remains incorrectly normalized at the real repository boundary: `complete_message_command` swallows the typed retryable outcome before the router adapter can produce the promised structured 503 or perform an explicit ambiguity reread. A committed lost-response resume may then run AI against a silently partial DynamoDB `BatchGetItem`, and attachment deletion/account purge stops permanently at the first GSI page. These defects invalidate the evidence claims that every coordinate, completion transport, committed replay, and D-10 deletion path passed.

Review probes confirmed that `complete_upload_part(..., provider_etag="")` returns `True` and persists the empty ETag, and that `complete_message_command` returns `False` when `transact` raises `RETRYABLE_DEPENDENCY`. The selected existing remediation tests still pass because they do not traverse either real boundary: 18 selected tests passed. Real S3 multipart/version behavior, deployed cleanup scheduling/IaC, and production log capture remain honestly **NOT RUN** and owned by Phases 479/480.

## Critical Issues

### CR-01: Multipart part success accepts an unusable ETag and permanently closes the retry fence

**Classification:** BLOCKER
**Files:** `src/stoa/services/attachment_service.py:539-559,575-619,682-724`; `src/stoa/db/repositories/attachment_repo.py:410-440`

**Issue:** The strict provider-coordinate helper added by Plan 473-15 is not applied to `UploadPart` success. The service converts `result.get("ETag")` to `""` and passes it to `complete_upload_part`; stale reconciliation does the same for `ListParts`. The repository accepts that empty value, marks the part `completed`, and removes `lease_expires_at`. `complete_upload` trusts every completed ledger row and sends the empty ETag to `CompleteMultipartUpload`. The provider rejects that request, while subsequent identical chunk retries short-circuit on `status == "completed"` and can never repair the ledger. The upload remains unusable until expiry even if the part bytes were successfully stored.

This is the same malformed-success/idempotency class Plan 473-15 claimed to close, just one transition earlier. The direct repository probe returned `True` and captured `:etag == ""`; the coordinate test matrix only covers upload issuance, staging completion, promotion, and cleanup writes.

**Fix:** Validate the `UploadPart`/`ListParts` ETag with the non-coercing required-coordinate helper before calling `complete_upload_part`, and add the same guard inside `complete_upload_part` before it removes the lease. On malformed success, leave the part in `uploading` so an expired takeover can reconcile the exact provider part. Add the full absent/non-string/blank matrix for both `upload_part` and `list_parts`, plus a restart test proving the part is adopted once and assembly succeeds without another upload.

### CR-02: Real completion transport failures are swallowed before structured retry or lost-response reconciliation

**Classification:** BLOCKER
**Files:** `src/stoa/db/repositories/attachment_repo.py:1141-1191,1905-1936`; `src/stoa/routers/conversations.py:908-922`; `tests/test_conversations.py:1123-1139`; `docs/security/phase-473-evidence.md:31,42,64`

**Issue:** `transact` correctly converts a generic completion SDK/transport exception into `AttachmentTransactionError(RETRYABLE_DEPENDENCY)`, but `complete_message_command` catches every `AttachmentTransactionError` and returns `False`. The router therefore never sees the typed failure through `_conversation_repository_call`; it merely polls the command and usually returns `message_in_progress` after one second. A known uncommitted outage is not the promised structured 503, while an ambiguous commit is not explicitly classified and reread at the repository boundary.

The completion-stage test bypasses this behavior by monkeypatching `complete_message_command` itself to raise a raw exception. The review probe exercised the actual function with a typed retryable transaction and observed `False`. Consequently the evidence statement that completion transport and ambiguous reread paths all passed is not supported by the tested call chain.

**Fix:** Preserve a typed completion result. On `RETRYABLE_DEPENDENCY`, consistently reread the same command: return the stored completed result if the transaction committed, return structured `upload_service_unavailable` if it did not or cannot be read, and preserve conflict/concealment semantics for conditional outcomes. Do not collapse dependency and conditional ambiguity into one boolean. Test endpoint/timeout/generic SDK errors by injecting them below `transact_write_items`, including a commit-then-raise fake, for both regular and SSE routes.

### CR-03: Lost-response replay can finalize a different AI answer from a partial attachment read

**Classification:** BLOCKER
**Files:** `src/stoa/db/repositories/attachment_repo.py:901-936`; `src/stoa/routers/conversations.py:662-689,833-856`

**Issue:** `get_attachments` performs one DynamoDB `BatchGetItem` and ignores `UnprocessedKeys`. It also does not require the returned IDs to equal the requested IDs. During `message_committed`/`ai_running` recovery, the router silently constructs `prepared` from whatever subset arrived, emits summaries for that subset, and continues extraction and AI generation. Normal DynamoDB throttling can therefore make a committed message with up to eight attachments resume using only some or none of its immutable content. The final stored assistant result can differ from the original request while the same idempotency key reports successful one-effect convergence.

The committed-lost-response test replaces `get_attachments` with a complete in-memory dictionary, so it cannot detect this provider-supported partial-success shape.

**Fix:** Retry `UnprocessedKeys` with a small bounded policy and consistent redacted dependency handling. Before AI work, require every stored attachment ID to resolve to the expected active owner-bound immutable record; if the complete set cannot be loaded, raise `upload_service_unavailable` without claiming/rerunning the AI lease. Add one- and multi-round `UnprocessedKeys` tests, plus a permanently missing item case, and assert zero extraction/AI/completion effects until the exact committed set is available.

### CR-04: Conversation deletion and account purge leave private attachments beyond the first DynamoDB page

**Classification:** BLOCKER
**Files:** `src/stoa/db/repositories/attachment_repo.py:1473-1484`; `src/stoa/services/attachment_service.py:1571-1634,1637-1676`; `docs/security/phase-473-evidence.md:58`

**Issue:** `list_owner_attachment_items` issues one GSI query and discards `LastEvaluatedKey`. Both conversation deletion and account purge depend on that result as if it were exhaustive. Once an owner has more than one DynamoDB page, associations or attachment metadata on later pages are never released. Worse, an association and its attachment metadata can land on different pages; the first-page association is skipped because its metadata is absent, and repeated calls query the same first page, so the private object can remain indefinitely after conversation deletion or account closure.

This is a privacy-retention correctness failure under D-10, not a query optimization. The cited evidence test uses a small single-page fake and cannot establish complete deletion.

**Fix:** Make the owner-item repository API exhaustively paginate, or expose a bounded continuation and persist deletion progress until every page is processed. Ensure association/metadata joins work across page boundaries and that retries resume after partial provider/database failure. Add multi-page tests with the association and metadata split across pages, and verify account purge/conversation deletion removes all logical references and exactly the last physical version.

## Warnings

### WR-01: Deterministic attachment errors are masked as an in-progress command after quota was charged

**Classification:** WARNING
**Files:** `src/stoa/routers/conversations.py:706-776`; `src/stoa/services/attachment_service.py:1455-1478`

**Issue:** After the command/quota claim succeeds, any `AttachmentDecisionError` from binding is caught and followed by a command reread. The command necessarily exists with the same fingerprint even when the bind transaction definitely failed and its status is still `claimed`, so the code always enters `_wait_for_message_command` and eventually reports `message_in_progress`. Stable outcomes such as `storage_quota_exceeded` or a concealed upload/attachment conflict are lost, the daily message quota remains charged, and the claimed command can repeat the same deterministic failure until its TTL expires.

**Fix:** Reread only to resolve an ambiguous dependency/lost-response result. If the command advanced to `message_committed`, `ai_running`, or `completed`, converge normally; if it remains `claimed`, propagate the original deterministic error (or the structured dependency outage) and apply the documented quota-release/consumption policy. Add command-level tests for quota and concealed-resource transaction outcomes, not only service-level transaction classification.

### WR-02: External OOXML relationships bypass the active-content guard

**Classification:** WARNING
**File:** `src/stoa/services/document_extraction_service.py:19-27,180-197`

**Issue:** Archive names are lowercased before comparison, but `_ACTIVE_MEMBER_PARTS` contains mixed-case `externalLinks/`, so `xl/externalLinks/...` never matches. The relationship check is also a raw search for exactly `targetmode="external"`; valid XML using single quotes or whitespace around `=` bypasses it. The parser currently reads only selected members, which limits immediate exploitation, but documents that violate the explicit no-active/external-content contract are accepted and sent into extraction rather than rejected as `active_content`.

**Fix:** Store all member markers in lowercase and parse `.rels` XML, rejecting any `Relationship` whose `TargetMode` attribute equals `External` case-insensitively regardless of quoting or whitespace. Add XLSX external-link members and single-quoted/whitespace relationship fixtures.

---

_Reviewed: 2026-07-17T09:20:40Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
