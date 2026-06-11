# Phase 141 UI Design Contract

**Phase:** 141 Responsive Student Parent Tutor Core Flow Polish
**Status:** Approved
**Updated:** 2026-06-11

## Visual Contract

- Preserve existing STOA operational styling and component primitives.
- Do not introduce a new layout system or new color palette.
- Use subtle responsive refinements in shared primitives rather than page-specific decorative redesign.
- Keep dashboard/tool surfaces dense, scannable, and action-oriented.

## Mobile Layout Contract

- Mobile viewport target is 390 x 844.
- Shared page actions must wrap on mobile instead of overflowing.
- Shared buttons must allow multi-line labels on mobile while preserving fixed icon-button dimensions.
- Mobile top navigation should prioritize utility actions and avoid crowding from long labels.
- Mobile bottom navigation should use stable, evenly distributed items with safe-area padding.
- Dense tutor AI tool controls should stack before switching to horizontal layout at wider breakpoints.

## Browser Evidence Contract

Targeted mobile checks must cover:

- Student dashboard/practice/chat.
- Parent overview/report.
- Tutor queue/request detail/AI tools.
- Admin overview/moderation.

Each route check must verify no horizontal overflow and at least one primary visible action or heading.
