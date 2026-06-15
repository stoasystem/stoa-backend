# Phase 194: Student Parent Assignment Explanation UX - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Build student and parent assignment explanation surfaces that show why automated or reviewed assignments appeared without exposing answer keys or internal ranking internals.

</domain>

<decisions>
## Implementation Decisions

### Scope
- Use existing student assignment and parent progress routes.
- Trust backend role-safe pruning for answer keys and automation internals.
- Keep explanation UI simple and family-safe.

### the agent's Discretion
Use route-level pages rather than changing existing dashboard cards, to keep the first integration focused and easy to verify.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Existing `DashboardLayout`, `PageContainer`, `PageHeader`, and card components.
- Existing parent route structure under `/parent/children/:childId`.

### Established Patterns
- Student routes live inside the student role route group.
- Parent child routes use `childId` params.

### Integration Points
- `GET /adaptive/students/me/assignments`
- `GET /adaptive/parents/me/children/{student_id}/progress`

</code_context>

<specifics>
## Specific Ideas

Show assignment source label, target topic, due state, automation/tutor-reviewed explanation, status, next action, assigned/completed counts, and no-assignment states.

</specifics>

<deferred>
## Deferred Ideas

Deep assignment detail pages, student completion actions, and notification-driven assignment entry points remain future scope.

</deferred>
