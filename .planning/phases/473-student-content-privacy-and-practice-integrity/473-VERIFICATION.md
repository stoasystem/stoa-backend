---
phase: 473-student-content-privacy-and-practice-integrity
verified: 2026-07-18T12:02:00Z
status: gaps_found
score: 4/5 must-haves verified
overrides_applied: 0
requirements:
  passed: 2
  total: 3
  blocked:
    - V9PRIV-02
decision_coverage:
  honored: 19
  total: 22
  not_honored:
    - D-10
    - D-16
    - D-17
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "UploadPart/ListParts acknowledgements now require exact ETag/checksum facts before ledger completion"
    - "Conversation completion preserves typed outcomes and reconciles ambiguous commits"
    - "Committed conversation replay requires a complete exact attachment set"
    - "Owner attachment retention and purge use exhaustive authoritative pagination"
    - "Deterministic bind errors retain their stable rejection outcome"
    - "OOXML admission parses and rejects external relationships through the semantic package boundary"
  gaps_remaining:
    - "Deletion-command claims compare an active lease with the new future expiry, and branch persistence is not bound to the returned claim"
    - "Private notification delivery calls providers directly when authoritative owner-generation metadata is missing or malformed"
  regressions: []
gaps:
  - truth: "Only one current deletion-command lease may mutate or finalize the durable 17-branch account-deletion proof"
    status: failed
    reason: "An unexpired running command is eligible for immediate takeover because its stored expiry is compared with the claimant's future expiry; the returned lease owner/version is discarded and branch writes condition only on generation and running status."
    artifacts:
      - path: "src/stoa/jobs/account_deletion.py"
        issue: "The job passes only a future lease expiry and then calls continue_command by command ID, discarding the returned claim identity."
      - path: "src/stoa/db/repositories/account_deletion_repo.py"
        issue: "Claim uses lease_expires_at < :expiry rather than current time; branch persistence has no lease-owner or command-version CAS."
      - path: "src/stoa/services/account_deletion_service.py"
        issue: "Continuation reloads mutable command state without an opaque claim token and may persist/finalize stale branch evidence."
    missing:
      - "Compare stored lease expiry with an explicit current epoch."
      - "Thread an opaque lease owner/version token through continuation, branch persistence, renewal, and finalization."
      - "Advance a CAS version/digest for branch writes and validate the durable branch-result set in the terminal transaction."
      - "Add two-worker unexpired, expired-takeover, stale-write, and stale-finalization tests."
  - truth: "Every private notification, push, and realtime provider effect is owner/fence/lease bound or explicitly sealed global non-private data"
    status: failed
    reason: "Email digest, push, and WebSocket delivery bypass the delivery-intent fence when owner-generation metadata is missing or invalid; direct probes delivered private payloads on those fallback paths."
    artifacts:
      - path: "src/stoa/services/notification_service.py"
        issue: "Digest and push fall back to direct provider calls when a positive account-fence generation is absent."
      - path: "src/stoa/services/websocket_service.py"
        issue: "Missing/invalid generation sets leased=False and fanout proceeds without an account-fence recheck."
    missing:
      - "Fail closed for private rows without authoritative owner and generation metadata."
      - "Resolve legacy ownership through a strongly consistent authoritative join before delivery."
      - "Permit an ownerless path only for a persisted sealed global_nonprivate classification."
      - "Route every other provider effect through the same intent/lease primitive and add deletion-race tests for missing, malformed, and stale generation metadata."
deferred:
  - truth: "Real S3 multipart, version, promotion, overwrite, and restart-recovery behavior is observed in an approved non-production environment"
    addressed_in: "Phase 479"
    evidence: "The checked evidence records P479-REAL-S3-MULTIPART-VERSIONING as NOT RUN."
  - truth: "The cleanup scheduler, retries, alarms, and IaC are deployed and observed"
    addressed_in: "Phase 480"
    evidence: "The checked evidence records P480-DEPLOYED-CLEANUP-SCHEDULER-IAC as NOT RUN."
  - truth: "Production/deployed log redaction is captured from the promoted artifact"
    addressed_in: "Phase 480"
    evidence: "The checked evidence records P480-PRODUCTION-LOGS as NOT RUN."
---

# Phase 473: Student Content Privacy And Practice Integrity Verification Report

**Phase Goal:** Ensure student uploads and exercise previews cannot expose another user's content or answers.
**Verified:** 2026-07-18T12:02:00Z
**Status:** `gaps_found`
**Re-verification:** Yes — after Plans 473-18 through 473-35
**Checked HEAD:** `1c661c9ea88cb56ee9294320ef4e08687befaab7`

