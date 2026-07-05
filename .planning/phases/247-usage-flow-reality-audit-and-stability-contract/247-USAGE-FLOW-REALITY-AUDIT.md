# Phase 247 Usage Flow Reality Audit

## Summary

The current backend has meaningful usage coverage for the major student learning flows introduced through v5.11, but it is not yet a fully closed stability contract. The highest-priority closure work is not a new analytics stack; it is tighter idempotency semantics, explicit partial-failure handling, practice teacher-help coverage, and reconciliation explanations.

## Flow Classification

| Flow | Backend entry | Frontend entry | Current metering | Classification | Evidence |
|------|---------------|----------------|------------------|----------------|----------|
| Question submit | `src/stoa/routers/questions.py` `POST /questions` | Student question/chat surfaces | Atomic `QUESTION#day` counter plus `question_submission` ledger event | Both counter and ledger | `tests/test_questions.py`, `tests/test_usage_ledger.py` |
| Question idempotent retry | `src/stoa/routers/questions.py` | Submit with `idempotencyKey` | Existing ledger lookup returns existing question or 409 without counter increment | Covered retry path | `test_submit_question_idempotent_retry_without_question_does_not_increment_counter` |
| Chat message | `src/stoa/routers/conversations.py` `POST /conversations/{id}/messages` and stream variant | `/Users/zhdeng/stoa-frontend/src/services/chat/chatApi.ts` | `CHAT#day` counter plus `chat_message` ledger event | Both counter and ledger | `tests/test_conversations.py` |
| Conversation teacher help | `src/stoa/routers/conversations.py` `POST /teacher-help/request` | chat teacher-help mutation/API | `conversation_teacher_help_request` ledger event | Ledger-only support-visible | `tests/test_conversations.py` |
| Question teacher help | `src/stoa/routers/questions.py` `POST /questions/{id}/request-teacher` | recent question/escalation surfaces | `question_teacher_help_request` ledger event | Ledger-only support-visible | `tests/test_questions.py` |
| Practice answer | `src/stoa/routers/practice.py` `POST /practice/challenges/{id}/answer` | `/Users/zhdeng/stoa-frontend/src/services/practice/practiceApi.ts` | `practice_answer` ledger event | Ledger-only support-visible | `tests/test_curriculum_analytics.py` |
| Lesson completion | `src/stoa/routers/practice.py` lesson completion route | practice UI/API | `practice_lesson_completion` ledger event | Ledger-only support-visible | `tests/test_curriculum_analytics.py` |
| Hint request | `src/stoa/routers/practice.py` `POST /practice/hints` | practice hint API | `HINT#day` counter plus `hint_request` ledger event | Both counter and ledger | `tests/test_curriculum_analytics.py` |
| Practice teacher help | `src/stoa/routers/practice.py` `POST /practice/teacher-help` | `/Users/zhdeng/stoa-frontend/src/services/practice/practiceApi.ts` | Returns ready response only | Missing ledger coverage | Route inspection |
| Reviewed assignment generation | `src/stoa/services/adaptive_learning_service.py` | tutor/admin assignment flows | `reviewed_assignment_generation` ledger event | Ledger-only support-visible | `tests/test_adaptive_learning.py` |
| Assignment lifecycle | `src/stoa/services/adaptive_learning_service.py` | student/tutor assignment flows | `assignment_started/completed/skipped/archived` ledger events | Ledger-only support-visible | `tests/test_adaptive_learning.py` |
| Curriculum reads | practice/catalog/adaptive read APIs | dashboard/practice/profile pages | No usage event | Intentionally skipped read-only | Route inspection |
| Billing entitlement reads | subscription/account operations APIs | billing/account operations pages | No usage event | Intentionally skipped read-only | Existing v5.13/v5.14 contract |
| Account operations usage visibility | parent/admin account operations services/pages | account operations e2e specs | Reads usage summaries and reconciliation status | Support explanation surface | `tests/test_usage_ledger.py`, frontend e2e fixtures |
| Admin usage summary | admin usage page/API | `/admin/usage` | Operational aggregate read | Future-only for v5.15 smoke | Route/page inspection |

## Consume Rules

- A question consumes quota only after the daily question counter increments.
- A chat message consumes quota only after the chat counter increments and the student/assistant messages are persisted.
- A hint consumes quota only after the hint counter increments and a hint is returned.
- Ledger-only support actions consume support-visible activity only after the target transition or request is accepted.
- Assignment generation should record only reviewed/persisted generation, not previews or failed provider calls.

## Skip Rules

- Read-only curriculum, billing entitlement, usage summary, account operations, history, and dashboard reads do not write usage events.
- Failed not-found, unauthorized, and ownership-mismatch requests do not write usage events.
- Counter-rejected quota attempts do not write ledger rows.
- Duplicate question retries with a matching existing ledger row should not increment counters.
- Provider-blocked live smoke and external provider activations remain externally blocked and do not become local usage events.
- Dry-runs, previews, and admin inspection paths are non-consuming unless a later phase defines an explicit operational audit event.

## Stability Gaps

1. Question submit writes the ledger after the counter increment but before the question item is persisted. If item persistence fails, support sees counter plus ledger with no question row. Phase 248 should either make this ordering explicit and test the partial state, or move to a safer idempotency model without double-charging retries.
2. Chat and hint counters increment before the full route completes. Their current tests cover successful ledger calls, but not partial failures between counter increment, persistence, provider response, and ledger write.
3. Generic rate-limit counters increment then reject when `new_count > limit`, which can leave over-limit attempts counted. Phase 249 reconciliation should classify over-limit counter drift instead of treating it as matched consumption.
4. Practice teacher-help has a frontend/backend endpoint but no usage ledger event. Phase 248 should add a governed support-visible event or document it as a non-real placeholder.
5. Duplicate idempotency currently relies on explicit request keys for question submit and resource-derived keys for non-question actions. Mismatched duplicate intent is not uniformly detected.
6. Account operations explanations can show unreconciled usage, but Phase 249 still needs a sharper support action for matched, drifted, stale, partial, over-limit, and no-usage states.
7. v5.14 focused frontend e2e remains blocked by execution approval and should stay visible through the v5.15 release gate.

## Phase 248-250 Priorities

- Phase 248: add practice teacher-help ledger coverage or explicit skip evidence; add partial-failure and duplicate-intent tests for question/chat/hint; preserve metadata privacy.
- Phase 249: expand reconciliation statuses for over-limit, stale, partial, no-usage, and support action explanations across counters, ledger, entitlements, and account operations summaries.
- Phase 250: add deterministic product smoke checks for auth, entitlement, curriculum read, question submit, teacher help, and admin/account support surfaces; classify expected auth/provider blocks separately from regressions.

## Out Of Scope

- Warehouse/BI deployment.
- External APM rollout.
- Live Stripe/TWINT, Cognito/email, notification, or support-provider activation.
- Raw prompts, answers, message bodies, verification codes, tokens, private artifact keys, or provider payloads in usage/support evidence.
