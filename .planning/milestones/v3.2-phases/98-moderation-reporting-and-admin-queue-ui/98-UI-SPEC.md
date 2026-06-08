# UI Spec: Phase 98 Moderation Reporting And Admin Queue UI

## Audience

Internal admins triaging reported learning content, plus students and tutors who need a low-friction report action from existing learning workflows.

## Experience Direction

Operational and compact. The admin page should feel like the existing report operations and teacher SLA surfaces: restrained cards, clear filters, dense context, and predictable action controls. No marketing hero, decorative background, or explanatory feature copy.

## Required Views

- Student/tutor report dialog:
  - Icon+text report trigger.
  - Reason select.
  - Severity select.
  - Optional note.
  - Submit/cancel states and error feedback.
- Admin moderation queue:
  - Status, severity, and reason filters.
  - Queue rows with case id, severity, surface/reason, and context preview.
  - Detail panel with question, AI answer, and teacher reply previews.
  - Assignment input.
  - Status action buttons for `in_review`, `actioned`, `dismissed`, and `closed`.
  - Resolution note and internal note controls.
  - Case history timeline.

## Constraints

- Do not expose private image keys, presigned URLs, raw artifacts, tokens, or credentials.
- Keep controls stable at mobile and desktop widths.
- Use existing cards, badges, buttons, dialog, textarea, and dashboard layout patterns.
