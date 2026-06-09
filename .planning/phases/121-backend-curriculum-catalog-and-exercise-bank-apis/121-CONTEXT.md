# Phase 121 Context: Backend Curriculum Catalog And Exercise Bank APIs

**Milestone:** v3.8 Full Curriculum Rollout
**Requirement:** CURRIC-02
**Status:** Complete

## Phase Boundary

Add backend curriculum catalog and exercise bank APIs that expose active curriculum data while preserving existing practice progress behavior.

## Existing Code Insights

- Practice content is already stored under `PK=PRACTICE` with subject, topic, unit, lesson, and challenge sort-key prefixes.
- Student progress is already stored under `PK=PROGRESS#{user_id}`.
- Mistake review data is already stored under `PK=MISTAKES#{user_id}`.
- Existing practice routes expose subjects, overview, topic roadmaps, lesson detail, lesson completion, challenge answers, mistakes, hints, and teacher-help request helpers.

## Decisions

- Implement curriculum rollout as an additive projection over existing practice content rather than replacing current practice identifiers.
- Add static `/practice/curriculum/*` routes before dynamic practice routes to avoid routing conflicts.
- Treat missing content state on existing practice rows as `active`, allowing current seeded practice data to backfill into the curriculum catalog.
- Restrict preview/inactive content to tutor, teacher, and admin roles.
- Hide answer keys from students even when `includeAnswers=true`; answer keys are available only to tutor/teacher/admin callers.

## Deferred

- Rich content authoring workflow and versioned publishing.
- Automatic student assignment or delivery of generated exercises.
- Long-term adaptive sequencing beyond existing progress and weak-topic signals.
