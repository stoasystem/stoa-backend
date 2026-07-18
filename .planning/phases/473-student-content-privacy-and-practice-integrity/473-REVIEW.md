---
phase: 473-student-content-privacy-and-practice-integrity
reviewed: 2026-07-18T11:52:24Z
depth: standard
diff_base: fce68392137d1020a378d239c27af1cf9c7fe156^
head: faf6646baf8a0e1810738a575969cab8ce91994d
files_reviewed: 69
severity:
  critical: 2
  warning: 3
  info: 0
  total: 5
status: issues_found
---

# Phase 473 Code Review

## Summary

The deterministic 69-file `src`/`scripts` scope was reviewed at standard depth. The implementation closes the six findings from the earlier, narrower Phase 473 review, and the complete test suite and scoped lint pass. This final pass nevertheless found two ship-blocking account-deletion/provider-race defects and three robustness defects.

Verification performed:

- `.venv/bin/python -m pytest -q` — **1923 passed**
- `.venv/bin/ruff check <all 69 scoped Python files>` — **all checks passed**
- Source review — call-chain, conditional-write, deletion-fence, provider-effect, restart, and evidence-generator analysis across every existing file returned by the supplied diff-base command

## Critical findings

### CR-01: An active deletion-command lease is immediately stealable, and stale workers may overwrite branch results

**Files:** `src/stoa/jobs/account_deletion.py:79-99`; `src/stoa/db/repositories/account_deletion_repo.py:836-924`; `src/stoa/services/account_deletion_service.py:1284-1329`

`run_account_deletion_scan` claims a command with an expiry two minutes in the future. `claim_deletion_command` decides whether a running lease is expired using `lease_expires_at < :expiry`, where `:expiry` is that *new future expiry*, rather than comparing the stored expiry with the current time. Almost every currently active lease therefore satisfies the takeover condition as soon as another scanner sees it.

The returned lease owner/version is then discarded. `continue_command` reloads by command ID, and `persist_branch_result` conditions only on generation and `status == running`; it does not require the claim's lease owner or claimed command version. A stolen/stale worker can consequently overwrite a newer worker's cursor, epoch, debt, or completion result. Finalization validates the caller's in-memory branch map, while its transaction checks command version but not the stored branch-result map; branch persistence itself does not advance that version. This can make the two-clean-epoch proof diverge from the durable state used during concurrent execution and can duplicate irreversible provider cleanup.

**Fix:** Pass an explicit `now_epoch` to the claim and compare stored expiry with that value. Return and thread an opaque claim token (lease owner plus version) through the service; condition every branch persist, renewal, and finalization on it. Advance a CAS version with each branch result and validate the durable branch-result digest/set in the final transaction. Add two-worker tests covering an unexpired lease, expired takeover, stale cursor/result writes, and stale finalization.

### CR-02: Missing owner-generation metadata bypasses delivery intents and calls providers directly

**Files:** `src/stoa/services/notification_service.py:747-779,934-965`; `src/stoa/services/websocket_service.py:193-268`

Email digest and push delivery use the fenced `run_delivery_intent` path only when an owner and positive account-fence generation are present. Otherwise they call the email/push provider directly. WebSocket fanout similarly sets `leased = False` for a missing/invalid generation, then posts to matching connections without any account-fence recheck. These are private notification payloads, not the sealed `global_nonprivate` classification.

Legacy, malformed, or partially migrated rows can therefore produce outbound effects after account deletion has installed its permanent fence. The fallback directly contradicts the Phase 473 contract that unresolved private-looking delivery is debt and that every provider mutation is owner/fence/lease bound. It also allows the final deletion scan to race a delivery path it cannot cancel through an intent.

**Fix:** Fail closed for private rows without an authoritative owner and generation. Resolve legacy ownership through an authoritative strongly consistent join before delivery; only a persisted, explicit sealed `global_nonprivate` classification may use a non-owner path. Route all other digest, push, and WebSocket effects through one intent/lease primitive and add deletion-race tests for missing, malformed, and stale generation metadata.

## Warnings

### WR-01: Production deletion audit timestamps default to empty strings

**Files:** `src/stoa/services/account_deletion_service.py:1264-1278,1313-1329`; `src/stoa/jobs/account_deletion.py:76`; `src/stoa/db/repositories/account_deletion_repo.py:913-923,982-1029`

`AccountDeletionService` defaults `self.now` to `lambda: ""`. Both production entry points construct it without injecting a clock. Branch `updated_at`, terminal `completed_at`, receipt completion time, and the permanent fence's `deleted_at`/`updated_at` are therefore blank in production. Tests mostly inject a deterministic clock, hiding the default-path defect.

**Fix:** Default to `datetime.now(UTC).isoformat()` and reject blank or unparsable lifecycle timestamps at the repository boundary. Exercise the production constructor in finalization tests.

### WR-02: Parent-profile scrubbing can overwrite concurrent parent updates

**Files:** `src/stoa/services/account_deletion_service.py:414-433`; `src/stoa/db/repositories/account_deletion_repo.py:595-662`

The account-profile branch deep-copies a parent profile, removes the deleting child, and replaces the entire row. The transaction verifies both account fences, but the row condition checks only that the row exists and still has the same parent user ID. It does not compare a row version or the original image. A concurrent active-parent profile update between scan and `Put` can be silently lost when the stale scrubbed copy wins.

**Fix:** Use a narrow `UpdateExpression` where the schema permits it, or require and increment a row version/original-image digest in the transaction. On conflict, retain branch debt and rescan. Add a concurrent parent preference/profile update test.

### WR-03: Claimed notification delivery intents have no crash-recovery path

**Files:** `src/stoa/services/notification_service.py:115-170`; `src/stoa/db/repositories/notification_repo.py:361-386`

Delivery intents store `lease_expires_at`, but `claim_delivery_intent` accepts only `status == registered`; it never permits takeover of an expired `claimed` intent. If a worker crashes after claim and before completion, replay observes the existing claimed record, fails the registered-only claim, and returns `retryable_claim_conflict` forever. The same operation is never delivered or conclusively terminalized, and the orphaned pending intent can remain account-deletion debt.

**Fix:** Add expired-lease takeover using a comparison against current epoch, with a new owner/token and CAS protection. Preserve the no-blind-retry rule by allowing takeover only while no provider effect could have begun, or introduce an explicit pre-effect state transition that makes ambiguity terminal. Test crashes before the final fence check, immediately before provider invocation, and after provider acceptance.

## Scope

The review covered every existing file returned by:

```text
git diff --name-only fce68392137d1020a378d239c27af1cf9c7fe156^..HEAD -- src scripts
```

The scope contains 5 scripts and 64 source files (69 total). No source file was modified by this review.

---

_Reviewer: Codex using the gsd-code-review workflow_
