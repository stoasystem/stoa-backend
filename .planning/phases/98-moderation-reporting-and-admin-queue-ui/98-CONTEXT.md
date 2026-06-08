# Phase 98 Context: Moderation Reporting And Admin Queue UI

**Milestone:** v3.2 Content Moderation And Internal Operations
**Requirement:** UI-17
**Status:** Complete

## Phase Boundary

Expose practical moderation workflows in the frontend:

- Student report action from the learning conversation assistant answer.
- Tutor report actions from help request detail context.
- Admin moderation queue with filters, detail context, assignment, status actions, resolution notes, and internal notes.

## Implementation Decisions

- Keep the admin page dense and operational, matching existing admin dashboards.
- Add a shared report dialog for student/tutor surfaces.
- Add demo fallback data so internal demo-mode verification works without production customer mutations.
- Add a new `/admin/moderation` admin route and nav entry.

## Verification Focus

- Student can open and submit the report dialog.
- Admin can filter/open/action/note a moderation case.
- Existing tutor help workflow remains usable after adding report actions.
