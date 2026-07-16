---
phase: 473-student-content-privacy-and-practice-integrity
verified_at: 2026-07-16
status: gaps_found
score: 68
requirements:
  passed: 2
  total: 3
decisions:
  passed: 15
  total: 22
---

# Phase 473 Independent Verification

## Verdict

**Status: `gaps_found`. Score: 68/100.** The current code materially closes cross-student identifier authorization and practice-answer preview leakage, and the fresh local suites are green. It does not, however, achieve the complete Phase 473 upload-integrity and privacy contract. A finalized S3 object remains replaceable through the still-valid presigned POST, while later OCR and document reads are not bound to the validated ETag or an immutable object version. Five additional stable-error, redaction, and replay gaps identified by the phase code review also remain present in current source.

The score is the directly auditable locked-decision score: **15 of 22 D-decisions fully verified**. Artifact existence and passing tests do not raise the score where required negative coverage is absent or the call chain contradicts the claimed invariant.

## Fresh automated verification

| Verification | Fresh result | Adjudication |
| --- | ---: | --- |
| Exact Phase 473 combined command from `473-VALIDATION.md` | **230 passed in 3.54s** | Confirms current positive/fake-provider matrix, but contains no post-finalize object replacement, presign dependency-failure, transaction-reason, content-log, or conversation replay negative test. |
| Full repository suite, `.venv/bin/python -m pytest -q` | **1232 passed in 36.25s** | Reproduces the documented full-suite baseline on current HEAD `a31f25b3ca7714777312d478d7eb4a58bbb19c35`. It does not close source-proven gaps. |
| Inherited authorization regression | Prior phase evidence reported **635 passed**, and those tests are included in the fresh full suite | The task prompt mentions 389; no 389-test Phase 472 command or result exists in the supplied Phase 473 validation/evidence. The canonical Phase 473 evidence records 635, so this verification does not invent a 389-test observation. |
| Real S3 presigned POST boundary | **NOT RUN** | No approved non-production bucket/credentials. |
| Deployed cleanup schedule/IaC | **NOT RUN** | Phase 479-owned external evidence is unavailable. |
| Production/provider log capture | **NOT RUN** | Local source already proves unsafe logging paths; Phase 480 production capture remains unavailable. |

## Requirements traceability

| Requirement | Status | Actual-code finding |
| --- | --- | --- |
| **V9PRIV-01** | **Passed locally** | Public question input uses opaque owner-scoped upload/attachment references; owner/state/type reservation occurs before OCR; fresh consumption, durable attachment, association, quota charge, and question put are conditionally transacted. Missing/foreign/non-image/expired resources stop before OCR. The immutable-byte defect below weakens the content-integrity premise but does not restore the original cross-owner key primitive. |
| **V9PRIV-02** | **Failed** | Extension/MIME/magic/container/size validation exists at finalize, but the bytes later used are not immutable or ETag/version constrained. Stable dependency and transaction outcome mapping is also incomplete. Thus post-upload validation and stable-error requirements are not achieved end to end. |
| **V9PRIV-03** | **Passed locally** | Student preview/overview/path/lesson/catalog projections are typed answer-free allowlists; correct and incorrect attempts are persisted before result construction; owner attempt reads and scoped teacher/admin privileged reads are distinct and fail closed. |

The roadmap goal is therefore only partially achieved: cross-student opaque-ID ownership and early-answer prevention are sound in the inspected paths, but upload content approved at finalize is not necessarily the content later processed.

## Must-have audit

All named plan artifacts exist. The important executable links were independently traced as follows:

- **473-01:** typed attachment/practice contracts and exhaustive attachment error registry exist; preview/result schemas are structurally separate. The D-17 redaction truth fails because returned POST fields and logs still disclose prohibited values.
- **473-02:** intent and signed POST share server-generated type/size/key/expiry; finalize performs HEAD, bounded read, validation, and a conditional state transition. The key link stops at finalize: later reads do not enforce the stored ETag/version, so the validated-byte invariant is false.
- **473-03:** regular and streaming sends share attachment preparation/binding and safe history summaries; bounded extraction remains internal to the response model. The logging and replay portions of the truth fail, and extraction reads mutable key-only bytes.
- **473-04:** question requests are keyless, reservation precedes OCR, association is transactional, and question idempotency compares opaque attachment identity. OCR nevertheless receives only bucket/key and cannot prove it processed the finalized bytes.
- **473-05:** preview routes use allowlist projections; result construction follows the durable attempt receipt. Failed-write and foreign-attempt controls are present.
- **473-06:** dedicated curriculum-answer resource/purpose, current assignment facts, scoped teacher access, narrow admin read, and mutation-negative controls are present.
- **473-07:** cleanup uses a conditional non-consumable claim, bounded reference scan, retry tombstone, and safe summary. The evidence artifact exists but overclaims D-17 and immutable validation; its recorded tested SHA (`671612b...`) also differs from current HEAD, while this verification's fresh runs cover current HEAD.

