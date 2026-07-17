---
phase: 473-student-content-privacy-and-practice-integrity
verified: 2026-07-17T09:30:53Z
status: gaps_found
score: 4/5 must-haves verified
overrides_applied: 0
requirements:
  passed: 2
  total: 3
  blocked:
    - V9PRIV-02
decision_coverage:
  honored: 18
  total: 22
  not_honored:
    - D-07
    - D-08
    - D-10
    - D-16
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "CR-009: issuance, staging-completion, and immutable-promotion coordinates are now strict nonblank strings at service and repository boundaries"
    - "WR-009: upload cleanup now isolates candidate-local failures and continues later bounded candidates"
    - "WR-010: staging validation and conversation extraction own a non-None provider Body before readable-shape inspection and close best-effort in finally"
  gaps_remaining:
    - "WR-011 remains incomplete at complete_message_command, which swallows typed retryable transaction failure into False"
  regressions: []
gaps:
  - truth: "Upload part success and restart reconciliation require a usable provider ETag before the part ledger becomes completed"
    status: failed
    reason: "UploadPart and ListParts coerce absent or malformed ETags to strings, while complete_upload_part accepts them, marks the ledger completed, and removes the retry lease."
    artifacts:
      - path: "src/stoa/services/attachment_service.py"
        issue: "put_upload_chunk and _reconcile_provider_part pass str(value or '') instead of validating a nonblank string."
      - path: "src/stoa/db/repositories/attachment_repo.py"
        issue: "complete_upload_part has no defense-in-depth coordinate guard before REMOVE lease_expires_at."
    missing:
      - "Apply the strict required-coordinate validator to UploadPart and ListParts ETags before ledger completion."
      - "Reject malformed ETags inside complete_upload_part without changing status or removing the lease."
      - "Add absent/non-string/empty/whitespace matrices and restart adoption proving assembly succeeds without a blind second upload."
  - truth: "Conversation completion dependency failures retain typed retry semantics and explicitly reconcile an ambiguous committed response"
    status: failed
    reason: "complete_message_command catches every AttachmentTransactionError and returns False, so RETRYABLE_DEPENDENCY never reaches the structured adapter and the router polls toward message_in_progress instead of an explicit committed-state reread or safe 503."
    artifacts:
      - path: "src/stoa/db/repositories/attachment_repo.py"
        issue: "complete_message_command collapses semantic transaction outcomes to bool."
      - path: "src/stoa/routers/conversations.py"
        issue: "False completion is treated as an ordinary race and immediately enters bounded polling."
    missing:
      - "Preserve typed completion outcomes across the repository boundary."
      - "After possible commit/lost response, reread the same fingerprinted command and replay completed state; otherwise return upload_service_unavailable."
      - "Inject endpoint/timeout/generic SDK failures below transact_write_items for regular and SSE, including commit-then-raise."
  - truth: "A resumed committed conversation loads the exact complete stored attachment set before extraction or AI"
    status: failed
    reason: "get_attachments ignores DynamoDB UnprocessedKeys and missing requested IDs, and resume code silently builds prepared from the returned subset."
    artifacts:
      - path: "src/stoa/db/repositories/attachment_repo.py"
        issue: "get_attachments performs one BatchGetItem and returns a partial dictionary without completeness enforcement."
      - path: "src/stoa/routers/conversations.py"
        issue: "message_committed/ai_running recovery filters missing attachment IDs out and continues to extraction and AI."
    missing:
      - "Retry UnprocessedKeys with a bounded policy and redacted dependency failure."
      - "Require the returned active owner-bound immutable IDs to equal the stored requested IDs before claiming/running AI."
      - "Add multi-round unprocessed and permanently missing item tests with zero extraction/AI/completion effects."
  - truth: "Conversation deletion and account purge exhaustively process every owner attachment and association page"
    status: failed
    reason: "list_owner_attachment_items discards LastEvaluatedKey; release and purge treat the first page as exhaustive, including joins between association and attachment metadata."
    artifacts:
      - path: "src/stoa/db/repositories/attachment_repo.py"
        issue: "The GSI query has no pagination loop or continuation contract."
      - path: "src/stoa/services/attachment_service.py"
        issue: "release_resource_attachments and purge_student_attachments cannot resume or join records across pages."
    missing:
      - "Exhaustively paginate or persist a bounded deletion continuation until all pages are processed."
      - "Join association and attachment metadata safely across page boundaries."
      - "Add split-page conversation deletion and account purge tests proving all references and the exact last physical version are removed."
