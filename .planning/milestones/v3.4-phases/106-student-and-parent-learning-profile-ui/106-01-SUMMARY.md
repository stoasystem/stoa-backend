---
phase: 106
plan: 01
status: complete
completed: 2026-06-08
---

# Summary

Implemented the v3.4 learning profile frontend slice in `stoa-frontend`.

## Changes

- Replaced the stale `LearningProfile` type with the backend v3.4 shape.
- Added student and parent learning-profile API functions and TanStack Query hooks.
- Added `LearningProfileSignals` for subject activity, weak-topic evidence, rollout state labels, freshness, loading, and error states.
- Rendered learning signals on the student profile page and parent child summary page.
- Added rollout-aware subject choices to the student chat/new-question form.
- Updated the older advanced learning profile page and mock data to consume the same v3.4 contract.
- Added Playwright coverage for student learning expansion signals, chat subject choice, and parent child subject profile signals.

## Evidence

- Frontend lint passed.
- Frontend production build passed.
- Focused Playwright learning-profile and parent-dashboard suites passed.
