---
phase: 05-verification-and-test-data
created: 2026-06-02
scope: local-demo-and-backend-contract
---

# Phase 5 Test Data

## Local Frontend Demo Accounts

These accounts are seeded in `/Users/zhdeng/stoa-frontend/backend/app/seed.py` and used by the local frontend demo/auth flow:

| Role | Email | Password | Notes |
|------|-------|----------|-------|
| Parent | `parent@test.com` | `password123` | Parent account linked to Anna Keller. |
| Student | `student@test.com` | `password123` | Linked student account for parent verification. |

## Linked Child

| Field | Value |
|-------|-------|
| Student ID | `user-student` |
| Name | `Anna Keller` |
| Grade | `Grade 8` |
| Subjects | Mathematics, Physics |
| Parent Link | `user-parent -> user-student` through `parent_children` |

## Activity Data

The local frontend demo backend seeds enough data to verify parent summary/history/report surfaces:

- Conversations and messages for student learning activity.
- Learning history records for the child history route.
- Teacher-help request records for teacher-help count/activity.
- Parent report record `parent-report-anna-week-1` for available report state.

## Missing State Verification

The focused Playwright spec fixtures missing-report and no-child states directly:

- `{ "items": [] }` for `GET /parents/me/children`.
- `{ "status": "missing", "report": null, "message": "No weekly report is available yet." }` for `GET /parents/me/children/{childId}/report`.

## Backend Contract Verification

Backend tests in `tests/test_parent_children.py` use monkeypatched parent/child/report records to prove:

- Parent-only `/parents/me/...` behavior.
- Cross-parent denial before child data reads.
- Empty child list response.
- Missing report state.
- Legacy parent path compatibility.
