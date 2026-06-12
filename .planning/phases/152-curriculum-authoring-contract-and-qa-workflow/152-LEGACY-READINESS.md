# Legacy Readiness And Compatibility Rules

**Phase:** 152 - Curriculum Authoring Contract And QA Workflow
**Status:** Accepted

## Current Compatibility Surface

The existing curriculum surface is already used by student, tutor, parent, and adaptive-learning flows. Phase 153 must preserve these behaviors while adding authoring.

| Surface | Current source | Compatibility rule |
|---------|----------------|--------------------|
| Curriculum catalog | `curriculum_service.list_catalog` over `practice_repo` | Defaults to active/published content only. |
| Lesson detail | `curriculum_service.get_lesson_detail` | Answer keys are role-gated and hidden from students. |
| Exercise list | `curriculum_service.list_exercises` | Draft/review content is hidden unless preview is authorized. |
| Progress summary | `curriculum_service.get_progress_summary` | Continues reading existing progress/mistake rows by public IDs. |
| Practice lesson routes | `src/stoa/routers/practice.py` | Public lesson IDs remain stable and existing route shape remains valid. |
| Adaptive assignment from curriculum | `adaptive_learning_service._assignment_source` | `curriculum_exercise` lookup remains compatible with existing `challenge_id` records. |
| Assignment progress | `adaptive_learning_service._record_assignment_progress` | Completion/mistake recording continues using public lesson/exercise IDs. |

## Published Projection Requirements

Phase 153 may introduce new authoring rows, but published content must still be projectable into the field shape expected by current reads:

- lesson: `lesson_id`, `subject_id`, `topic_id`, `unit_id`, `title`, `objective`/`description`, `difficulty`, `estimated_minutes`, `rollout_state`;
- exercise/challenge: `challenge_id` or compatible `exercise_id`, `lesson_id`, `subject_id`, `topic_id`, `prompt`, `type`, `difficulty`, `order`, `answer_key`/`correct_answer`, `explanation`;
- topic/unit/subject bindings remain compatible with existing catalog sorting and filtering.

## Preview Boundary

Existing preview behavior can remain for admin/tutor/teacher roles. It must not become a shortcut for student or parent draft access.

Required guardrails:

- Default reads return published content only.
- `includePreview=true` requires an admin/tutor/teacher role.
- Requesting a non-active rollout state requires the same preview authorization.
- Student and parent responses do not include draft/review content or answer keys.

## Legacy Content Readiness Checklist

Before a legacy lesson/exercise can be imported or republished through the authoring flow:

- Public IDs are normalized and collision-checked.
- Required lesson and exercise fields can populate current API responses.
- Answer keys exist for gradable exercises.
- Locale/language metadata is either explicit or safely inferred.
- Subject aliases are normalized consistently with current catalog behavior.
- Existing assignments or progress rows referencing the content remain interpretable.
- Archive/rollback behavior is defined if the content already has historical usage.

## Tests Phase 153 Must Keep Green

- `tests/test_curriculum_rollout.py`
- `tests/test_adaptive_learning.py`

Phase 153 should add focused authoring tests without weakening these compatibility tests.

