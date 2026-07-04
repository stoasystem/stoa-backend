---
phase: 235
name: Frontend Curriculum Editor And Migration Console
status: approved
created: 2026-07-05
---

# Phase 235 UI Spec: Curriculum Editor And Migration Console

## Product Intent

Build a dense internal operations surface for curriculum operators. The UI must feel like the existing STOA admin/support consoles, not a landing page, CMS demo, or decorative dashboard.

Primary users are internal curriculum authors, reviewers, publishers, and migration operators. They need fast scanning, explicit state, safe confirmation, and reliable API-error visibility.

## Existing Frontend Contract

- Use `DashboardLayout`, `PageContainer`, and `PageHeader`.
- Use existing UI primitives from `src/components/ui/*` and common states from `src/components/common/*`.
- Match existing admin pages such as `AdminAccountOperationsPage`, `AdminUsagePage`, moderation, report operations, and subscription operations.
- Use lucide icons inside buttons where useful.
- Use TanStack Query hooks and `adminQueryKeys`.
- Do not add demo fallback for authoring or migration state.

## Route And Information Architecture

Target route: `/admin/curriculum`.

Top-level tabs:

- Worklist
- Editor
- Review
- Migration
- Evidence

The first viewport should show:

- Page header with concise description and one primary action.
- Capability/status strip showing author/reviewer/publisher/migration access from backend/user metadata when available.
- Worklist or selected lesson state, not explanatory marketing copy.

## Layout

- Page width follows current admin page constraints through `PageContainer`.
- Use compact full-width sections and repeated cards only for repeated items.
- No nested cards.
- Prefer two-column desktop layout for editor detail:
  - Left: lesson/exercise form.
  - Right: validation, diff, audit, and actions.
- Collapse to a single column on mobile.
- Keep toolbars stable height; buttons must not wrap awkwardly.
- Tables/lists should use horizontal density with readable row spacing.

## Visual Style

- Use existing brand tokens and neutral admin surface colors.
- Keep cards at current project radius and border treatment.
- Do not introduce gradient/orb/background decoration.
- State colors:
  - Ready/valid: secondary/success styling already used in admin surfaces.
  - Warning/conflict: outline or amber-tinted panel.
  - Blocking/unauthorized/error: destructive or high-contrast alert panel.
- Use small section headings and compact labels inside panels.

## Interaction Contract

### Worklist

- Show draft/review/published/archive state, updated time, updated by, and quick actions.
- Empty state must say no curriculum items are available, not use demo content.
- Loading and error states must be explicit.

### Editor

- Fields:
  - title, objective, description
  - subject, topic, unit, grade, difficulty, estimated duration, language/locale
  - sections, objectives, examples, formulas, media references, tags, prerequisites
  - exercise prompt, type, difficulty, order, answer key, hint, explanation, skills
- Actions:
  - Save draft
  - Validate
  - Submit review
  - Approve
  - Request changes
  - Publish
  - Rollback/archive where authorized
- Save/validate/review actions must show pending, success, and API-error states.

### Diff, Review, Audit

- Diff view compares selected from/to versions in a bounded structural list.
- Validation preview groups blocking issues by field path.
- Audit view shows operation, actor, actor capabilities, from/to state, reason, and timestamp.
- Missing reviewer/publisher capability must render a clear restricted state.

### Migration

- Manifest input supports paste and file upload if feasible.
- Dry-run result shows summary counts, per-row action, conflicts, validation issues, publish intent, and rollback hint.
- Apply requires entering or confirming the dry-run confirmation token.
- Apply confirmation must be explicit and visually separated from dry-run.
- Evidence view shows migration ID, status, source metadata, applied rows, pointer/manifest references, rollback metadata, and idempotent retry state.

## Copy Rules

- Use operational labels: `Dry-run`, `Apply migration`, `Validation blockers`, `Evidence`, `Rollback hint`.
- Avoid instructional paragraphs when a label, status badge, or inline error is enough.
- Unauthorized states should be precise: missing curriculum author/reviewer/publisher/migration capability.

## Non-Negotiables

- No demo fallback for curriculum editor or migration data.
- No frontend-only authorization decisions. Backend `403` must be handled and displayed.
- Ordinary teacher/tutor users must not see mutation affordances unless backend data indicates explicit capability.
- Do not alter student/parent curriculum practice screens in this phase.
- Do not hide API errors behind empty states.

## Verification Targets

- Authorized editor happy path.
- Validation error path.
- Diff/review path.
- Migration dry-run.
- Migration apply confirmation.
- Ordinary teacher/tutor unauthorized state.
- API-error state with no demo fallback.