deferred:
  - truth: "Real S3 multipart, version, promotion, overwrite, and restart-recovery behavior is observed in an approved non-production environment"
    addressed_in: "Phase 479"
    evidence: "Phase 479 defines/imports authoritative S3 lifecycle and policies and requires staging infrastructure evidence."
  - truth: "The cleanup scheduler, retries, alarms, and IaC are deployed and observed"
    addressed_in: "Phase 479"
    evidence: "Phase 479 success criteria require unused uploads and lifecycle ownership to be visible in versioned infrastructure and runbooks."
  - truth: "Production/deployed log redaction is captured from the promoted artifact"
    addressed_in: "Phase 480"
    evidence: "Phase 480 V9PRIV-04 requires captured logs without student/model text, keys, or provider payloads."
---

# Phase 473: Student Content Privacy And Practice Integrity Verification Report

**Phase Goal:** Ensure student uploads and exercise previews cannot expose another user's content or answers.
**Verified:** 2026-07-17T09:30:53Z
**Status:** `gaps_found`
**Re-verification:** Yes — after Plans 473-15 through 473-17
**Tested candidate checked:** `bc61107b920b158201ce4927485986d43aac59c8`

## Verdict

Phase 473 is not ready to close. The practice-answer boundary and question OCR ownership remain locally sound, and Plans 15/16 did close strict issuance/assembly/promotion coordinates, candidate-local cleanup isolation, provider Body ownership, and most conversation transport adapters. However, four independently reproduced code paths remain ship-blocking:

1. multipart UploadPart/ListParts success accepts an unusable ETag and removes the retry lease;
2. the real message-completion repository boundary swallows typed retryable failure;
3. committed conversation replay can continue with a partial attachment set;
4. conversation deletion/account purge stop at the first owner GSI page.

The exact nine-module Phase 473 matrix still passes **445 tests**, but those tests replace or omit the disputed lower boundaries. Passing broad tests therefore does not falsify the direct probes below. V9PRIV-02 remains blocked and the phase status is `gaps_found`.

## Goal Achievement

### Observable Truths

| # | ROADMAP observable truth | Status | Evidence |
|---|---|---|---|
| 1 | A student can upload a supported bounded file and use it once in their own question. | ✓ VERIFIED LOCALLY | Public question input is an opaque `AttachmentReference`; owner/type/status reservation precedes OCR; the conditional question/attachment transaction remains implemented and its positive/negative controls pass. |
| 2 | Foreign, malformed, missing, expired, oversized, mismatched, and reused uploads are denied with stable redacted errors. | ✗ FAILED | Malformed UploadPart/ListParts ETags are accepted as success; message completion retryable dependency is masked as `False`/polling; deterministic bind errors can also be masked as `message_in_progress`. |
| 3 | No student preview/overview/path/lesson response contains answers or answer-derived explanation before submission. | ✓ VERIFIED LOCALLY | Typed preview allowlists contain no answer fields; route projections use them; the recursive practice matrix passes. |
| 4 | Authorized teacher/admin tooling retains an explicit answer-bearing contract separate from the student contract. | ✓ VERIFIED LOCALLY | `PrivilegedPracticeAnswer` and the centrally scoped curriculum-answer dependency remain distinct from preview and mutation contracts. |
| 5 | Existing question responses hide object keys and raw OCR text. | ✓ VERIFIED LOCALLY | `QuestionResponse` exposes safe attachment/OCR metadata only; request models forbid storage coordinates; response/log canary controls pass locally. |

**Score:** 4/5 roadmap truths verified.

The score does not soften the verdict: any one blocker prevents goal closure, and blockers 3/4 invalidate additional Plan 03/10 conversation and retention must-haves not fully expressed by the five roadmap rows.

## Re-verification Result

The previous report's strict-coordinate CR-009, cleanup-isolation WR-009, and Body-ownership WR-010 gaps are closed in the source. The prior WR-011 conversation transport concern is only partially closed: `_conversation_repository_call` covers connected calls, but `complete_message_command` erases the typed outcome before the adapter sees it.

The four blockers below are newly discovered adjacent paths, not evidence of a source change after candidate `bc61107`; current implementation source/tests are byte-identical to that candidate. They demonstrate that the candidate's selected tests were incomplete.

