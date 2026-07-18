---
phase: 473-student-content-privacy-and-practice-integrity
reviewed: 2026-07-18T16:55:51Z
depth: standard
diff_base: 401a68f
head: 37bad48dcef555238f7e8eaf199a3462bed001b7
files_reviewed: 9
severity:
  critical: 0
  warning: 4
  info: 0
  total: 4
status: issues_found
---

# Phase 473 Post-Gap Code Review

## Summary

The deterministic nine-file `src`/`scripts` scope was reviewed at standard depth after Plans 473-36 through 473-40. Prior findings CR-01, CR-02, WR-01, and WR-03 are closed in the production call chains. WR-02 is only partially fixed: the scrub now checks a row version, but ordinary profile writers never advance that version, so the original lost-update race remains. The review also found two account/delivery replay defects and a final evidence-verification defect.

Verification performed:

- `.venv/bin/python -m pytest -q` — **2,009 passed**
- `.venv/bin/ruff check <all 9 scoped Python files>` — **all checks passed**
- Both Phase 473 inventory generators with `--check` — **passed**
- `git diff --check 401a68f..HEAD -- src scripts` — **passed**
- `verify-publication --candidate b43c71b...` from current HEAD — **failed** because HEAD is no longer the publication commit's direct child

## Prior-finding closure

| Finding | Result | Evidence |
| --- | --- | --- |
| CR-01 deletion lease theft/stale branch writes | Closed | Claim takeover compares against explicit current epoch; renewal, branch persistence, and finalization carry owner/version/digest CAS state. |
| CR-02 direct notification provider fallback | Closed | Digest, push, and WebSocket now strongly load persisted events and route permitted effects through the intent begin transition. |
| WR-01 blank production deletion timestamps | Closed | The service defaults to timezone-aware UTC and deletion persistence validates lifecycle timestamps. |
| WR-02 stale full-row parent scrub | **Not closed** | The scrub checks `version`, but active profile writers do not increment it. |
| WR-03 unrecoverable claimed delivery intent | Closed | Expired `claimed_pre_effect` work is recoverable; `effect_inflight` is terminalized unknown without blind retry. |

## Warnings

### WR-01: Parent-profile scrub CAS does not observe normal concurrent profile updates

**Files:** `src/stoa/db/repositories/account_deletion_repo.py:690-784`; downstream call chain `src/stoa/db/repositories/user_repo.py:52-158`

`scrub_parent_profile_child` now conditions its full-row replacement on the scanned profile's `version`. However, normal active-profile mutations—including locale, teacher availability, email verification, and parent-link updates—use `update_profile_fields`, whose transaction neither checks nor increments `version`. A concurrent update can therefore change unrelated parent fields while leaving the version unchanged; the deletion scrub's stale full-row `Put` still satisfies `#version=:expected_version` and overwrites those changes.

The focused race test simulates a concurrent writer that advances the version, so it proves only cooperation by a version-aware writer, not the actual production writer chain.

**Fix:** Make every profile mutation participate in one version CAS/increment contract, or change the deletion scrub to a genuinely narrow conditional update that never replaces unrelated fields. Add a race through real `user_repo.update_profile_fields` and prove the concurrent locale/preference bytes survive.

### WR-02: A transient delivery-begin dependency failure is permanently mislabeled as account deletion

**Files:** `src/stoa/db/repositories/notification_repo.py:275-283,807-920`; `src/stoa/db/repositories/account_deletion_repo.py:1506-1527`; `src/stoa/services/notification_service.py:529-542`

`account_deletion_repo.transact` maps both conditional transaction cancellation and nonconditional DynamoDB dependency failure to the same `AccountDeletionConflict` base type. `_delivery_conditional_loss` then returns `True` for every `AccountDeletionConflict`. Consequently, a network/service failure during `begin_delivery_effect` is converted to “delivery begin claim lost”; the service attempts `cancel_delivery_intent` and, if that write succeeds, permanently records `canceled_account_deletion` even though the account fence remained active.

This violates the Plan 37 requirement to map only typed conditional loss and propagate dependency failure as retryable. It can permanently suppress a valid digest, push, or WebSocket operation and publishes the wrong terminal reason.

**Fix:** Preserve separate typed conditional and dependency outcomes through `transact`. Only a verified fence/claim loss may cancel as account deletion; transient dependency failure must leave `claimed_pre_effect` recoverable and return a retryable dependency status. Test a nonconditional `ClientError` below `transact_write_items` followed by a healthy retry.

### WR-03: Completed account deletion cannot replay its promised receipt

**Files:** `src/stoa/db/repositories/account_deletion_repo.py:1254-1435`; `src/stoa/services/account_deletion_service.py:285-349`

The finalizer replaces the command with a minimized terminal row that omits `branch_ids` and `branch_contracts`. A later identical `DELETE /auth/me` resolves the completed command, but `begin_or_replay_deletion` requires both omitted fields to equal the current sealed registry. The immutable comparison therefore raises `deletion replay conflict` instead of returning the stored `deleted` receipt.

This affects the exact lost-response/idempotent replay contract: deletion completes safely, but a client that did not receive the final response cannot retrieve the terminal receipt through the documented endpoint.

**Fix:** Either retain the sealed branch IDs/contracts in the terminal row or use a distinct terminal replay validation based on the retained inventory digest, identity hashes, fingerprint, generation, and receipt. Add an end-to-end replay test that finalizes through the real terminal projection and invokes `begin_or_replay_deletion` again.

### WR-04: Published evidence cannot be independently reverified from the final Phase 473 HEAD

**File:** `scripts/verify_phase473_evidence.py:1092-1102`

Clean `verify-publication` requires the current `HEAD^` to equal the captured candidate and the candidate-to-HEAD diff to contain exactly four publication files. That was true at publication commit `5da6936`, but Plan 40 then added metadata commit `37bad48`. From the final Phase 473 HEAD, the documented verifier now fails immediately with `publication must be a clean direct candidate child`, even though the evidence files are unchanged.

This makes the published evidence dependent on checking out a historical commit, while the CLI has no argument for the publication commit and reads artifacts from the current worktree. The summary's claim that the result is ready for independent aggregate verification is therefore not reproducible in the delivered repository state.

**Fix:** Accept and verify an explicit publication commit: require it to be the candidate's single direct child, read all four artifacts from that commit's Git blobs, and separately prove the current HEAD descends from it without modifying those blobs. Add a regression with one or more later metadata commits.

## Scope

Reviewed every existing file returned by:

```text
git diff --name-only 401a68f..HEAD -- src scripts
```

The nine files are the two inventory generators, evidence verifier, account-deletion repository/job/service, notification repository/service, and WebSocket service. Cross-file callers were inspected where necessary to validate the changed contracts. No source file was modified by this review.

---

_Reviewer: Codex using the gsd-code-review workflow_
