---
phase: 473-student-content-privacy-and-practice-integrity
verified: 2026-07-16T21:37:06Z
status: gaps_found
score: 4/5 must-haves verified
requirements:
  passed: 2
  total: 3
decision_coverage:
  honored: 20
  total: 22
  not_honored: [D-09, D-16]
gaps:
  - id: CR-009
    severity: blocker
    requirement: V9PRIV-02
  - id: WR-009
    severity: warning
    requirement: V9PRIV-02
  - id: WR-010
    severity: warning
    requirement: V9PRIV-02
  - id: WR-011
    severity: warning
    requirement: V9PRIV-02
---

# Phase 473: Student Content Privacy And Practice Integrity Verification Report

**Phase Goal:** Ensure student uploads and exercise previews cannot expose another user's content or answers.
**Verified:** 2026-07-16T21:37:06Z
**Status:** `gaps_found`

## Verdict

Phase 473 is not ready to close. The independently observed full suite (1,344 passed), Phase 472 regression (636 passed), schema/codebase-drift checks, and evidence-manifest integrity are valid observations, and the original CR-001 plus WR-001 through WR-006 defects are closed. Actual-code tracing nevertheless confirms the fresh review's CR-009 and WR-009 through WR-011. The passing suite does not exercise these malformed-success, batch-isolation, malformed-body-ownership, or repository-transport paths.

CR-009 is a release blocker. Empty provider `UploadId`/`VersionId` values are accepted as successful coordinates and the repository removes the durable operation fence. A completed staging object can consequently become unaddressable to cleanup while the row can still advance toward `cleanup_complete`. This recreates CR-007's forbidden retention/truth outcome, violates D-09, and blocks V9PRIV-02. WR-011 separately leaves conversation Stage-A, polling, transaction, and lost-response reread transport failures outside the stable structured-error boundary required by D-16/V9PRIV-02.

Real S3 behavior, deployed scheduler/IaC, and production-log capture remain honestly **NOT RUN**. They belong to Phases 479/480 and do not by themselves block this local verification; the status is `gaps_found` because locally inspectable source paths are defective.

## Goal Achievement

### Observable Truths

| # | ROADMAP observable truth | Status | Evidence |
|---|---|---|---|
| 1 | A student can upload a supported bounded file and use it once in their own question. | ✓ VERIFIED LOCALLY | Opaque owner-scoped upload, immutable validation/OCR, and atomic question association are implemented; V9PRIV-01 controls pass. |
| 2 | Foreign, malformed, missing, expired, oversized, mismatched, and reused uploads are denied with stable redacted errors. | ✗ FAILED | Empty provider success coordinates are persisted as success, and connected conversation repository transport failures can escape as raw/unstructured 500s. Cleanup can lose the exact target needed to remove abandoned bytes. |
| 3 | Student preview/overview/path/lesson responses contain no answer or answer-derived explanation before submission. | ✓ VERIFIED LOCALLY | Typed answer-free projections and recursive route controls pass; results follow durable attempt recording. |
| 4 | Assigned teachers and admins retain a separate explicit answer-bearing read contract. | ✓ VERIFIED LOCALLY | Assignment-scoped `teacher` and global admin reads remain separate from student contracts and teacher mutation authority. |
| 5 | Question responses hide object keys and raw OCR text. | ✓ VERIFIED LOCALLY | Public models and privacy deny controls remain opaque; no reviewed change reintroduced coordinates or OCR material. |

**Score:** 4/5 truths verified.

## Fresh Finding Adjudication

### CR-009 — Empty provider success coordinates erase the recovery fence (BLOCKER, confirmed)

- `create_upload_intent` converts `created["UploadId"]` to `str` without requiring a non-empty value (`attachment_service.py:357-385`).
- multipart completion converts missing/empty `VersionId` and `ETag` to `""` and sends them to the success transition (`attachment_service.py:691-739`).
- `record_staging_multipart` and `recover_staging_completion` accept those empty values and call `_fenced_transition(..., remove_operation=True)` (`attachment_repo.py:256-269,493-510`).
- With empty `VersionId`, validation rejects the row only after the `staging_assembly` operation identity has been removed. Cleanup therefore cannot recover the exact completed version, may persist `cleanup_staging_deleted`, and can later report completion without deleting the provider object.