## Locked decision matrix

| Decisions | Result | Evidence/adjudication |
| --- | --- | --- |
| D-01, D-02, D-03, D-05 | **Gap** | Validators enforce these at finalize, but a same-key replacement can bypass format, image-dimension, magic/container, and integrity approval before OCR/extraction. |
| D-04 | **Pass** | Signed and server-side document byte ceilings remain enforced; the known replacement attack is same-length and does not defeat the 50 MiB ceiling. |
| D-06 | **Pass** | Intent TTL is 1800 seconds. |
| D-07 | **Gap** | Question idempotency exists, but conversation message submission has no client idempotency key/fingerprint or original-result replay. |
| D-08 | **Pass** | Transient question/provider failures release within original expiry; terminal validation/object failures invalidate. |
| D-09 | **Pass** | Expired/invalid/abandoned intents become unusable before bounded retry-safe cleanup; cleanup failure does not restore usability. |
| D-10 | **Pass** | Durable conversation associations/reference counts preserve history until explicit release/purge. |
| D-11 | **Pass** | 5 GiB/15 GiB limits and transactional byte conditions block new bytes without automatic history deletion. Error taxonomy under a quota race is separately deficient under D-16. |
| D-12 | **Pass** | Active owner attachment reuse adds an association/reference and no storage bytes. |
| D-13 | **Pass** | Verified Actor is authoritative; public models reject owner/bucket/key fields. |
| D-14 | **Pass** | Missing and foreign upload/attachment lookups use the same concealed external error. |
| D-15 | **Pass** | Owner-visible expiry maps to `upload_expired` and reselect action. |
| D-16 | **Gap** | Transaction cancellations collapse to not-found; quota and retryable dependency semantics are lost. Presign repository/signing failures can bypass `upload_service_unavailable`. |
| D-17 | **Gap** | `post["fields"]` returns the generated raw key; AI/conversation logs interpolate student/model text and raw provider exceptions. Existing tests assert field names or narrow attachment logs, not actual-value absence across these paths. |
| D-18 | **Pass** | Result construction follows successful immutable attempt persistence; failed writes return answer-free failure. |
| D-19 | **Pass** | Only explicitly approved directional hints pass answer/explanation guards; full explanations are result-only. |
| D-20 | **Pass** | Preview and attempt-result contracts are distinct; student route families recursively omit forbidden answer-derived keys. |
| D-21 | **Pass** | Active assigned teachers are scoped by server-loaded curriculum coordinates; admin automatic access is narrow to answer READ; mutation remains separate. |
| D-22 | **Pass** | Anonymous, student, parent, unassigned/stale/disabled/wrong-scope teachers are denied the privileged answer contract. |

## Code-review finding adjudication

### CR-001 — Open, critical: validated S3 object replacement / TOCTOU

`finalize_upload` stores an ETag after HEAD/GET comparison (`attachment_service.py:695-723`), but `extract_message_attachment_context` later calls `get_object` with only bucket/key and checks only length (`attachment_service.py:483-489`). OCR likewise sends only bucket/name to Rekognition (`ocr_service.py:47-53`). The presigned POST remains valid for 1800 seconds and targets that same key (`attachment_service.py:151-160`). A client can replace finalized bytes with different same-length bytes and bypass validation. No current test performs this overwrite or asserts zero OCR/extraction/association/AI effects.

**Required remediation:** enable/version the object store and persist `VersionId`, then use that version for every GET/OCR operation; or copy validated bytes to a new server-only immutable key and expire/delete the writable staging key. At minimum, enforce stored ETag with `IfMatch` on every byte read and use an OCR path that verifies immutable identity. Add post-finalize replacement tests for conversation extraction and question OCR with zero-effect sentinels.

