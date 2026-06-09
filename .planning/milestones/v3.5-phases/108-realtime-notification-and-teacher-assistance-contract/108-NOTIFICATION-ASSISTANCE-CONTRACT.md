# Notification And Teacher Assistance Contract: v3.5 Foundation

**Status:** Passed
**Milestone:** v3.5 Realtime And Teacher Assistance Foundation
**Requirement:** NOTIFY-01

## Boundary

v3.5 creates durable in-product notification events and teacher assistance summary seeds. It does not ship WebSocket delivery, push notifications, native mobile notification channels, email digests, automatic exercise generation, or full AI teacher tooling.

## Notification Events

Initial event types:

- `teacher_requested`
- `teacher_takeover`
- `teacher_reply`
- `moderation_case_update`
- `subscription_request_update`
- `learning_profile_update`

Minimum fields:

- `event_id`
- `recipient_id`
- `recipient_role`
- `event_type`
- `target_type`
- `target_id`
- `title`
- `summary`
- `status`: `created`, `read`, `archived`, `failed`
- `created_at`
- `read_at`
- `archived_at`
- `metadata`
- `actor_id` optional
- `actor_role` optional

## Recipient Rules

| Event | Recipients | Target |
|-------|------------|--------|
| `teacher_requested` | Tutors/admins assigned to teacher queue visibility | `question` |
| `teacher_takeover` | Student who owns the question | `question` |
| `teacher_reply` | Student who owns the question | `question` |
| `moderation_case_update` | Admins; reporter when a user-facing status changes | `moderation_case` |
| `subscription_request_update` | Parent who owns the request; admins for new requests | `subscription_request` |
| `learning_profile_update` | Student and linked parent when subject profile evidence changes | `learning_profile` |

Admin/tutor queue-wide events may use role recipients (`recipient_role=admin` or `recipient_role=tutor`) and no user-specific `recipient_id`. User-specific list APIs must return only direct events for the user plus role events for the user's role.

## Delivery And Retention

- v3.5 delivery is pull-based through authenticated APIs.
- WebSocket subscription delivery is a future transport over the same event model.
- Events are retained as product metadata and may be archived by the recipient.
- `read` and `archived` are recipient-local display states, not source workflow status.
- Event creation must be best-effort for existing workflows: notification persistence failures must not break teacher, moderation, subscription, or learning flows.
- Event payloads must contain summaries and identifiers only; no raw private report artifacts, no image S3 keys, and no unreviewed HTML.

## UI Display Rules

- Count `created` events as unread.
- Hide `archived` events by default but keep them listable through a filter later.
- Group events by created date and event type where useful.
- Show transport-neutral copy such as "Notifications" or "Updates"; do not claim realtime delivery.
- Show unavailable states when a summary seed cannot be generated from accessible data.

## Teacher Assistance Summary Seed

Inputs:

- Question content and subject/topic metadata.
- AI response summary.
- Teacher reply history where available.
- Student profile weak-topic seeds.
- Conversation context where available.

Output shape:

- `summary_id`
- `question_id`
- `student_id`
- `subject`
- `student_context_summary`
- `question_summary`
- `ai_answer_summary`
- `weak_topics`
- `suggested_focus`
- `source_count`
- `created_at`

## API Shape

Notifications:

- `GET /notifications`
- `GET /notifications?status=created|read|archived`
- `POST /notifications/{event_id}/read`
- `POST /notifications/{event_id}/archive`

Teacher assistance:

- `GET /tutors/questions/{question_id}/assistance-summary`

Admin:

- `GET /admin/notifications?event_type=...`

## Functional Verification Priorities

- Events are generated for selected existing workflows without changing those workflows.
- Recipients see only their events.
- Users can mark events read/archived.
- Tutors can view a summary seed for an accessible question.
- UI does not claim full WebSocket realtime or automatic exercise generation.
