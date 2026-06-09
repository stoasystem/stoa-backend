# Phase 122 Context: Student/Parent Curriculum UX And Tutor Signals

**Milestone:** v3.8 Full Curriculum Rollout
**Requirement:** UI-23
**Status:** Complete

## Phase Boundary

Expose the curriculum rollout through student, parent, tutor, and admin-adjacent surfaces using real curriculum API data and clear rollout states.

## Existing Code Insights

- Student practice overview already shows subject selection, daily goal, and practice progress.
- Parent child summary already shows subject profile and weak topic signals.
- Tutor help request detail already shows practice context, teacher assistance seed, and AI teacher draft tools.
- Practice API services already use `withPracticeDemo` for demo-safe fallback data.

## Decisions

- Add a reusable `CurriculumRolloutPanel` instead of a standalone route.
- Place the panel on:
  - student practice overview,
  - parent child summary,
  - tutor help request detail.
- Use the new backend `/practice/curriculum/*` APIs through practice services and hooks.
- Keep the UI explicit that only active curriculum content appears in normal flows and draft/reviewed/archived states are hidden unless authorized.

## Deferred

- Full curriculum authoring/admin publishing UI.
- Separate curriculum explorer route.
- Automatic assignment/delivery of generated exercises.