### WR-001 — Open: raw key in presigned POST fields

The service returns `post["fields"]` unchanged (`attachment_service.py:162-165`); the fake accurately places the generated key in `fields["key"]`. Tests check that schema names such as `object_key` are absent rather than checking that the generated key value is absent.

**Required remediation:** either proxy upload/provider-abstraction so the durable coordinate is not disclosed, or explicitly redefine the randomized staging key as a short-lived upload capability and remove the stronger no-key claim. In either case, never make it the durable read key and assert actual generated-key canaries across responses/logs/evidence.

### WR-002 — Open: content/provider diagnostics logged verbatim

`ai_service._sanitise_input` logs the first 120 characters (`ai_service.py:77-80`), malformed model output logs the first 200 characters (`ai_service.py:145-146`), Bedrock hint failures log raw exceptions (`ai_service.py:266-267`), and title failures do the same (`conversations.py:271-272`). OCR-derived text can enter the sanitization path.

**Required remediation:** log only category, exception class, lengths, and correlation/event IDs. Add `caplog` tests with unique OCR/student/model/provider canaries for injection, malformed JSON, Bedrock failure, and title failure.

### WR-003 — Open: transaction cancellation taxonomy

`attachment_repo.transact` classifies every `TransactionCanceledException` as the same generic conflict (`attachment_repo.py:856-875`). Service adapters then commonly return `upload_not_found`, including quota-condition races and retryable dependency cancellations.

**Required remediation:** map redacted cancellation reason categories by known operation index (without retaining messages), or separate distinguishable quota/dependency outcomes. Test quota-race => `storage_quota_exceeded`, retryable dependency/conflict => `upload_service_unavailable`, and zero mutations in both cases.

### WR-004 — Open: presign dependency failures bypass stable errors

The intent is persisted before unguarded `generate_presigned_post` (`attachment_service.py:150-161`). Repository/signing/credential failure is not translated to `AttachmentDecisionError`, and may leave a usable orphaned pending intent.

**Required remediation:** generate/validate issuance before durable persistence where feasible, or terminally invalidate/cleanup an intent on issuance failure; translate repository/signing failures to redacted 503 `upload_service_unavailable`. Add route-level failure injection for both dependencies and assert no usable orphan.

### WR-005 — Open: conversation replay is not idempotent

`SendMessageRequest` has no idempotency field (`conversations.py:125-138`), and `_send_message_impl` creates new message IDs for every request (`conversations.py:542-556`). A lost response followed by retry either fails for a consumed upload or duplicates a saved-attachment message/reference and AI call.

**Required remediation:** require a bounded client idempotency key, store a fingerprint of content plus ordered attachment identities, return the original result for exact replay, and reject mismatched reuse. Add lost-response and concurrent duplicate tests proving one message, one association/ref increment, one byte charge, and one AI invocation.

## Human verification and external debt

These are honest external limitations, not substitutes for the code fixes above:

1. **Real S3 POST and immutable-version behavior — NOT RUN.** After CR-001 remediation, exercise boundary and one-byte-over uploads in an approved non-production versioned bucket; overwrite/replay the staging capability and verify immutable reads reject or remain pinned.
2. **Deployed cleanup schedule/IaC — NOT RUN.** Verify EventBridge/Lambda ownership, bounded invocation, retry, alarms, and no deletion of active/consumed/durable objects when Phase 479 infrastructure is available.
3. **Production log-redaction capture — NOT RUN.** After WR-002 remediation, verify provider and application logs contain only approved metadata in a non-production deployed environment.

## Exit remediation order

1. Close CR-001 with version-bound or server-copied immutable bytes and adversarial replacement tests.
2. Decide and enforce the staging-key disclosure contract; remove false no-key evidence claims.
3. Redact all content/provider log paths and add cross-service canary coverage.
4. Implement transaction and presign dependency error taxonomy with orphan cleanup.
5. Add conversation request idempotency and replay/concurrency coverage.
6. Re-run the 230-test phase gate, inherited authorization gate, full suite, deterministic inventory, and evidence denylist on one source SHA; update `phase-473-evidence.md` to match the repaired code and external NOT RUN status.

## Verification conclusion

Phase 473 has strong local authorization and practice-integrity foundations, but **cannot be marked passed** while the validated object can be replaced before use and while D-16/D-17/D-07 guarantees are contradicted by current source. The correct status is `gaps_found`.
