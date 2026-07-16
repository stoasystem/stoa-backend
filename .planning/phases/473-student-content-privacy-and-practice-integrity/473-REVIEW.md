---
phase: 473-student-content-privacy-and-practice-integrity
reviewed: 2026-07-16T18:23:11Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - docs/security/route-authorization-inventory.json
  - src/stoa/db/repositories/attachment_repo.py
  - src/stoa/models/attachment.py
  - src/stoa/routers/conversations.py
  - src/stoa/routers/files.py
  - src/stoa/routers/questions.py
  - src/stoa/security/attachment_errors.py
  - src/stoa/security/private_telemetry.py
  - src/stoa/services/ai_service.py
  - src/stoa/services/attachment_service.py
  - src/stoa/services/document_extraction_service.py
  - src/stoa/services/file_validation_service.py
  - src/stoa/services/ocr_service.py
  - tests/test_attachment_security.py
  - tests/test_conversations.py
  - tests/test_files.py
  - tests/test_questions.py
findings:
  critical: 1
  warning: 3
  info: 0
  total: 4
status: issues_found
---

# Phase 473: Code Review Report

**Reviewed:** 2026-07-16T18:23:11Z
**Depth:** standard, with cross-file lifecycle and authorization tracing
**Files Reviewed:** 17
**Status:** issues_found

## Summary

The gap implementation closes the six findings from the earlier review at their original failure sites: uploads now use an opaque chunk gateway and exact immutable versions; private telemetry is allowlisted; transaction cancellation is classified by semantic operation; issuance failures use the stable error contract; and regular/SSE message retries share a durable command record. The recorded 1,303-test pass is consistent with those improvements.

Adversarial review nevertheless found one new ship-blocking retention/crash-consistency defect and three robustness defects. The critical issue is not exercised by the current cleanup fixtures because they model only staging coordinates, while every successfully validated upload now also owns a promoted immutable version.

## Prior Finding Re-adjudication

| Prior finding | Status | Fresh evidence |
| --- | --- | --- |
| CR-001 replaceable validated bytes | Closed at the read boundary | `attachment_service.py:518-593` validates one exact staging `VersionId`, promotes the same bounded spool, persists key/version/ETag/SHA/length, and OCR/extraction reads the stored immutable version. |
| WR-001 public storage coordinates | Closed | `attachment.py:44-84` and `files.py:61-117` expose only opaque intent/chunk/completion fields; provider URL, bucket, key, upload ID, ETag, and version are absent. |
| WR-002 private content/provider logs | Closed for reviewed paths | `private_telemetry.py:11-67` uses a closed category registry and class/size/count/correlation allowlist; AI/question/conversation paths no longer interpolate payloads or exception text. |
| WR-003 transaction semantics | Closed | `attachment_repo.py:1570-1612` classifies only ordered cancellation codes and semantic operation kinds; `attachment_service.py:971-984` maps the closed outcomes to quota, retryable dependency, or concealed-resource errors. |
| WR-004 issuance dependency error | Closed at issuance | `attachment_service.py:135-223` creates an `issuing` record, aborts/marks failure on dependency errors, and returns `upload_service_unavailable`. WR-007 below covers later gateway operations. |
| WR-005 conversation replay contract | Substantially closed, with a new robustness defect | `conversations.py:569-850` adds fingerprinted command/quota claims, replay polling, deterministic message IDs, and fenced result persistence. WR-006 identifies a parameter-shadowing bug in deterministic fresh-attachment IDs. |

## Critical Issues

### CR-007: The new gateway can permanently retain unbound student bytes after expiry or a provider/database split

**Classification:** BLOCKER
**Files:** `src/stoa/services/attachment_service.py:48-130,452-480,498-633`; `src/stoa/db/repositories/attachment_repo.py:482-555,615-632`; `tests/test_attachment_security.py:2089-2138`

**Issue:** Promotion writes a server-only immutable object at a random key and records its key/version only after the multipart completion succeeds. A process death after `complete_multipart_upload` but before `mark_validated` leaves no durable coordinates from which cleanup can find the object or multipart upload. The staging completion path has the same split: if provider completion succeeds but the process dies (or the repository transition fails), the row remains `assembling` without the returned `VersionId`.

