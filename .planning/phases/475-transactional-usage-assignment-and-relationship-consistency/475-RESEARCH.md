# Phase 475: Transactional Usage Assignment And Relationship Consistency - Research

**Researched:** 2026-07-21
**Domain:** DynamoDB transaction boundaries, durable idempotency, concurrency control, reconciliation, and terminal replay
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

The planner and executor must preserve all decisions D-01 through D-16 in `475-CONTEXT.md`. The most consequential constraints are:

- An ambiguous question submission is a durable, visible `processing` outcome, not a false terminal failure. Same-request replay returns the original result without another question, quota charge, ledger event, or upload.
- A proven terminal question failure restores question allowance and reverses the ledger while retaining successfully uploaded attachments as reusable storage-quota-bearing resources.
- Teacher takeover has one atomic winner, no loser side effects, one session, one notification, and recoverable winner-owned follow-up effects.
- Parent access remains denied unless the active forward and reverse relationship rows agree. Conflicting histories require administrator choice; reconciliation is preview-first, version-safe, and idempotent.
- Rate limits count one admitted logical request once; rejected and same-operation retried requests do not increase the counter.
- Legacy missing practice answers are explicit unknowns; transient delivery-begin dependency failures remain retryable; completed deletion replay returns the stored terminal receipt.
- Work is backend-only and Web-first. Do not introduce Expo, iOS, Android, or native-client tasks.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Required outcome | Primary code boundary |
|----|------------------|-----------------------|
| V9DATA-01 | Question quota, ledger, upload consumption, idempotency, and initial question persistence commit or converge as one logical command. | `routers/questions.py`, `question_repo.py`, `usage_ledger_*`, `attachment_*` |
| V9DATA-02 | One concurrent teacher-takeover winner, session, and notification. | `routers/teachers.py`, `question_repo.py`, `notification_service.py` |
| V9DATA-03 | Bidirectional parent binding is atomic; historical asymmetry repair is safe and idempotent. | `user_repo.py`, `routers/admin.py`, authorization relationship reads |
| V9DATA-04 | Rejected rate attempts do not inflate counters; admitted-operation retry is idempotent. | `services/rate_limit.py`, chat/hint call sites |
| V9DATA-05 | Wrong submitted answer round-trips safely; legacy absence is unknown. | `practice_repo.py`, `practice_projection_service.py`, `routers/practice.py` |
| V9DATA-06 | Ordinary parent profile writers and child scrub cannot lose unrelated concurrent values. | `user_repo.py`, `account_deletion_repo.py`, deletion branch |
| V9DATA-07 | Delivery-begin distinguishes conditional ownership loss from transient dependency failure. | `notification_repo.py`, `notification_service.py` |
| V9DATA-08 | Identical completed deletion retry returns the stored deleted receipt without cleanup effects. | `deps.py`, `account_deletion_service.py`, `account_deletion_repo.py`, `routers/auth.py` |

</phase_requirements>

## Executive Summary

The repository already contains most primitives needed for Phase 475: a shared DynamoDB transaction adapter, account-fence conditions, immutable command patterns, deterministic usage identities, attachment transaction builders, conditional status updates, delivery-intent leases, and a terminal deletion receipt. The main problem is that the affected routes do not compose these primitives into one domain outcome, or collapse distinct conditional and dependency failures into the same business result.

The safest design is not one universal transaction spanning the whole phase. Each user command needs its own smallest correctness boundary:

1. **Question admission transaction:** one durable command row/payload digest, capped quota update, ledger event, initial question row, active account fence, and attachment association/consumption operations. Expensive OCR/AI remain outside admission; their existing recoverable states continue after the question exists.
2. **Teacher claim transaction:** conditional question transition plus deterministic session and takeover-effect identity. Notification delivery is a recoverable effect keyed to the successful claim, not an independent route side effect.
3. **Relationship transaction:** forward row, reverse row, and required narrow profile link update in one conditional transaction. Historical repair produces a version-bound preview and applies only unambiguous rows that still match the preview.
4. **Single-item conditional protocols:** capped/idempotent rate admission, profile version increments, typed delivery-begin outcomes, bounded answer normalization, and terminal receipt projection.

DynamoDB `TransactWriteItems` is atomic across up to 100 actions, but it cannot contain two actions targeting the same item. Therefore a counter's limit condition and increment must be expressed in the same `Update`, and a profile CAS and field changes must also be one `Update`. A `ClientRequestToken` is helpful only as a transport optimization because its idempotency window is ten minutes; Phase 475 requires durable application command rows and payload digests for retries over the product's full retention period.