## Verdict

Phase 473 is not ready to close. The prior upload, conversation, retention, document-validation, and practice-answer blockers are closed, and the full repository suite passes **1,923 tests**. However, both critical findings in the current code review reproduce against production boundaries:

1. active account-deletion leases are immediately stealable and stale workers are not fenced from branch writes/finalization;
2. private digest, push, and WebSocket payloads can bypass the account fence when owner-generation metadata is absent or malformed.

The second defect is a direct private-content delivery path after deletion begins. The first can corrupt the durable proof intended to prevent private rows or provider effects from surviving account closure. Either is sufficient to block V9PRIV-02 and Phase 473 closure. The three review warnings also reproduce, but are recorded separately because they do not independently demonstrate cross-user content disclosure.

## Goal Achievement

### Observable Truths

| # | ROADMAP observable truth | Status | Evidence |
|---|---|---|---|
| 1 | A student can upload a supported bounded file and use it once in their own question. | ✓ VERIFIED LOCALLY | Opaque owner-bound attachment references, exact provider acknowledgements, post-upload validation, conditional question association, and positive/negative controls are substantive and wired. |
| 2 | Foreign, malformed, missing, expired, oversized, mismatched, and reused uploads are denied with stable redacted errors. | ✗ FAILED AT EXPANDED PRIVATE-LIFECYCLE BOUNDARY | Upload-specific denial paths are now sound, but missing notification owner-generation facts result in direct private delivery rather than a stable fail-closed decision; deletion-command concurrency can also invalidate safe failure cleanup/account closure. |
| 3 | No student preview/overview/path/lesson response contains answers or answer-derived explanation before submission. | ✓ VERIFIED LOCALLY | Typed answer-free projections, immutable attempt receipts, and constant reviewed hint templates pass recursive route tests. |
| 4 | Authorized teacher/admin tooling retains an explicit answer-bearing contract separate from the student contract. | ✓ VERIFIED LOCALLY | Exact course/class teacher scope and narrow admin READ remain distinct from student preview/result contracts. |
| 5 | Existing question responses hide object keys and raw OCR text. | ✓ VERIFIED LOCALLY | Public models and response/log canaries expose only opaque identifiers and safe OCR metadata. |

**Score:** 4/5 roadmap truths verified.

## Re-verification Result

All four blockers and both warnings from the 2026-07-17 report are closed:

- Plan 18 enforces nonblank exact part ETag/checksum acknowledgements and repository invariants.
- Plans 20/21 preserve typed conversation dispositions, reconcile ambiguous completion, and require exact complete attachment/history snapshots.
- Plans 22/23 replace the one-page owner GSI assumption with authoritative exhaustive retention and purge contracts.
- Plan 20 preserves deterministic post-claim rejection instead of converting it to `message_in_progress`.
- Plan 24 establishes semantic OOXML identity and parses relationship attributes, rejecting external/escaping targets.

The focused provider/conversation/retention/document/practice regression set passed **231 tests**. The two current blockers arise in the account-deletion and outbound-notification scope introduced by Plans 29–35.

## Current Review Finding Adjudication

### CR-01 — BLOCKER, reproduced

`run_pending_deletions` creates an expiry two minutes in the future and passes it to `claim_deletion_command` (`account_deletion.py:76-98`). The repository takeover predicate is `lease_expires_at < :expiry` (`account_deletion_repo.py:836-881`), not `lease_expires_at < now_epoch`. A direct lower-boundary probe recorded no current-epoch value and the exact future-expiry predicate.

The claim returns a new owner and version, but the job discards them and calls `continue_command(command_id)`. `persist_branch_result` conditions only on generation and `status == running` (`account_deletion_repo.py:884-924`), while continuation accepts only a command ID (`account_deletion_service.py:1284-1330`). The probe confirmed no lease-owner/version fields in the branch CAS. A stale worker can therefore overwrite cursor, debt, epoch, or quiescence evidence and may race terminalization.

### CR-02 — BLOCKER, reproduced

Email digest and push use `run_delivery_intent` only for a positive owner generation, otherwise they call the provider directly (`notification_service.py:747-779`, `934-965`). WebSocket fanout similarly makes `leased=False` for invalid metadata and posts without a fence check (`websocket_service.py:193-277`).

