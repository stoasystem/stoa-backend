---
phase: 106
name: Student And Parent Learning Profile UI
milestone: v3.4
status: complete
created: 2026-06-08
completed: 2026-06-08
---

# Phase 106 Context

## Objective

Expose the v3.4 learning expansion foundation in the frontend without representing physics, German, or English as full curriculum rollouts.

## Inputs

- Phase 104 subject contract: `math` active; `physics`, `german`, and `english` foundation profile support.
- Phase 105 backend endpoints:
  - `GET /students/{student_id}/learning-profile`
  - `GET /parents/me/children/{child_id}/learning-profile`
- Existing student profile, parent child summary, and chat/question entry UI.

## Scope

- Student profile renders subject-level activity, weak topic evidence, loading/error states, and freshness.
- Parent child summary renders the same learning-profile contract for linked child data.
- Student chat/new-question entry renders rollout-aware subject choices and uses the selected subject when creating a conversation.
- Existing advanced learning profile page and mocks are realigned to the v3.4 backend response shape.

## Non-Goals

- No full curriculum content UI.
- No exercise generation UI.
- No new entitlement or payment-provider behavior.