## Current-State Findings

### 1. Question admission remains deliberately non-atomic

- `submit_question()` currently reserves an attachment, increments the question counter, performs OCR, writes the usage ledger, then writes the question/attachment transaction.
- `record_question_usage_event()` still declares `write_order="counter_then_ledger"`.
- If the question write fails, the existing test `test_submit_question_persistence_failure_leaves_counter_and_ledger_for_reconciliation` proves the partial state instead of convergence.
- Existing replay checks read the ledger first. A ledger row without a question returns a generic 409, so it cannot represent the selected visible processing/recovery contract.
- `attachment_service.commit_question_with_attachment()` already composes the question row with fenced attachment operations. Phase 475 should expose/reuse those transaction operations so quota, ledger, command, question, and attachment state share one commit.
- OCR and AI provider calls must not be placed inside a DynamoDB transaction. Attachment validation/promotion is already completed before question association; AI response remains a later status transition.

**Planning consequence:** separate “admission transaction,” “route/replay projection,” and “historical reconciliation” into three small plans. Do not combine them with AI answer generation.

### 2. Teacher takeover is a read-then-three-write sequence

- `teachers.takeover()` reads authorized question state, generates a random session ID, calls `question_repo.update_status()`, calls `create_teacher_session()`, then emits a notification.
- `question_repo.update_status_conditionally()` and fenced transaction helpers already exist, but takeover does not use them.
- Random session identity complicates lost-response replay. Derive a stable claim/session/effect identity from the question and durable winning claim, or persist it in the atomic claim and always replay it.
- `emit_teacher_takeover()` should become an idempotent effect producer keyed to the claim rather than a fire-and-forget call with no durable uniqueness boundary.

**Planning consequence:** first establish one claim/session transaction and deterministic 409 classification; then add a separate recovery plan for exactly-one notification and winner replay.

### 3. Parent binding rows are transactional, but the required profile link is not

- `put_parent_student_binding()` now writes forward and reverse rows in one transaction behind the student account fence.
- `repair_parent_binding()` first calls `update_student_parent_link()` and then calls `put_parent_student_binding()`. Failure between those calls still leaves the legacy profile projection and formal relationship rows inconsistent.
- The current binding puts are unconditional and can overwrite a conflicting parent relationship unless the composed transaction adds exact identity/version conditions.
- Strict authorization already reads both formal directions, so one-sided rows remain denied; this must not change during repair.
- Existing admin repair is immediate mutation. It needs a preview model that classifies normal, repairable, conflict, and changed/skipped entries, plus an apply operation bound to observed versions/digests.

**Planning consequence:** one plan composes the profile projection and both formal rows; a separate plan implements preview/apply reconciliation and its admin contract.

### 4. Profile scrub CAS is only half of the concurrency protocol

- Phase 473 added `scrub_parent_profile_child()` with an expected row version, and tests prove stale scrub rejection using a fake concurrently incremented profile.
- Ordinary writers call `update_profile_fields()` with only an active account-fence condition. They do not consistently condition on and increment the profile row's `version`.
- Therefore the Phase 473 race test demonstrates the scrub algorithm, but not a real ordinary-writer-versus-scrub race.

**Planning consequence:** inventory every shared `USER#{id}/PROFILE` writer, route them through one version increment/CAS contract or a proven narrow update, then race the real locale/preference writer against the real scrub. This is distinct from relationship repair.

### 5. Rate counters need both a cap and a durable logical-operation identity

- `_increment_and_check()` uses unconditional `ADD count :one` and only rejects after reading a value greater than the limit.
- A condition such as `attribute_not_exists(count) OR count < :limit` prevents rejected requests from changing the counter.
- A cap alone does not make provider retry idempotent. One operation record must be created atomically with the counter increment (or the counter row must hold a bounded operation identity strategy) so the same admitted request replays without increment.
- Chat and hint call sites need an operation identity that survives network/provider retries. Do not use `challenge_id` alone for hints because multiple distinct hint requests may target the same challenge.

**Planning consequence:** one focused plan owns the admission record, cap, typed result, and focused chat/hint call-site migration.

### 6. Practice persistence is partially fixed but lacks the complete public legacy contract

