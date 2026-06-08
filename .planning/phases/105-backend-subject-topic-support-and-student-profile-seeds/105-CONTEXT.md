# Phase 105 Context

**Phase:** Backend Subject/Topic Support And Student Profile Seeds
**Milestone:** v3.4 Learning Expansion Foundation
**Requirement:** LEARN-02
**Status:** Ready for implementation

## Inputs

- Phase 104 defined the v3.4 learning expansion contract.
- Existing question records already store `subject`, `knowledge_points`, `student_feedback`, `status`, and timestamps.
- Existing practice mistakes store `subject_id` and `topic_id`.
- Existing parent/student APIs already expose summary-style learning data.

## Implementation Boundary

- Reuse existing DynamoDB question and practice access patterns.
- Do not create new tables, indexes, buckets, or workers.
- Preserve existing math behavior.
- Add foundation support for physics, German, and English without claiming full curriculum coverage.

## Decisions

- Centralize subject taxonomy, prompt context, topic seed extraction, and profile aggregation in `learning_profile_service`.
- Add dedicated learning-profile endpoints rather than overloading existing summary responses.
- Keep parent access ownership-checked through `/parents/me/children/{child_id}/learning-profile`.
