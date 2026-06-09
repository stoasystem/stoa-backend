# Adaptive Memory And Assignment Contract: v4.0

## Memory Scope

Durable memory records are created per student with subject/topic-level evidence.

Minimum memory fields:

- `student_id`
- `subject`
- `topic_id`
- `strengths`
- `weak_topics`
- `mastered_concepts`
- `struggling_concepts`
- `preferred_explanation_style`
- `recent_questions`
- `recent_curriculum_progress`
- `recent_exercise_attempts`
- `teacher_notes`
- `recommended_next_steps`
- `freshness`
- `last_updated_at`

## Input Sources

- Submitted questions and AI answer metadata.
- Student feedback ratings and comments.
- Tutor replies and resolution notes.
- Curriculum lesson progress and exercise attempts.
- AI teacher summary and exercise draft metadata.
- Weekly report weak topics, strengths, and recommendations.

## Assignment Lifecycle

Assignment states:

- `draft`
- `recommended`
- `assigned`
- `started`
- `completed`
- `skipped`
- `archived`

Assignments may come from curriculum exercises or AI exercise drafts. Generated exercises require teacher/admin review before assignment.

## Recommendation Boundary

- The system can recommend next practice based on weak-topic evidence, curriculum progress, and recent attempts.
- The system can surface recommended assignments to tutors/admins.
- The system must not claim fully autonomous tutoring decisions in v4.0.

## Visibility Contract

- Students can see assigned practice, recommendations, completion state, and lightweight rationale.
- Tutors can see memory evidence, stale flags, and assignment controls.
- Parents can see progress signals, weak areas, completed/assigned practice, and freshness.
- Raw internal scoring/debug details remain internal.

## Functional Verification Priorities

- Memory aggregation produces stable summaries from question, curriculum, and exercise evidence.
- Reviewed assignment lifecycle supports draft/recommended/assigned/started/completed/skipped/archived.
- Student/tutor/parent views use role-appropriate fields.
- Stale memory is visibly marked.
