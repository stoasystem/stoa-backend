# AI Teacher Tools Contract: v3.7

## Tool Outputs

Initial outputs:

- `session_summary`
- `misconception_summary`
- `suggested_teaching_focus`
- `draft_followup_explanation`
- `practice_exercise_draft`

## Input Sources

- Question content.
- AI answer.
- Teacher replies.
- Conversation context.
- Subject and topic taxonomy.
- Student learning profile seeds.
- Feedback and escalation history.
- Existing tutor assistance summary seeds from v3.5.

## Exercise Draft Shape

Minimum fields:

- `draft_id`
- `student_id`
- `subject`
- `topic_ids`
- `difficulty`: `easy`, `medium`, `hard`
- `exercise_count`
- `items`
- `answer_key`
- `explanations`
- `source_context`
- `prompt_version`
- `status`: `draft`, `accepted`, `rejected`, `archived`
- `created_by`
- `created_at`
- `reviewed_by`
- `reviewed_at`

## Review Lifecycle

- `generate`: create draft content from approved context.
- `regenerate`: create a new version while preserving prior draft metadata.
- `accept`: mark draft as teacher/admin approved.
- `reject`: mark draft unusable with optional reason.
- `archive`: hide draft from active workflow without deleting evidence.

Generated content must not be sent to students or assigned automatically in v3.7.

## Functional Verification Priorities

- Tutor/admin can generate summaries for visible question/session context.
- Tutor/admin can generate bounded exercise drafts by student/subject/topic/difficulty/count.
- Draft lifecycle supports regenerate/accept/reject/archive.
- Student delivery remains a future explicit action.
