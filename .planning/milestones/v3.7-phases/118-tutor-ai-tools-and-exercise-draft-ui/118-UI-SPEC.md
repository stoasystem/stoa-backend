---
phase: 118
name: Tutor AI Tools And Exercise Draft UI
milestone: v3.7
status: complete
requirement: UI-22
---

# UI Spec

## Surface

Add an `AI teacher tools` panel to the tutor help request detail page.

## Required Controls

- Generate teacher summary draft for the current request.
- Show session summary, misconception summary, suggested focus, and draft follow-up explanation.
- Generate practice exercise draft from current student, subject, topic, difficulty, and count.
- Bound item count to 1-5.
- Support regenerate, accept, reject, and archive actions for each draft.

## Required States

- Empty: no draft generated yet.
- Draft: generated and awaiting teacher/admin review.
- Accepted, rejected, archived: reviewed state disables final review actions.
- Error: draft generation unavailable.

## Safety Copy

- The panel must clearly show draft-only status.
- Drafts must show `not delivered`; no UI action may imply automatic student delivery.

## Accessibility

- Generate buttons must have distinct accessible names for summary and exercise workflows.
- Icon buttons/actions require visible or accessible labels.