The existing malformed-provider tests cover non-mapping responses, not `{}`, empty `UploadId`, empty `VersionId`, or the chosen ETag invariant. CR-007 is closed only for well-formed coordinates; its must-have invariant is not globally closed.

### WR-009 — One stale-recovery lookup failure aborts the cleanup batch (confirmed)

`_matching_exact_version` lets `_provider_mapping` raise `AttachmentDecisionError` on list/head failures (`attachment_service.py:282-303`), while `cleanup_upload_intent` catches only `AttachmentRepositoryConflict` (`attachment_service.py:238-240`). The scheduled job has no per-candidate exception boundary (`upload_cleanup.py:57-79`). One transient or malformed candidate can therefore stop all later candidates and prevent a bounded retryable summary. This weakens D-09's asynchronous deletion guarantee.

### WR-010 — Closable non-readable provider bodies are not closed (confirmed)

Both validation and conversation extraction validate `body.read` before entering the `try/finally` that owns `close` (`attachment_service.py:944-949,1486-1491`). A non-`None`, closable body with a missing/non-callable or raising `read` attribute exits before `_close_provider_body`. The regular readable-body matrix therefore does not close WR-008 on every returned-body exit. This is resource-safety debt under V9PRIV-02; it does not independently demonstrate forbidden-content disclosure, so D-17 remains locally satisfied.

### WR-011 — Conversation replay exposes repository transport failures (confirmed)

- Stage-A calls `get_message_command` directly (`conversations.py:147-163`).
- replay polling calls it directly (`conversations.py:550-560`).
- the lost-response reread also calls it outside a dependency translator (`conversations.py:698-716`).
- `attachment_repo.transact` catches only `ClientError` (`attachment_repo.py:1875-1900`), and `bind_message_attachments` catches only `AttachmentTransactionError`.

Endpoint/transport exceptions and other repository failures can bypass `upload_service_unavailable`, skip same-fingerprint convergence, and surface as an unstructured 500. The current lost-response test injects an already-normalized transaction error, so it does not prove the actual transport path. D-16 and V9PRIV-02 remain incomplete.

## Prior Finding Re-adjudication

| Finding | Status | Independent adjudication |
|---|---|---|
| CR-001 | ✓ CLOSED | Validation reads an exact staging `VersionId`; the same bounded spool is promoted; immutable consumers verify version/checksum/length. |
| WR-001 | ✓ CLOSED | Public request/response models expose only opaque application IDs and safe attachment metadata. |
| WR-002 | ✓ CLOSED LOCALLY | Reviewed paths use allowlisted private telemetry and safe categories; deployed production capture remains Phase 480-owned. |
| WR-003 | ✓ CLOSED for classified `ClientError` cancellation outcomes | Ordered operation semantics distinguish quota, concealed resource, and retryable dependency outcomes. WR-011 is a separate unclassified transport path. |
| WR-004 | ⚠ PARTIAL | Exception and missing-key issuance failures are stable, but CR-009 accepts an empty success coordinate. |
| WR-005 | ✓ CLOSED for modeled command races | Deterministic command/message/attachment IDs and tested regular/SSE replay converge. WR-011 covers unmodeled transport failures. |
| CR-007 | ⚠ REOPENED BY CR-009 | Exact recorded staging/immutable versions are cleaned correctly, but an empty success coordinate discards the record required to discover the exact target. |
| WR-006 | ✓ CLOSED | Command-derived fresh attachment IDs and durable keys remain exact across replay; reuse consumes no fresh ID. |
| WR-007 | ⚠ PARTIAL | File gateway stages are normalized; cleanup and conversation replay still contain unclassified connected dependency exits (WR-009/WR-011). |
| WR-008 | ⚠ PARTIAL | Readable bodies close on tested exits; closable non-readable bodies escape before ownership is established (WR-010). |

## Requirements Coverage

| Requirement | Status | Adjudication |
|---|---|---|
| V9PRIV-01 | ✓ SATISFIED LOCALLY | Actor-owned opaque uploads, immutable OCR coordinates, and atomic conditional question association remain implemented and tested. |
| V9PRIV-02 | ✗ BLOCKED | CR-009 permits false-success coordinates and unsafe cleanup truth; WR-009/010/011 leave cleanup isolation, resource ownership, and stable dependency handling incomplete. |
| V9PRIV-03 | ✓ SATISFIED LOCALLY | Student previews remain structurally answer-free; attempts gate result disclosure; privileged reads remain separate and scoped. |

