---
phase: 123
status: passed
date: 2026-06-09
requirement: VERIFY-21
---

# Phase 123 Release Gate

## Decision

v3.8 passes the local functional release gate for full curriculum rollout.

## Evidence

- Backend full test suite passed: `311 passed in 6.52s`.
- Backend focused Ruff passed for curriculum service, practice repository/router changes, and curriculum rollout tests.
- Frontend lint passed.
- Frontend production build passed.
- Targeted Playwright coverage passed for student/parent learning-profile flows and tutor workflow: `4 passed`.
- Feature gap audit now records full multi-subject curriculum rollout as closed for local functional scope.

## Scope Closed

- Curriculum hierarchy and rollout-state contract for math, physics, German, and English.
- Backend curriculum catalog, lesson detail, exercise bank, and curriculum progress APIs backed by existing practice records.
- Student/parent curriculum rollout visibility and tutor curriculum context signals.
- Inactive/draft/preview/archived boundary handling, including answer-key authorization.

## Residual Scope

- Automatic student assignment of generated exercises.
- Long-term adaptive exercise sequencing beyond current progress and weak-topic signals.
- Rich curriculum authoring workflow with approval queues and versioned publishing.
- Production content QA/analytics.
- Payment-provider integration, production WebSocket infrastructure rollout, push/native/email delivery, mobile/multilingual polish, and support integrations.
