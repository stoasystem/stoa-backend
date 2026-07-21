# Phase 475: Existing Pattern Map

**Mapped:** 2026-07-21
**Purpose:** Bind each planned change to the closest current implementation and test analog.

## Pattern Summary

| Phase 475 responsibility | Closest reusable analog | Reuse rule |
|--------------------------|-------------------------|------------|
| Durable question command + quota claim | `attachment_repo.claim_message_command_and_quota()` and `tests/test_phase473_message_command.py` | Copy the command fingerprint/disposition/strong-reread model, but use question-specific keys and the question quota/ledger contract. |
| Composed question/attachment transaction | `attachment_repo.build_question_attachment_transaction()` and `attachment_service.commit_question_with_attachment()` | Expose/compose transaction operations; do not reimplement attachment ownership, storage quota, or fence conditions in the route. |
| Typed transaction boundary | `account_deletion_repo.transact()` plus repository-specific conflict wrappers | Keep conditional/business conflict distinct from dependency failure; do not collapse both to `AccountDeletionConflict` at the route boundary. |
| Teacher claim/session | `question_repo.update_status_conditionally()` and deterministic command patterns | Use one conditional question transition and one deterministic session row in the same transaction. |
| Exactly-once takeover notification | Delivery-intent command/lease patterns in `notification_repo.py` | Persist a deterministic effect identity from the winning claim and replay it; a loser never emits an effect. |
| Bidirectional relationship write | Current `user_repo.put_parent_student_binding()` | Retain its two formal rows/account fence and add conflict conditions plus required profile projection to the same transaction. |
| Preview/apply repair | Privileged identity reconciliation and Phase 472 dry-run-first administration | Preview returns bounded classifications and observed versions; apply rechecks coordinates and never elevates or overwrites conflicts. |
| Profile CAS | `account_deletion_repo.scrub_parent_profile_child()` and `test_parent_scrub_is_version_cas_and_never_replaces_concurrent_preferences` | Make ordinary writers increment the same version so the existing scrub CAS becomes real end-to-end concurrency control. |
| Capped logical usage | Message command quota-operation rows | Pair an operation row with a conditional counter update; same operation replays and a rejected new operation leaves the counter unchanged. |
| Practice answer projection | `practice_repo.put_attempt()` and `practice_projection_service.build_attempt_result()` | Add bounded normalization/schema metadata and explicit legacy unknown; preserve answer-free preview separation. |
| Delivery failure taxonomy | `notification_repo` delivery claims and recovery states | Return/raise typed outcomes for proven deletion, claim loss, and dependency retry before service routing. |
| Terminal deletion replay | `account_deletion_repo.finalize_account_deletion()` stored `receipt` | Treat the stored receipt as authoritative and avoid scheduling continuation for terminal replay. |

## Files And Closest Analogs

### Question admission

- Modify `src/stoa/db/repositories/question_repo.py` for question command keys, transaction operation construction, disposition, and strong replay reads.
- Modify `src/stoa/services/usage_ledger_service.py` only for canonical event/item construction and reconciliation semantics; keep raw content out of ledger metadata.
- Modify `src/stoa/routers/questions.py` to orchestrate prepare → atomic admission → processing/final projection. Keep OCR/AI outside the transaction.
- Reuse `src/stoa/db/repositories/attachment_repo.py` transaction operations rather than duplicating attachment lifecycle logic.
- Add focused tests alongside `tests/test_questions.py`, `tests/test_usage_ledger.py`, and a new lower-bound transaction/failure module if needed.

### Teacher takeover

- Modify `src/stoa/db/repositories/question_repo.py` for one claim/session transaction and deterministic claim/session IDs.
- Modify `src/stoa/routers/teachers.py` to consume typed claim results and emit a structured deterministic 409 for losers.
- Modify `src/stoa/services/notification_service.py` only to enqueue/replay the deterministic winning takeover effect.
- Extend `tests/test_teacher_dispatch.py` with a real barrier and lower-bound final-state assertions; retain `tests/test_teacher_reply_sla.py` for SLA-field regression.

### Relationships and profile versioning

- Modify `src/stoa/db/repositories/user_repo.py` for composed binding/profile operations and a shared profile version increment contract.
- Modify `src/stoa/routers/admin.py` for separate preview/apply repair contracts; authorization remains capability-scoped through the existing admin target provider.
- Extend `tests/test_admin_authorization.py` for the real repair route and `tests/test_student_authorization_matrix.py`/`tests/test_parent_children.py` for fail-closed asymmetric authorization.
- Extend `tests/test_phase473_account_deletion_claim_fencing.py` using the real locale/preference writer instead of a synthetic version mutation.

### Rate, practice, delivery, deletion

- Modify `src/stoa/services/rate_limit.py` and its chat/hint call sites using the message-command quota-operation approach.
- Modify `src/stoa/db/repositories/practice_repo.py`, `src/stoa/services/practice_projection_service.py`, and `src/stoa/models/practice.py` narrowly; do not change answer reveal timing.
- Modify `src/stoa/db/repositories/notification_repo.py` and `src/stoa/services/notification_service.py` together for typed delivery-begin outcomes.
- Modify `src/stoa/services/account_deletion_service.py`, `src/stoa/deps.py`, and `src/stoa/routers/auth.py` narrowly for stored terminal receipt replay and no background rescheduling.

## Test Construction Rules

- Use captured transaction operation lists for exact condition/key assertions.
- Use `TransactionCanceledException.CancellationReasons` only internally; redact raw provider messages and item coordinates from public outcomes.
- For concurrency, use a barrier immediately before the transaction, not sequential calls labeled concurrent.
- For ambiguous timeouts, the fake must optionally apply the transaction before raising, then a strong read must distinguish committed from retryable.
- Every replay assertion includes a side-effect counter proving zero additional writes/provider calls.
- Every reconciliation apply test runs twice and proves the second execution performs zero mutations.

## Anti-Patterns To Avoid

- Route-level sequences of independent repository writes for one logical admission/claim/binding.
- `ClientRequestToken` as the sole idempotency store.
- Catching all conditional/dependency failures as deletion or quota conflict.
- Whole-profile replacement for a narrow relationship or privacy update.
- Random IDs regenerated on retry for session, command, ledger, or notification effects.
- Tests that mock the repository method whose transaction/condition behavior is the requirement under test.
- Any Phase 475 plan touching `mobile/` or native-client code.

---

*Phase: 475-Transactional Usage Assignment And Relationship Consistency*