**Coverage:** 2/3 requirements satisfied.

## Decision Adjudication

| Decisions | Status | Evidence |
|---|---|---|
| D-01–D-08 | ✓ HONORED | Supported formats, bounded validation, 30-minute intent expiry, atomic consumption/replay, and terminal-vs-retryable states remain implemented and exercised. |
| D-09 | ✗ NOT HONORED | CR-009 can discard the only exact recovery coordinate; WR-009 can starve later cleanup candidates. Asynchronous deletion and cleanup truth are not guaranteed. |
| D-10–D-15 | ✓ HONORED | Durable history, 5/15 GiB quotas, reuse without double charge, Actor authority, concealment, and `upload_expired` remain intact. |
| D-16 | ✗ NOT HONORED | WR-011 permits unstructured conversation dependency failures; empty provider success responses are not consistently rejected as the stable temporary-service outcome. |
| D-17 | ✓ HONORED LOCALLY, WITH WR-010 DEBT | Public/log/evidence deny controls remain coordinate/content-safe. The malformed-body resource leak must still be fixed; deployed log capture remains Phase 480-owned. |
| D-18–D-22 | ✓ HONORED | Recorded-attempt gating, directional hints, separate answer contracts, assigned `teacher`/admin reads, and denied role/scope matrix remain verified. |

**Coverage:** 20/22 decisions honored; D-09 and D-16 are not honored.

## Evidence Integrity And Boundaries

The source-lock mechanics are reproducible: candidate `b3964d52eb483f4e80a4bca0366bbbcd79468059`, its evidence-parent relation, exact post-source evidence diff, manifest hashes/byte counts, route inventory, privacy denylist, and clean-tree observations are internally consistent. They prove what the selected tests observed, not the absence of untested source defects.

Consequently, `docs/security/phase-473-evidence.md`, its manifest, and `473-VALIDATION.md` are structurally valid but substantively stale where they claim CR-007, WR-007, WR-008, D-09, D-16, and V9PRIV-02 are fully closed. They must be regenerated from a new immutable candidate after repair.

| External observation | Status | Phase ownership / impact |
|---|---|---|
| Real S3 multipart/version/promotion/recovery | **NOT RUN** | Phase 479 infrastructure evidence; honest deferred boundary, not this local failure's cause. |
| Deployed cleanup scheduler/IaC/retries/alarms | **NOT RUN** | Phase 479; local cleanup semantics still must be correct first. |
| Production/deployed log capture | **NOT RUN** | Phase 480 observability/privacy evidence; local deny controls remain useful but not production proof. |

## Required Gap Plans

### Plan 473-15 — Provider-coordinate invariants and isolated cleanup recovery

1. Require non-empty `UploadId`, staging `VersionId`, and the chosen required ETag invariant before any transition removes an operation fence.
2. Add repository defense-in-depth rejecting empty multipart/version coordinates.
3. Preserve the `staging_issuance`/`staging_assembly` operation on malformed success so restart and exact-key cleanup remain possible.
4. Normalize expected provider/repository lookup failures to a coordinate-free `retryable` outcome and isolate each scheduled candidate.
5. Add `{}`, empty/missing-coordinate, first-candidate-fails/later-candidate-converges, restart, and no-false-`cleanup_complete` tests.

### Plan 473-16 — Provider-body ownership and conversation transport convergence

1. Establish `try/finally` ownership immediately after receiving any non-`None` provider body; validate `read` inside it and close exactly once.
2. Normalize Stage-A, transaction, replay-poll, and lost-response repository transport failures to stable structured outcomes without exception/provider diagnostics.
3. Preserve same-fingerprint reread/convergence when the transaction committed but its response was lost.
4. Add route-level generic transport injections and closable non-readable/read-property-failure spies with response/log privacy canaries.

### Plan 473-17 — Re-lock source and republish evidence

After 473-15/16, lock a clean candidate, rerun the Phase 473 matrix, exact Phase 472 regression, full suite, Ruff, inventory, manifest, and privacy denylist, then regenerate evidence/validation/manifest without inferring any external NOT RUN result.

## Final Determination

`gaps_found` — keep Phase 473 incomplete and route to `$gsd-plan-phase 473 --gaps`. Do not advance to Phase 474 based on the current evidence set.