Direct probes supplied private-looking push/WebSocket rows with no generation. Push returned `sent` with one provider call; WebSocket returned `delivered` with one provider call. No explicit sealed `global_nonprivate` classification was required. This contradicts Plan 34/35's fail-closed private-delivery and external-debt contract and can disclose private notification content after the permanent deletion fence is installed.

### WR-01 — WARNING, reproduced

`AccountDeletionService` defaults `now` to `lambda: ""` (`account_deletion_service.py:1264-1278`), and production construction in the scheduled job injects no clock. A direct production-constructor probe returned `''`; `BranchResult.persisted` consequently stored blank `updated_at`, and finalization receives the same blank value. Audit/fence lifecycle timestamps are therefore not trustworthy on the production path.

### WR-02 — WARNING, reproduced

Parent-profile scrubbing deep-copies the scanned row and replaces the full item (`account_deletion_repo.py:595-662`). The transaction checks both account fences and row existence/parent ID, but neither the original image nor a row version. The probe showed the complete stale profile—including its unchanged version and unrelated preference fields—being supplied as the replacement. A concurrent active-parent update can be lost.

### WR-03 — WARNING, reproduced

`claim_delivery_intent` accepts only `status == registered` (`notification_repo.py:361-387`). Its recorded condition contains no expired-claimed takeover and no current-time comparison. A crash after claim leaves the same intent returning `retryable_claim_conflict` forever, potentially retaining deletion debt indefinitely.