## Mandatory Review Finding Adjudication

### 1. UploadPart/ListParts ETag invariant — BLOCKER, reproduced

- Service path: `put_upload_chunk` passes `str(result.get("ETag") or "")` to repository completion; restart reconciliation does the same for `ListParts` (`attachment_service.py:539-559`, `575-619`).
- Repository path: `complete_upload_part` accepts any runtime value, persists it, changes status to `completed`, and removes `lease_expires_at` (`attachment_repo.py:410-440`).
- Assembly trusts every completed row and forwards `provider_etag` to `CompleteMultipartUpload` (`attachment_service.py:684-724`).
- Direct service probes returned an accepted receipt and `ledger completed etag ''` for both UploadPart success and ListParts adoption without ETag.
- Direct repository probes accepted `None`, `""`, whitespace, and `123`, returning `True` and storing each value.

This falsifies the Plan 15 claim that every fence-removing provider success coordinate is strict. Issuance `UploadId`, staging `VersionId`/ETag, and immutable `VersionId`/ETag are strict; part ETag is not.

### 2. `complete_message_command` typed retry — BLOCKER, reproduced

`transact` correctly converts generic described-transaction transport to `AttachmentTransactionError(RETRYABLE_DEPENDENCY)`, but `complete_message_command` catches all `AttachmentTransactionError` values and returns `False` (`attachment_repo.py:1141-1191`). The router then enters `_wait_for_message_command` (`conversations.py:908-922`).

The direct below-boundary probe forced `RETRYABLE_DEPENDENCY` from `transact`; actual `complete_message_command` returned `False`. Existing completion transport tests monkeypatch `complete_message_command` itself, so they never test this behavior. This leaves prior WR-011 incomplete and violates stable dependency/error and explicit lost-response convergence claims.

### 3. Partial `BatchGetItem` replay — BLOCKER, reproduced

`get_attachments` performs exactly one high- or low-level `BatchGetItem`, ignores `UnprocessedKeys`, and returns whatever `Responses` contains (`attachment_repo.py:901-936`). During committed recovery, the router constructs `prepared` only for IDs present in the partial dictionary and continues (`conversations.py:678-689`).

The direct fake returned attachment `a`, left `b` under `UnprocessedKeys`, and the repository returned one call/one ID with `missing_b=True`. No completeness check failed. A normal partial DynamoDB response can therefore alter the attachment context used for the final assistant result under the same command fingerprint.

### 4. Owner attachment pagination — BLOCKER, reproduced

`list_owner_attachment_items` issues one `GSI-StudentId` query and discards `LastEvaluatedKey` (`attachment_repo.py:1473-1484`). `release_resource_attachments` and `purge_student_attachments` consume the result as exhaustive (`attachment_service.py:1571-1676`).

The direct fake returned a `LastEvaluatedKey`; the repository made one call and never sent `ExclusiveStartKey`. Later-page associations/metadata are unreachable, including when the two halves of a join land on different pages. This violates the explicit deletion/account-closure retention contract in D-10.

### 5. Deterministic bind errors masked after claim — WARNING, reproduced

After command/quota claim, the bind block catches every `AttachmentDecisionError`, rereads a same-fingerprint `claimed` command, and polls (`conversations.py:754-776`). A direct command probe injected `storage_quota_exceeded`; the observed public decision became `message_in_progress`. The daily chat quota claim also remains charged.

This is a real stable-error/recovery defect, but it does not independently expose another user's content. It should be fixed with outcome-aware ambiguity handling; broader rejected-counter convergence also intersects Phase 475's V9DATA-04 ownership.

### 6. External OOXML relationship guard — WARNING, reproduced

`_passive_archive` lowercases archive names but compares them to mixed-case `"externalLinks/"`, and scans relationship XML only for the exact bytes `targetmode="external"` (`document_extraction_service.py:19-26`, `180-197`). Direct XLSX and DOCX probes showed that `xl/externalLinks/externalLink1.xml` and `TargetMode = "External"` were accepted and extracted.

The extractor reads only allowlisted internal XML and does not fetch the external target, so this is not evidence of cross-user disclosure. It does violate the plan's no-active/no-external-content safety contract and must be hardened by lowercased markers plus parsed `.rels` attributes.

## Plans 15/16 Exact-Path Check

