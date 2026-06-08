# Learning Expansion Contract: v3.4 Foundation

## Subjects

| Subject ID | Label | Rollout State | Notes |
|------------|-------|---------------|-------|
| `math` | Mathematics | active | Existing MVP behavior remains default. |
| `physics` | Physics | foundation | Subject accepted once backend support exists; content depth remains limited. |
| `german` | German | foundation | Language-learning prompts need separate behavior from STEM prompts. |
| `english` | English | foundation | Language-learning prompts need separate behavior from STEM prompts. |

## Topic Shape

Minimum normalized topic fields:

- `subject`
- `topic_id`
- `label`
- `source`: `ai_response`, `teacher_reply`, `admin_correction`, `profile_seed`
- `confidence`
- `evidence_question_ids`
- `first_seen_at`
- `last_seen_at`

## Student Profile Seed

Minimum aggregate fields:

- `student_id`
- `subject_activity`: question count, feedback average, teacher escalation count
- `weak_topics`: topic id, label, subject, count, latest evidence
- `strength_topics`: optional, future-safe
- `updated_at`

## Prompt Contract

- Math and physics prompts should keep step-by-step explanation behavior.
- German and English prompts should emphasize language learning, correction, and explanation rather than solving numeric problems.
- All subjects should preserve the existing “guide understanding, do not simply give final answers” product behavior.
- Full curriculum coverage and exercise generation are future scope.

## Functional Verification Priorities

- Existing math question submission still works.
- New subject identifiers are validated predictably.
- Prompt context differs by subject where implementation uses AI.
- Student/profile summaries can aggregate subject/topic seeds from real question data.
- Parent/student UI labels foundation subjects without claiming a full curriculum rollout.