## Required Artifacts And Wiring

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/stoa/services/attachment_service.py` + `attachment_repo.py` | Exact owner/provider lifecycle, recovery, retention, and purge | ✓ VERIFIED LOCALLY | Prior acknowledgement, partial-replay, and pagination blockers are closed; focused tests pass. |
| `src/stoa/services/document_extraction_service.py` + semantic validators | Bounded no-active/no-external document use | ✓ VERIFIED LOCALLY | Plan 24's semantic package/parser isolation replaces the earlier byte/case heuristic. |
| `src/stoa/routers/conversations.py` + command repository | Exact replay and typed dependency behavior | ✓ VERIFIED LOCALLY | Complete attachment/history set and stale-worker AI fences are substantive and tested. |
| Practice models/projections/routes | Answer-free preview and immutable post-attempt result | ✓ VERIFIED LOCALLY | Preview, hint, receipt, and privileged scope contracts remain separate and wired. |
| `account_deletion_repo.py` + `account_deletion_service.py` | One lease-fenced, source-sealed, exact-once 17-branch deletion proof | ✗ PARTIAL/BLOCKING | Registry/seal logic exists, but claim ownership does not fence branch persistence/finalization. |
| `notification_service.py` + `websocket_service.py` | Every private provider effect owner/fence/intent bound | ✗ FAILED | Missing generation bypasses the intent and directly invokes push/email/WebSocket providers. |
| Checked boundary/private-store inventories | Deterministic source-bound coverage | ⚠ STRUCTURALLY VALID, INCOMPLETE BEHAVIORAL COVERAGE | Both `--check` commands pass, but their selected tests do not falsify the five reproduced paths. |
| Immutable Phase 473 evidence and manifest | Candidate-bound local receipts and honest external scope | ⚠ HASH-VALID, SUBSTANTIVELY STALE | All three manifest hashes/byte counts reproduce and current source matches candidate `cf3549a`; the 1,923 green nodes omit the unsafe lower-bound cases. |

## Key Link Verification

| From | To | Via | Status |
|---|---|---|---|
| deletion scanner | one current command worker | claim expiry + returned claim token | ✗ BROKEN |
| branch handler result | durable branch proof | lease/version-bound conditional persist | ✗ BROKEN |
| durable 17-branch proof | permanent fence finalization | durable current claim/result validation | ✗ UNSAFE UNDER CONCURRENCY |
| private notification row | provider effect | owner/generation intent and final fence recheck | ✗ BYPASSABLE |
| upload/provider acknowledgement | durable part/object ledger | closed parser + checksum + conditional transition | ✓ WIRED |
| committed conversation command | exact attachment/history context | complete consistent set + fingerprint anchor | ✓ WIRED |
| student practice route | answer-free projection | typed preview/hint builders | ✓ WIRED |
| recorded attempt | answer-bearing result | create-only immutable receipt | ✓ WIRED |

## Behavioral Verification

| Check | Result | Status |
|---|---|---|
| Full repository pytest | `1923 passed in 64.79s` | ✓ PASS, insufficient for five review paths |
| Focused provider/conversation/retention/document/practice matrix | `231 passed in 2.58s` | ✓ PASS |
| Current deletion/seal/notification suites | `46 passed in 0.28s` | ✓ PASS, demonstrates lower-boundary blind spot |
| Deletion claim probe | Predicate used future `:expiry`; no `:now_epoch` | ✗ FAIL |
| Branch persist probe | Predicate had generation/status only; no lease owner/version | ✗ FAIL |
| Missing-generation private push | `sent`, provider called once | ✗ FAIL |
| Missing-generation private WebSocket | `delivered`, provider called once | ✗ FAIL |
| Production deletion clock | `repr(now()) == ''`; persisted timestamp blank | ⚠ WARNING |
| Parent scrub replacement | Full stale profile and unchanged version supplied to replacement hook | ⚠ WARNING |
| Delivery-intent recovery | Claim predicate registered-only; no current-time/expired takeover | ⚠ WARNING |
| Boundary/private-store/route inventories | All `--check` commands pass | ✓ PASS |
| Targeted Ruff and `git diff --check` | Pass | ✓ PASS |
| Evidence manifest SHA-256 and byte counts | All three artifacts reproduce | ✓ PASS |

No phase-declared `probe-*.sh` exists. The failing checks above were run as isolated direct Python lower-boundary probes without modifying source or tests.

## Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| V9PRIV-01 | ✓ SATISFIED LOCALLY | Question OCR accepts only an active owner attachment and conditionally associates the exact immutable object with the created question; foreign/missing remain concealed. |
| V9PRIV-02 | ✗ BLOCKED | Core upload validation/lifecycle is fixed, but safe account-closure cleanup and private provider delivery are not lease/fence complete. |
| V9PRIV-03 | ✓ SATISFIED LOCALLY | Student previews remain answer-free; hints are closed reviewed constants; answer/explanation reads require an immutable recorded attempt or exact privileged scope. |

REQUIREMENTS marks all three complete, but this independent verification resolves V9PRIV-02 as blocked. No orphaned Phase 473 requirement IDs were found.

## Decision Coverage

| Decision group | Status | Adjudication |
|---|---|---|
| D-01–D-09 | ✓ HONORED LOCALLY | Supported formats/bounds, semantic validation, expiry, exact consumption/replay, retry recovery, and cleanup fences are implemented and tested; live S3 remains deferred. |
| D-10 | ✗ NOT HONORED | Account closure can run concurrent stale deletion workers, and private outbound effects can bypass the deletion fence. |
| D-11–D-15 | ✓ HONORED LOCALLY | Quotas, owner reuse, Actor authority, concealment, and `upload_expired` behavior remain intact. |
| D-16 | ✗ NOT HONORED | Missing private delivery metadata becomes direct delivery instead of a stable fail-closed/retryable action. |
| D-17 | ✗ NOT HONORED | Private notification content may be delivered after deletion without authoritative owner/fence validation. |
| D-18–D-22 | ✓ HONORED LOCALLY | Attempt-before-answer, non-derivable hints, answer-free student contracts, exact teacher/admin scope, and negative actor matrix pass. |

**Decision coverage:** 19/22 honored.

## Anti-Patterns And Planning Drift

No `TBD`, `FIXME`, `XXX`, `NotImplementedError`, or bare `pass` debt markers were found in the six files implicated by the current review. No project-local skill overrides or verification overrides exist.

All 35 plan/summary pairs exist and were reviewed. ROADMAP completion checkboxes remain stale for several executed plans (including 22/23, 29–32, 27, and 28), despite committed summaries and checked evidence. This is documentation drift, not the reason for `gaps_found`.

## External Boundaries

Real S3 behavior, deployed scheduler/IaC, and production logs remain explicitly `NOT RUN` under Phases 479/480. They are not counted as failures here. The current status is caused solely by locally observable production-code defects.

## Gaps Summary

Two blockers prevent closure:

1. make deletion claims compare against current time and thread a claim/version token through every branch write and finalization;
2. fail closed on unresolved private delivery ownership and route every private email/push/WebSocket effect through a fence-bound delivery intent.

Three warnings should be repaired alongside them: use valid production lifecycle timestamps, CAS parent-profile scrub writes, and add a safe delivery-intent crash-recovery state machine.

No implementation file was modified and no commit was created.

---

_Verified: 2026-07-18T12:02:00Z_
_Verifier: Codex (gsd-verifier)_
