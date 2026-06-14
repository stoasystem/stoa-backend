# Phase 177 UI Design Contract: Admin Rich Curriculum Editor

## Product Surface

The editor is an internal curriculum operations workspace for admins, tutors, teachers, and curriculum reviewers. It should feel like a dense editorial tool, not a marketing page or learning surface.

## Layout Contract

Use a three-zone operational layout:

| Zone | Purpose | Required Behavior |
|------|---------|-------------------|
| Left rail | Worklist, subject/topic filters, lifecycle state filters | Fixed width on desktop, collapsible drawer on mobile/tablet. |
| Main editor | Lesson sections, examples, formulas, exercise blocks, hints, explanations, answer keys, tags, prerequisites, duration | Stable section stack with inline validation and no layout shift when errors appear. |
| Right panel | Validation, review notes, publish readiness, audit/refusal state | Sticky on desktop, tabbed below editor on narrow screens. |

Primary tabs:

- Editor
- Preview
- Diff
- Review
- Publish
- Audit

## Interaction Contract

- Draft save should be explicit unless autosave is implemented with visible saved/unsaved/error state.
- Validation errors should point to exact fields and blocks.
- Preview should render the student/parent published view shape without exposing draft-only metadata or answer keys to unauthorized roles.
- Diff should compare draft/review/published/rollback candidate versions at lesson and exercise-block granularity.
- Publish, rollback, and archive actions require an operator reason and show the expected current published version before submission.

## Component Contract

Use standard operational controls:

- Icon buttons for add/remove/reorder blocks.
- Segmented controls for editor/preview/diff/review modes.
- Field-level validation messages under inputs.
- Tables for worklist, migration/conflict previews, and audit history.
- Status badges for draft, in review, changes requested, approved, published, superseded, archived, and refused.
- Confirmation modal for publish/rollback/archive with reason input.

## Visual Contract

- Quiet, utilitarian information density.
- No hero sections, decorative cards, or marketing composition.
- Preserve readable line lengths for rich text blocks.
- Keep cards to repeated items such as exercise blocks, validation rows, and audit events.
- Use restrained color for state: neutral draft, blue review, green approved/published, amber changes/conflicts, red refused/validation failure, gray archived.

## Accessibility And Responsive Contract

- Keyboard navigation must reach worklist, editor blocks, validation panel, and publish actions.
- Reorder controls need accessible labels and non-drag alternatives.
- Mobile and tablet should prioritize review/preview over multi-column density: left rail becomes drawer, right panel becomes tabs.
- Long formulas, URLs, code blocks, and German/English localized labels must wrap without overlapping controls.

## Empty, Loading, Error, And Refusal States

- Empty worklist: show filters and a clear create-draft action.
- Loading: use skeleton rows/blocks with stable dimensions.
- Validation failure: keep draft content visible, focus the first failing field on request.
- Permission denied: explain that admin/tutor/teacher role is required without exposing draft content.
- Stale pointer/refusal: show current published version, submitted expected version, and next safe action.

## Frontend Implementation Notes

Expected `/Users/zhdeng/stoa-frontend` integration points:

- Admin curriculum worklist route.
- Lesson draft editor route.
- Preview/diff/review tabs.
- Publish/rollback/archive confirmation flows.
- Content-quality side panel or linked analytics view.

The frontend must not use demo fallback for publish, rollback, archive, or validation states.
