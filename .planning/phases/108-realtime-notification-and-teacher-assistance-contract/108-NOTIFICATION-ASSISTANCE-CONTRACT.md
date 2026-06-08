# Notification And Teacher Assistance Contract: v3.5 Foundation

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
- `student_context_summary`
- `question_summary`
- `ai_answer_summary`
- `weak_topics`
- `suggested_focus`
- `created_at`

## API Shape

Notifications:

- `GET /notifications`
- `POST /notifications/{event_id}/read`
- `POST /notifications/{event_id}/archive`

Teacher assistance:

- `GET /tutors/questions/{question_id}/assistance-summary`

## Functional Verification Priorities

- Events are generated for selected existing workflows without changing those workflows.
- Recipients see only their events.
- Users can mark events read/archived.
- Tutors can view a summary seed for an accessible question.
- UI does not claim full WebSocket realtime or automatic exercise generation.