The scheduled cleanup cannot recover either case. Candidate selection admits expired `pending_upload`, `validating`, and `validated` rows but excludes `issuing` and `assembling`. Even for a normal expired `validated` intent, `cleanup_upload_intent` loads `immutable_object_key` and `immutable_version_id` only to scan references; it deletes only `staging_object_key`/`staging_version_id`, then marks cleanup complete. The test fixture at `tests/test_attachment_security.py:2089-2098` contains staging coordinates only and therefore proves the old lifecycle, not deletion of the promoted immutable object. An unconsumed validated upload can consequently leave its private immutable bytes in storage forever while its database row says `cleanup_complete`, violating D-09 and the Phase 473 retention boundary.

**Fix:** Persist fenced staging/promotion operation coordinates before each provider mutation (including server-generated key and multipart ID), and make expired/lease-stale `issuing`, `assembling`, and promotion states cleanup-eligible. After the durable-reference scan, cleanup must abort any recorded multipart upload and delete every exact unreferenced staging and immutable `VersionId`; mark cleanup complete only after all required provider operations succeed. Add restart tests at every provider-success/repository-write boundary plus a validated-unbound fixture carrying both staging and immutable tuples, and assert exact deletion without touching a durable reference.

## Warnings

### WR-006: The deterministic attachment ID argument is overwritten before it is read

**Classification:** WARNING
**Files:** `src/stoa/services/attachment_service.py:885-931`; `src/stoa/routers/conversations.py:693-707`

**Issue:** The conversation executor correctly derives deterministic fresh-attachment IDs from the command ID and passes them to `bind_message_attachments`. The callee immediately reassigns `attachment_ids = []`, then constructs `deterministic_ids` from that empty list. Every fresh attachment therefore receives a random UUID. This defeats the intended deterministic downstream identity on recovery from an unknown transaction outcome and leaves the Plan 473-10 replay guarantee weaker than documented. Current concurrency tests verify convergence of effects but do not assert the actual attachment ID equals the command-derived value.

**Fix:** Preserve the parameter in a distinct name such as `deterministic_attachment_ids`, maintain a separate `bound_attachment_ids` output list, validate that the number of supplied deterministic IDs equals the number of fresh uploads, and add a lost-response/retry assertion for the exact durable attachment and association keys.

### WR-007: Gateway repository outages after issuance bypass the structured retry contract

**Classification:** WARNING
**Files:** `src/stoa/services/attachment_service.py:226-332,416-451,654-673`; `src/stoa/routers/files.py:76-117`

**Issue:** Issuance now translates dependency failures, but later operations do not consistently do so. `resolve_owned_upload` calls the repository without translation; chunk replay polling calls `get_upload_part` outside the guarded claim block; completion calls `list_upload_parts` and `begin_upload_assembly` outside a dependency translation boundary. The router catches only `AttachmentDecisionError`. A DynamoDB/client outage in these locations therefore produces an unstructured 500 instead of the required `upload_service_unavailable` code and bounded retry action.

**Fix:** Normalize repository/provider failures at the attachment-service boundary for every gateway stage, while preserving conditional owner/status conflicts as concealed `upload_not_found`. Add route-level failure injection for initial lookup, replay poll, part listing, assembly claim, and validation-state lookup, asserting the same redacted 503 body and correlation header.

### WR-008: Exact-version object streams are not closed

**Classification:** WARNING
**File:** `src/stoa/services/attachment_service.py:518-527,1003-1026`

**Issue:** Validation/promotion and conversation extraction read `response["Body"]` to EOF but never close the provider stream. The spool is closed, but the S3 `StreamingBody` owns the HTTP connection. Exceptions during validation, checksum mismatch, parser failure, or early bounded exit can retain connections until garbage collection, degrading upload/extraction reliability under repeated private-file requests.

**Fix:** Bind each provider body once and close it in `finally` (or a supported context manager) around the read. Add a fake body that records `close()` and assert closure for success, oversize, checksum mismatch, parser failure, and provider-read exceptions.

---

_Reviewed: 2026-07-16T18:23:11Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
