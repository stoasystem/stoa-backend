# Curriculum Rollout Contract: v3.8

## Curriculum Hierarchy

Canonical hierarchy:

- `subject`
- `grade_band`
- `unit`
- `topic`
- `lesson`
- `exercise`
- `checkpoint`

Supported rollout subjects:

- `math`
- `physics`
- `german`
- `english`

## Content States

- `seed`: imported or generated baseline content not ready for normal use.
- `draft`: editable curriculum content under preparation.
- `reviewed`: approved internally but not yet active for students.
- `active`: visible in normal student/parent/tutor curriculum flows.
- `archived`: hidden from normal flows while preserving progress/history compatibility.

## Lesson Fields

Minimum lesson fields:

- `lesson_id`
- `subject`
- `grade_band`
- `unit_id`
- `topic_id`
- `title`
- `objective`
- `explanation`
- `examples`
- `estimated_minutes`
- `difficulty`
- `prerequisite_lesson_ids`
- `status`
- `source`
- `created_at`
- `updated_at`

## Exercise Fields

Minimum exercise fields:

- `exercise_id`
- `lesson_id`
- `subject`
- `topic_id`
- `difficulty`
- `prompt`
- `choices`
- `answer_key`
- `explanation`
- `estimated_minutes`
- `skills`
- `status`
- `source`
- `created_at`
- `updated_at`

## Compatibility Contract

- Existing practice subjects/topics/lessons/challenges remain readable.
- Existing student progress, mistakes, completions, and challenge attempts remain attached to their original lesson/challenge identifiers.
- Backfill should add curriculum metadata around current records before replacing existing identifiers.
- Inactive, draft, and archived curriculum content is excluded from normal student flows unless explicitly requested by tutor/admin preview APIs.

## UI And API Implications

- Student UI needs subject, unit, topic, lesson, exercise, progress, and next-step navigation.
- Parent UI needs curriculum progress and weak-area summaries without exposing answer keys.
- Tutor/admin UI needs visibility into student curriculum context and inactive/draft status where authorized.
- Answer keys are not exposed to students before submission.

## Functional Verification Priorities

- Catalog APIs return active curriculum by subject/grade/topic.
- Existing practice progress still renders after curriculum metadata is added.
- Draft/inactive content is hidden from student flows.
- Parent and tutor views communicate curriculum progress and weak areas accurately.
