---
phase: 473-student-content-privacy-and-practice-integrity
reviewed: 2026-07-16T21:32:58Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/stoa/db/repositories/attachment_repo.py
  - src/stoa/jobs/upload_cleanup.py
  - src/stoa/routers/conversations.py
  - src/stoa/routers/files.py
  - src/stoa/security/attachment_errors.py
  - src/stoa/services/attachment_service.py
  - tests/test_attachment_security.py
  - tests/test_conversations.py
  - tests/test_files.py
findings:
  critical: 1
  warning: 3
  info: 0
  total: 4
status: issues_found
---

# Phase 473: Code Review Report

**Reviewed:** 2026-07-16T21:32:58Z
**Depth:** standard, with cross-file lifecycle, crash-consistency, authorization/concealment, structured-error, resource-lifetime, and evidence-binding tracing
**Files Reviewed:** 9
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

Plans 473-12 and 473-13 materially repair the previously proven failures. Normal well-formed provider responses now retain pre-mutation coordinates, stale workers are fenced, cleanup deletes recorded staging and immutable versions before completion, command-derived attachment IDs survive into durable keys, file-gateway dependency failures are redacted, and readable provider bodies close on the exercised exits. The 1,344-test observation is consistent with those improvements but does not cover the malformed-success and failure-isolation paths below.

One ship-blocking crash-consistency path remains: successful provider mutations whose response is a mapping but contains an empty required coordinate can be persisted as complete while the recovery fence is removed. This can recreate CR-007's false `cleanup_complete` outcome. Three additional robustness gaps remain in scheduled cleanup isolation, literal body ownership, and conversation replay dependency normalization. The source-bound evidence and validation therefore overstate CR-007, WR-007, WR-008, D-09, D-16, D-17, and V9PRIV-02 until these paths are fixed and the candidate is re-observed.

## Prior Finding Re-adjudication

| Prior finding | Status | Fresh evidence |
| --- | --- | --- |
| CR-001 replaceable validated bytes | Closed | Validation reads an exact staging `VersionId`, promotes the same bounded spool, and durable consumers verify the recorded immutable version/checksum/length. |
| WR-001 public storage coordinates | Closed | `files.py` and attachment response models remain opaque; no bucket, key, multipart ID, ETag, or VersionId is projected. |
| WR-002 private content/provider logs | Closed for reviewed paths | Reviewed upload/replay paths use stable categories and allowlisted private telemetry rather than payload or provider diagnostics. |
| WR-003 transaction semantics | Closed for `ClientError` cancellation responses | Ordered semantic operation kinds classify quota, concealed-resource, and retryable outcomes without provider messages. WR-011 covers transport failures outside this classifier. |
| WR-004 issuance dependency error | Closed for exception and missing-key responses, incomplete for empty success coordinates | Issuance failures return the stable outage category and retain the unique staging key, but CR-009 shows that an empty `UploadId` is accepted as success. |
| WR-005 conversation replay contract | Closed for modeled command races and `AttachmentTransactionError` outcomes | Deterministic command/message/attachment IDs and atomic command transitions converge the tested regular/SSE races. WR-011 covers unclassified repository transport failures. |
| CR-007 unbound byte retention | Closed for recorded and recoverable exact versions, not fully closed | Recorded staging/immutable tuples and stale operation states are cleaned exactly. CR-009 shows that empty success coordinates remove the operation marker and can again leave an unaddressable provider target. |
| WR-006 deterministic attachment IDs | Closed | The immutable input and bound output lists are distinct; cardinality and exact durable key tests cover fresh/reused ordering and retry. |
| WR-007 structured gateway dependencies | Closed for the file routes' tested stages, incomplete across connected replay/cleanup consumers | `_gateway_call` redacts the injected file-route stages. WR-009 and WR-011 identify remaining dependency exits outside that boundary. |
| WR-008 provider body closure | Closed for every readable-body exit exercised by tests, incomplete for malformed bodies | Success, size/checksum/parser/read failures close once. WR-010 identifies a closable body rejected before the `finally` owner is established. |

## Critical Issues

### CR-009: Empty provider success coordinates erase the only recovery fence

**Classification:** BLOCKER
**Files:** `src/stoa/services/attachment_service.py:357-385,691-739`; `src/stoa/db/repositories/attachment_repo.py:256-269,493-510`; `src/stoa/services/attachment_service.py:147-240`; `tests/test_files.py:249-290`

**Issue:** `_provider_mapping` validates only that a provider response is a dictionary. Issuance then converts `created["UploadId"]` to a string without requiring it to be non-empty, and completion passes `str(result.get("VersionId") or "")` and an equally unchecked ETag into `recover_staging_completion`. Both repository transitions accept empty coordinates and call `_fenced_transition(..., remove_operation=True)`. A direct repository probe confirms both transitions return success and remove `operation_kind`, `operation_fence`, lease, and takeover state while persisting an empty target.

