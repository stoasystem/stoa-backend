# Phase 141 Context: Responsive Student Parent Tutor Core Flow Polish

**Phase:** 141
**Requirement:** MOBILEUI-02
**Gathered:** 2026-06-11
**Status:** Ready for implementation

## Phase Boundary

Implement responsive polish for selected student, parent, tutor, and admin frontend flows in `/Users/zhdeng/stoa-frontend`.

The phase should use the Phase 140 contract as the source of truth and avoid broad redesign. The goal is practical mobile usability: no horizontal overflow, reachable primary actions, stable shared navigation, and targeted browser evidence.

## Decisions

- Make shared shell/action primitives safer first because they affect all selected role flows.
- Keep current STOA visual language, Tailwind/Radix/lucide stack, and shared components.
- Add Playwright coverage at 390 x 844 for representative role routes.
- Do not add localization persistence in this phase; Phase 142 owns language preference UI.

## Existing Code Context

- `src/layouts/AppLayout.tsx` owns top navigation, mobile bottom navigation, language switcher, notification center, and user menu.
- `src/components/common/PageHeader.tsx` and `PageActions.tsx` own shared page action layout.
- `src/components/ui/button.tsx` controls shared button sizing/wrapping behavior.
- `src/components/tutor/AiTeacherToolsPanel.tsx` is a dense tutor surface that needs mobile-safe action stacking.
- `tests/e2e/helpers.ts` provides demo login helpers for role-based Playwright checks.

## Verification Targets

- `npm run lint`
- `npm run build`
- `npx playwright test tests/e2e/mobile-responsive.spec.ts`