| Claimed closure | Status | Actual evidence |
|---|---|---|
| Strict required issuance/staging/promotion coordinates before fence removal | ✓ CLOSED for named Plan 15 paths | `_required_provider_coordinate` rejects non-string/blank values; repository `_require_provider_coordinate` defends multipart issuance, staging completion, and immutable success. UploadPart ETag is a separate uncovered blocker. |
| Truthful crash recovery/no false cleanup completion | ✓ CLOSED for the Plan 15 malformed issuance/assembly/promotion matrix | Restart/no-false-completion tests pass; exact provider coordinates remain durable on malformed major transitions. Part-ledger repair is not closed. |
| Per-candidate cleanup isolation | ✓ CLOSED | `cleanup_expired_uploads` catches candidate-local failures inside the loop and continues, while global listing remains outside the boundary (`upload_cleanup.py:70-87`). |
| Provider Body ownership before read inspection and exact-once close offer | ✓ CLOSED LOCALLY | Both staging validation and immutable extraction place `getattr(body, "read")` inside an outer `try/finally`; malformed Body matrices pass. Real connection-pool behavior remains NOT RUN. |
| Normalized conversation repository transport with regular/SSE parity | ⚠ PARTIAL | Stage A, claim, polling, lease and direct adapter paths are normalized; actual completion transaction semantics are swallowed inside `complete_message_command`. |

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/stoa/models/attachment.py` | Opaque coordinate-free upload/attachment contracts | ✓ VERIFIED | Substantive and wired into files/questions/conversations. |
| `src/stoa/services/file_validation_service.py` | Bounded supported-file validation | ✓ VERIFIED | Format/size/magic/container validators are substantive; boundary tests pass. |
| `src/stoa/db/repositories/attachment_repo.py` | Conditional lifecycle, transactions, batch reads and retention queries | ✗ PARTIAL/BLOCKING | Core implementation exists, but UploadPart coordinate, BatchGet completeness, completion outcome, and owner pagination are defective. |
| `src/stoa/services/attachment_service.py` | Owner lifecycle/association/extraction/cleanup orchestration | ✗ PARTIAL/BLOCKING | Major coordinates/Body ownership are fixed; part completion and paginated retention wiring are incomplete. |
| `src/stoa/routers/conversations.py` | Exact command replay with full attachment set and structured dependencies | ✗ PARTIAL/BLOCKING | Regular/SSE share the executor, but completion and partial committed-recovery paths are hollow at lower boundaries. |
| `src/stoa/models/practice.py` | Separate preview/result/privileged schemas | ✓ VERIFIED | Preview schema structurally excludes answer-bearing fields; result requires attempt ID. |
| `src/stoa/services/practice_projection_service.py` | Central answer-free/result/hint projection | ✓ VERIFIED | Wired across practice/curriculum routes; no answer toggle enters preview builders. |
| `src/stoa/jobs/upload_cleanup.py` | Bounded, isolated, coordinate-free cleanup job | ✓ VERIFIED LOCALLY | Candidate isolation is substantive and tested; deployed scheduling is deferred. |
| `docs/security/phase-473-evidence.md` and manifest | Source-bound honest evidence | ⚠ STRUCTURALLY VALID, SUBSTANTIVELY STALE | Candidate binding, hashes and NOT RUN statements reproduce, but local closure claims omit four real source paths. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Files gateway | upload part ledger | UploadPart/ListParts -> `complete_upload_part` | ✗ NOT SAFE | Malformed ETag can permanently complete the ledger row. |
| Part ledger | multipart assembly | completed rows -> provider ETag list | ✗ NOT SAFE | Assembly forwards stored empty ETag. |
| Conversation completion | transaction classifier | `complete_message_command` -> `transact` | ✗ BROKEN | Typed retryable dependency is collapsed to `False`. |
| Committed message | immutable attachment context | stored IDs -> `get_attachments` -> extraction | ✗ HOLLOW/PARTIAL | Missing/unprocessed IDs are silently filtered out. |
| Conversation/account deletion | all owner attachments | GSI query -> release/purge | ✗ TRUNCATED | Only the first page is processed. |
| Student practice preview | allowlist projection | practice/curriculum routes -> preview builders | ✓ WIRED | Recursive answer-canary tests pass. |
| Student answer | result projection | `put_attempt` receipt -> `build_attempt_result` | ✓ WIRED | Result construction follows durable attempt persistence. |
| Privileged answer route | central authorization | load-once challenge -> assignment/admin policy | ✓ WIRED | Scoped route and mutation-negative controls pass. |

## Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Produces complete/real data | Status |
|---|---|---|---|---|
| Question OCR | resolved attachment record | Actor-owned upload/saved-attachment repository record | Yes; immutable tuple reaches OCR only after authorization | ✓ FLOWING |
| Conversation replay | `prepared` attachment records | one `BatchGetItem` over stored attachment IDs | No; unprocessed/missing IDs are discarded | ✗ HOLLOW PARTIAL FLOW |
| Conversation retention | owner attachment/association rows | one GSI query | No; later pages are discarded | ✗ TRUNCATED FLOW |
| Practice previews | challenge/lesson/curriculum records | repository -> typed allowlist builders | Yes; answer fields are not copied | ✓ FLOWING |
| Practice result | `recorded_attempt` | conditional `put_attempt` receipt | Yes; missing receipt fails result construction | ✓ FLOWING |

## Behavioral Spot-Checks

| Behavior | Command/probe | Result | Status |
|---|---|---|---|
| Exact Phase 473 matrix | nine-module pytest command from Plan 17 | `445 passed in 5.70s` | ✓ PASS, but insufficient coverage |
| Existing remediation/review-adjacent controls | seven exact test selectors | `34 passed in 0.26s` | ✓ PASS, demonstrates mocked-boundary blind spot |
| Repository UploadPart ETag guard | direct `complete_upload_part` fake-table probe | Accepted/stored `None`, empty, whitespace, and integer; returned `True` | ✗ FAIL |
| UploadPart service path | direct `put_upload_chunk` fake provider with missing ETag | `receipt accepted`, ledger `completed`, ETag `''` | ✗ FAIL |
| ListParts restart adoption | direct `_reconcile_provider_part` fake without ETag | `adopted True`, ledger `completed`, ETag `''` | ✗ FAIL |
| Message completion typed retry | direct `complete_message_command` with `RETRYABLE_DEPENDENCY` | Returned `False` | ✗ FAIL |
| Batch attachment completeness | direct `get_attachments` with `UnprocessedKeys` | One call; returned only `a`; silently missed `b` | ✗ FAIL |
| Owner pagination | direct GSI fake with `LastEvaluatedKey` | One query; no `ExclusiveStartKey` | ✗ FAIL |
| Deterministic bind error | direct command probe with storage quota error | Original `storage_quota_exceeded`; observed `message_in_progress` | ⚠ WARNING |
| OOXML external content | direct XLSX/DOCX archive probes | External-link member and whitespace relationship accepted | ⚠ WARNING |
| Evidence manifest | independent SHA-256/byte reproduction | PASS | ✓ PASS |
| Authorization inventory | generator `--check` | PASS | ✓ PASS |

## Probe Execution

No phase-declared or conventional `scripts/*/tests/probe-*.sh` probes exist. Direct repository/provider probes above were run in isolated Python processes from the repository root.

## Requirements Coverage

| Requirement | Source plans | Status | Evidence |
|---|---|---|---|
| V9PRIV-01 | 01, 02, 04, 08–10, 12–17 | ✓ SATISFIED LOCALLY | Actor-owned opaque question upload, immutable OCR input, conditional reservation/association and ownership concealment remain implemented/tested. |
| V9PRIV-02 | 01–03, 07–17 | ✗ BLOCKED | UploadPart malformed success, structured completion dependency, partial committed attachment recovery, and exhaustive retention cleanup are incomplete. |
| V9PRIV-03 | 01, 05–07, 10–11, 13–14, 17 | ✓ SATISFIED LOCALLY | Preview allowlists, attempt-before-result, safe hints and scoped privileged reads remain intact. |

No orphaned Phase 473 requirement IDs were found: ROADMAP, plans and REQUIREMENTS all map V9PRIV-01/02/03 to this phase. REQUIREMENTS' checklist still shows V9PRIV-02 unchecked even though its traceability table says Complete; this verification resolves the conflict as **blocked**.

## Decision Coverage

| Decision | Status | Adjudication |
|---|---|---|
| D-01 | ✓ HONORED | Question images remain JPEG/PNG only. |
| D-02 | ✓ HONORED | 10 MiB and 4096-edge enforcement remains tested. |
| D-03 | ✓ HONORED WITH WARNING | Supported conversation formats remain available; external OOXML active-content rejection is incomplete (WR-02). |
| D-04 | ✓ HONORED | Non-image documents retain the 50 MiB bound. |
| D-05 | ✓ HONORED | Extension/MIME/magic/container validation remains wired before durable use. |
| D-06 | ✓ HONORED | Unbound intent expiry remains 1,800 seconds. |
| D-07 | ✗ NOT HONORED | Completion retry ambiguity and partial attachment reload do not guarantee replay of the original complete result. |
| D-08 | ✗ NOT HONORED | Malformed part success removes the retry lease and returns accepted instead of preserving bounded transient repair. |
| D-09 | ✓ HONORED LOCALLY | Plans 15/16 preserve non-consumable cleanup state and candidate isolation; live scheduler/S3 remains deferred. |
| D-10 | ✗ NOT HONORED | Deletion/account closure does not process attachment rows beyond the first page. |
| D-11 | ✓ HONORED WITH WARNING | 5/15 GiB limits and no auto-deletion remain; a transaction-time quota error can be masked after chat command claim (WR-01). |
| D-12 | ✓ HONORED | Owner saved-attachment reuse remains a logical association without duplicate storage charge. |
| D-13 | ✓ HONORED | Verified Actor remains authoritative; public contracts reject owner/storage coordinates. |
| D-14 | ✓ HONORED | Missing and foreign resources retain the same redacted external behavior. |
| D-15 | ✓ HONORED | Owner-visible expiry remains `upload_expired`. |
| D-16 | ✗ NOT HONORED | Malformed part success and swallowed completion dependency do not produce the required stable actionable error; deterministic bind errors may become `message_in_progress`. |
| D-17 | ✓ HONORED LOCALLY | Public models/log telemetry/evidence remain coordinate/content redacted; production capture is Phase 480-owned. |
| D-18 | ✓ HONORED | Answer reveal follows a durable attempt receipt. |
| D-19 | ✓ HONORED | Only explicitly approved non-answer hints are returned before submission. |
| D-20 | ✓ HONORED | Student preview families remain answer-free; result is a separate owner attempt contract. |
| D-21 | ✓ HONORED | Assigned teachers and active admins use a narrow read-only answer policy. |
| D-22 | ✓ HONORED | Anonymous/student/parent/unassigned/stale/wrong-scope teacher cases are denied. |

**Decision coverage:** 18/22 honored; D-07, D-08, D-10 and D-16 fail.

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/stoa/routers/conversations.py` | 1011 | Existing “structured placeholder” comment in legacy initial-message path | ℹ INFO | Not a debt marker and not involved in the four blockers; initial conversation creation still uses the legacy helper without attachments. |

No unreferenced `TBD`, `FIXME`, or `XXX` markers were found in phase-modified production files. The scanned `return {}`/`return []` matches are legitimate empty-input/optional-member results, not user-visible stubs.

## Evidence Integrity And External Boundaries

The evidence mechanics are reproducible:

- candidate `bc61107b920b158201ce4927485986d43aac59c8` exists;
- current source/tests differ from it only in planning/evidence/review artifacts, not implementation;
- the evidence manifest hashes and byte sizes reproduce;
- route authorization inventory `--check` passes;
- real S3, deployed scheduler/IaC and production logs are explicitly `NOT RUN`.

Those facts prove source binding and honest external scope. They do not prove that the selected local tests covered every relevant source path. The evidence and VALIDATION documents are therefore structurally valid but substantively stale wherever they claim complete local closure of V9PRIV-02, D-07, D-08, D-10, D-16 and conversation/retention replay behavior.

External real-provider/deployment/log observations remain deferred to Phases 479/480 and do not cause this status. The four locally observable blockers do.

## Gaps Summary

Four blockers prevent goal closure:

1. require and preserve a usable UploadPart/ListParts ETag before ledger completion;
2. preserve typed message-completion outcomes and explicitly reread ambiguous commits;
3. require the exact complete stored attachment set before resumed extraction/AI;
4. exhaustively paginate and resume owner attachment deletion/purge.

Two additional warnings should be fixed alongside those blockers: preserve deterministic attachment errors after command claim, and parse OOXML external relationships case/whitespace/quoting independently.

The gaps are structured in frontmatter for the next gap-closure planning pass. No implementation files were modified and no commit was created.

---

_Verified: 2026-07-17T09:30:53Z_
_Verifier: the agent (gsd-verifier)_