If multipart creation actually succeeded but returned an empty ID, the row becomes `pending_upload` without an addressable multipart or issuance-recovery marker. If multipart completion succeeded but returned no VersionId (for example, versioning is disabled/misconfigured or a provider wrapper emits a partial success mapping), the row becomes `validating` with an empty staging version and without the assembly-recovery marker. Validation then rejects it, but expired cleanup sees neither a recorded staging version nor `operation_kind == "staging_assembly"`; it marks `cleanup_staging_deleted` and can reach `cleanup_complete` without deleting or recovering the completed staging object. That is the same retention/truth violation as CR-007 and blocks D-09/V9PRIV-02.

The malformed-provider matrix only returns a non-dictionary list. The crash tests always return non-empty provider coordinates, so neither test family exercises a partial success mapping.

**Fix:** Validate every required provider coordinate before any success transition: require a non-empty multipart `UploadId` before `record_staging_multipart`, and a non-empty staging `VersionId` (plus the chosen required ETag invariant) before `recover_staging_completion`. On an empty issuance coordinate, retain/transition the pre-persisted `staging_issuance` operation so exact-key cleanup enumerates unfinished multiparts. On an empty completion coordinate, leave the row fenced in `assembling` so restart/cleanup recovers from the exact unique key. Add repository defense-in-depth that refuses empty multipart/version coordinates before `remove_operation=True`. Test `{}`, `{"UploadId": ""}`, `{"VersionId": "", "ETag": "..."}`, and missing/empty ETag according to the invariant; assert no operation marker is discarded and later cleanup cannot report completion until the actual exact provider target is absent.

## Warnings

### WR-009: One stale-recovery lookup failure aborts the entire scheduled cleanup batch

**Classification:** WARNING
**Files:** `src/stoa/services/attachment_service.py:109-240,282-303`; `src/stoa/jobs/upload_cleanup.py:57-79`

**Issue:** Provider errors during multipart abort/delete are converted to the per-item `"retryable"` outcome, but `_matching_exact_version` calls `_provider_mapping`, which raises `AttachmentDecisionError` on `ListObjectVersions`/`HeadObject` failures. `cleanup_upload_intent` catches only `AttachmentRepositoryConflict`, and `cleanup_expired_uploads` has no per-candidate exception boundary. A transient lookup failure for one stale `assembling` or `promoting` row therefore terminates the Lambda invocation, prevents remaining candidates from being processed, and produces no bounded retryable summary. Generic repository/table failures from candidate listing or per-item calls have the same unclassified exit when they are not already wrapped as `AttachmentRepositoryConflict`.

**Fix:** Normalize expected provider/repository dependency failures inside `cleanup_upload_intent` to `"retryable"`, and place a final coordinate-free per-candidate isolation boundary in the job so one corrupt/transient row cannot stop the bounded batch. Do not serialize exception text or coordinates. Add multi-candidate tests where the first stale recovery lookup fails and later candidates still converge while the first remains `cleanup_pending` and is counted retryable.

### WR-010: A closable malformed provider body is rejected before the `finally` owner exists

**Classification:** WARNING
**File:** `src/stoa/services/attachment_service.py:937-949,1479-1491`

**Issue:** Both exact-version read paths bind `body`, test whether `read` is callable, and only then enter the `try/finally` that calls `_close_provider_body`. A provider/wrapper response containing a closable body with a missing or non-callable `read` is rejected before `finally`, so the owned HTTP/resource object is never closed. This contradicts the Plan 13 key link that every returned provider body is closed and leaves WR-008 incomplete at the malformed-response boundary.

**Fix:** Establish `try/finally: _close_provider_body(body)` immediately after retrieving any non-`None` body, and perform the readable-shape validation inside that protected region. Add closable/non-readable and read-property-failure spies for validation and extraction, asserting exactly one close and the same stable error/category.

### WR-011: Conversation attachment replay still exposes raw repository transport failures

**Classification:** WARNING
**Files:** `src/stoa/routers/conversations.py:147-163,543-566,698-716`; `src/stoa/services/attachment_service.py:1428-1443`; `src/stoa/db/repositories/attachment_repo.py:1875-1900`

**Issue:** The file routes now receive normalized `AttachmentDecisionError`, but the connected conversation replay path does not consistently use that boundary. The Stage-A dependency and polling call `get_message_command` directly outside the route's `try/except`. More importantly, `transact` catches only `ClientError`; endpoint/transport failures and other SDK exceptions propagate raw through `bind_message_attachments`, whose handler catches only `AttachmentTransactionError`. The route catches only `AttachmentDecisionError`. A repository outage or unknown transaction-response failure can therefore become an unstructured 500 rather than the stable retryable code, and the immediate race/replay lookup is skipped. The lost-response unit test injects an already-classified `AttachmentTransactionError`, so it cannot reveal this actual transport path.

**Fix:** Convert non-cancellation repository transport failures to the closed retryable dependency outcome without consuming provider diagnostics, then let the command executor perform its same-fingerprint state reread before returning the stable outage/in-progress contract. Wrap Stage-A and poll repository reads similarly. Add route-level generic transport injections before command lookup, during the message transaction, and during replay polling; assert a stable code/correlation response, no payload/provider text, and successful convergence when the transaction actually committed despite the lost response.

---

_Reviewed: 2026-07-16T21:32:58Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