- `put_attempt()` already stores both `student_answer` and `submitted_answer`; `record_attempt()` forwards the answer.
- Current storage accepts arbitrary `Any` without an explicit serialized byte/shape bound or schema version.
- `get_mistakes()` merges current attempts and legacy mistake rows. Public projections still need one explicit sentinel/nullable contract for a genuinely absent historical answer instead of `""`.
- Existing Phase 473 snapshot tests are the closest analog and must remain answer-reveal safe.

**Planning consequence:** this is a small normalization/projection plan, not a rewrite of practice attempts.

### 7. Delivery begin conflates conditional loss with dependency failure

- `notification_repo.begin_delivery_effect()` can raise `AccountDeletionConflict` for scope mismatch, fence/conditional loss, malformed state, and some dependency failures.
- `run_delivery_intent()` catches that broad type and immediately calls `cancel_delivery_intent()`, returning `canceled_account_deletion`.
- The selected contract requires a typed repository result/exception taxonomy: proven deleted fence, conditional claim/scope loss, and retryable dependency failure must remain distinct.
- Existing `tests/test_phase473_delivery_intent_recovery.py` provides the lease and exactly-once recovery harness; extend it with an injected nonconditional failure below transaction begin followed by a healthy retry.

**Planning consequence:** keep repository classification and service routing in one focused plan because neither is correct independently.

### 8. Terminal deletion data already stores the desired receipt

- Finalization persists `status="complete"` and a nested `receipt` containing `command_id`, `status="deleted"`, and `completed_at`.
- `begin_or_replay_deletion()` currently synthesizes a `DeletionReceipt` from top-level command fields and returns the original `accepted_at`, ignoring the stored terminal receipt shape.
- `get_deletion_command()` first tries the active identity binding, then `find_deletion_command_for_identity()`, which is the required post-profile-deletion lookup path.
- The endpoint always schedules `continue_deletion_command()` even when the dependency returned a terminal deleted receipt.

**Planning consequence:** one plan projects and validates the stored terminal receipt through the real dependency and endpoint and suppresses background cleanup for terminal replay.

## Recommended Architecture

### Durable command identity

Every retry-sensitive operation should use:

- a server-owned domain prefix;
- verified actor/resource identity;
- a caller idempotency key or stable business operation ID;
- a canonical payload digest covering exact content and ordered resource identities;
- an immutable created/accepted result identity;
- explicit state (`processing`, `committed`, `reversed`, `terminal_failed` as applicable);
- a version/lease only when recovery work can be taken over.

Do not use a random result ID as the idempotency key. Do not rely on the AWS transaction token after ten minutes. A changed payload under the same application key is a deterministic mismatch, not a new attempt.

### Failure classification

Repository code should classify:

| Outcome | Meaning | External action |
|---------|---------|-----------------|
| `duplicate_same` | Existing command has the same payload digest | Return original processing/final result |
| `duplicate_mismatch` | Same identity, different payload digest | Structured 409; create a new submission identity |
| `business_conflict` | Quota full, teacher already claimed, binding conflicts | Deterministic bounded 409/429/action |
| `conditional_retry` | Version/lease changed and a fresh read may converge | Re-read original command/resource; never terminalize blindly |
| `dependency_retry` | Throttle, timeout, malformed dependency response | Preserve recoverable state and retry later |
| `proven_terminal` | Deletion or validated terminal failure is durable | Return/cancel using stored terminal evidence |

Never classify a transaction cancellation solely from a broad exception class. Inspect the operation position/cancellation reason where available, or perform a strong read of the authoritative state before emitting a terminal business outcome.

### Reconciliation safety

- Preview must be a pure read that emits bounded opaque coordinates, observed versions/digests, classification, and proposed action.
- Apply must re-read or condition on every observed coordinate. If it changed, report `skipped_changed`; do not overwrite.
- Auto-apply only one-sided, unambiguous relationships whose other endpoint/profile agrees with the same parent/student identity.
- Conflicting identities are report-only until an administrator supplies an explicit corrected target.
- Re-running preview/apply after success must report already consistent and perform zero writes.

## Testing Strategy

### Deterministic test layers

1. **Transaction-shape unit tests:** capture operation arrays and assert keys, conditions, digests, version increments, and account-fence operations.
2. **Expression/fake-table behavior tests:** execute the repository against focused in-memory tables that enforce conditional semantics.
3. **Barrier concurrency tests:** synchronize two workers immediately before the competing transaction; assert one winner and exact final rows/effects.
4. **Failure-injection matrices:** fail before commit, return an ambiguous timeout after commit, fail each recoverable effect, then retry using the same identity.
5. **Route projection tests:** assert structured API status/code/action and the selected friendly-state semantics without exposing owner/provider details.
6. **Phase integration gate:** run all focused Phase 475 tests together under Phase 474's authoritative backend gate and generate source-bound evidence.

