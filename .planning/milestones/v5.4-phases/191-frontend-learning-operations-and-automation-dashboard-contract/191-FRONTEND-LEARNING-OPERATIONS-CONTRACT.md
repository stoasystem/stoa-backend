# Frontend Learning Operations And Automation Dashboard Contract

## Function Purpose

v5.4 turns backend learning automation into usable product workflows.

The user-facing purpose is:

- Tutors/admins can preview and approve automated practice assignment candidates.
- Tutors/admins can see why candidates were selected or refused.
- Operators can inspect learning health, sequencing coverage, assignment outcomes, and intervention opportunities.
- Students and parents can understand why practice work appeared and what it targets.

This is not automatic assignment of human teachers to student help requests.

## Implementation Strategy

Use existing backend APIs first:

| Workflow | Existing API |
|----------|--------------|
| Preview automation candidates | `POST /adaptive/students/{student_id}/assignment-automation/batches/preview` |
| Execute approved automation batch | `POST /adaptive/students/{student_id}/assignment-automation/batches/execute` |
| Tutor/admin assignment review | `GET /adaptive/students/{student_id}/assignments` |
| Student assignment list | `GET /adaptive/students/me/assignments` |
| Parent progress explanation | `GET /adaptive/parents/me/children/{student_id}/progress` |
| Operator learning dashboard | `GET /admin/curriculum/analytics/dashboard` |
| Warehouse readiness | `GET /admin/curriculum/analytics/warehouse-readiness` |
| Warehouse export summary | `GET /admin/curriculum/analytics/warehouse-export` |

Frontend work should integrate these routes with explicit no-demo-fallback states. Backend work should be limited to missing fields, unstable response shape, or contract bugs found during integration.

## Tutor/Admin Automation Console

Required UI surfaces:

- Student selector or student detail entry point.
- Policy controls: autonomy level, subject/topic filters, source types, max assignments, confidence threshold, freshness, due window, paused state.
- Preview action that renders:
  - selected candidates
  - refused candidates
  - refusal reasons
  - confidence/source/review status
  - expected impact
- Approval/execute action that renders:
  - created/assigned/delivered/skipped/refused/duplicate/failed results
  - assignment IDs for created items
  - safe automation metadata
- Empty states:
  - no eligible candidates
  - policy paused
  - student out of scope
  - all candidates duplicate/stale/low-confidence

## Learning Operations Dashboard

Required UI surfaces:

- Cohort/subject/topic filters where supported.
- Sequencing coverage summary.
- Assignment starts/completions/skips/archives.
- Content quality and intervention candidates.
- Warehouse readiness card with `not_configured` as a normal internal-development state.
- Export preview/download affordance if existing API response is useful for operators.

## Student/Parent Explanation UX

Student view should show:

- Assignment title, subject/topic, due state, and next action.
- Source label such as curriculum practice, reviewed AI practice, or adaptive recommendation.
- Plain explanation: why this was assigned and whether it was tutor-approved/automation-created.

Parent view should show:

- Family-safe progress explanation.
- Assigned/completed counts.
- What the assignment targets.
- No answer keys, raw student answers, or internal ranking internals.

## State Handling

The frontend must handle:

- Loading.
- Empty.
- Policy paused.
- Refused candidates.
- Partial execute success.
- Duplicate result.
- Backend validation error.
- Unauthorized/role mismatch.
- No live warehouse configured.

## Role Boundaries

- Tutor/admin/teacher can operate preview/execute and view dashboard details.
- Student can see own assignments and explanations.
- Parent can see child progress summaries and assignment explanations.
- Student/parent must not see answer keys or internal ranking internals.

## Follow-Up Phases

- Phase 192: Tutor/admin automation review console.
- Phase 193: Learning operations dashboard integration.
- Phase 194: Student/parent assignment explanation UX.
- Phase 195: v5.4 release gate and next milestone decision.