### Mandatory cases by requirement

| Requirement | Minimum proof |
|-------------|---------------|
| V9DATA-01 | Failure at every transaction boundary; concurrent same key; changed-payload conflict; timeout-after-commit replay; processing-to-final; terminal reversal; attachment retained; historical repair preview/apply/replay. |
| V9DATA-02 | Two barrier-synchronized teachers; one 200, one deterministic 409; one owner/session/notification; winner retry; failure after claim followed by effect recovery. |
| V9DATA-03 | No half-write; duplicate identical binding; conflicting parent preserved/denied; preview-only zero writes; changed-after-preview skipped; repeated apply zero additional writes. |
| V9DATA-04 | Repeated 429 stays exactly at limit; concurrent final slot; same-operation provider retry no increment; distinct operation rejected; UTC day boundary. |
| V9DATA-05 | Scalar/list/Unicode round trip; bounded oversize policy; legacy absent answer explicit unknown; correct answer never substituted. |
| V9DATA-06 | Real locale/preference writer races real child scrub; unrelated bytes preserved; same-sensitive-field scrub wins; stale writer/scrub retries safely. |
| V9DATA-07 | Conditional claim loss is retry/conflict; proven deleted fence cancels; injected dependency failure remains recoverable; healthy retry delivers/reserves/completes once. |
| V9DATA-08 | Real `DELETE /auth/me` terminal replay returns stored receipt; zero new branch/cleanup/background calls; changed identity/fingerprint remains conflict. |

## Validation Architecture

Nyquist artifact generation is disabled by the current project research configuration, so no separate `475-VALIDATION.md` should be required for this run. Plans must nevertheless include the following executable gates:

- Focused tests added by each atomic plan run immediately in that plan.
- A final Phase 475 integration plan runs all Phase 475 tests plus the nearest inherited regression files.
- `ruff check` and targeted mypy run on every changed runtime module.
- The final evidence command must use Phase 474's authoritative verification entry point or its documented focused-test extension; a standalone ad-hoc passing pytest run is supporting evidence, not release evidence.
- No plan may claim live AWS mutation. DynamoDB behavior is proven by deterministic transaction/failure/concurrency tests unless an explicitly approved nonproduction integration environment is later supplied.

## Plan Decomposition Recommendation

The user's “one plan, one thing” constraint should produce thirteen small plans:

1. Question admission transaction primitive.
2. Question route processing/replay projection.
3. Question historical reconciliation and terminal reversal.
4. Teacher atomic claim/session.
5. Teacher notification/effect recovery.
6. Atomic parent binding/profile projection.
7. Parent binding preview/apply reconciliation.
8. Shared profile version/CAS protocol and real scrub race.
9. Capped idempotent rate admission.
10. Bounded practice answer and legacy-unknown projection.
11. Typed delivery-begin outcomes and healthy retry.
12. Completed deletion receipt replay.
13. Phase-wide integrated evidence and source coverage.

Each plan should contain one implementation task (including its focused tests) and avoid mixing unrelated requirements merely to reduce plan count.

## Sources

### Project sources

- `.planning/phases/475-transactional-usage-assignment-and-relationship-consistency/475-CONTEXT.md`
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `docs/audit/full-project-audit.md`
- `docs/audit/findings.json`
- Runtime and test files named throughout this document.

### Primary platform references

- [AWS DynamoDB `TransactWriteItems` API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html) — atomic action bundle, conditions, same-item restriction, limits, and client request token.
- [AWS DynamoDB transactions guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html) — transaction behavior, conflicts, capacity, and recommended transaction sizing.
- [AWS DynamoDB item/conditional-write guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html) — unconditional atomic counters are not idempotent; conditional writes are required where overcount is unacceptable.
- [Botocore `TransactionCanceledException`](https://docs.aws.amazon.com/botocore/latest/reference/services/dynamodb/client/exceptions/TransactionCanceledException.html) — ordered cancellation reasons used for typed outcome classification.

---

*Phase: 475-Transactional Usage Assignment And Relationship Consistency*
*Research completed: 2026-07-21*
