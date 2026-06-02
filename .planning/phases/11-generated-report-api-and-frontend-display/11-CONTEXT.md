# Phase 11: Generated Report API and Frontend Display - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>

## Phase Boundary

This phase exposes generated weekly report details through the parent API and renders those details in the parent portal. It covers generated report detail, missing state, and generation/email failure visibility for the owning parent. It does not broaden backend verification beyond focused route/frontend tests; Phase 12 and Phase 13 cover wider verification.

</domain>

<decisions>

## Implementation Decisions

### Backend API Contract

- Extend the existing `/parents/me/children/{child_id}/report` and `/reports/{week}` response shape rather than creating a separate report endpoint.
- Preserve legacy report fields for backward compatibility.
- Add generated report fields: `weekEnd`, `stats`, `summary`, `strengths`, `weakTopics`, `recommendationItems`, `teacherNote`, `generatedAt`, `emailStatus`, `status`, and error fields.
- Map stored statuses to parent-facing state:
  - `available` for generated/email_sent/email_failed reports with content.
  - `failed` for generation_failed reports.
  - `missing` when no report exists.

### Frontend Display Contract

- Extend `ParentChildReportDetail` and `ParentChildReportState` types.
- Keep using the real `/parents/me/children/{childId}/report` endpoint with no demo fallback.
- Update `ChildReportPage` to render generated summary, week range, stats, weak topics, recommendation items, generated timestamp, and email status.
- Preserve the existing missing-report card.
- Show `email_failed`, `pending`, or generation failure states clearly but calmly.

### UI Direction

- Use the existing parent dashboard design system: quiet operational cards, compact metric tiles, and readable report sections.
- Avoid marketing-style hero layout or nested card stacks.
- Use badges for status and fixed metric cards for scanability.

### the agent's Discretion

The agent may inline simple report section rendering in `ChildReportPage` rather than introducing new components if that keeps the change scoped.

</decisions>

<code_context>

## Existing Code Insights

### Backend

- `ParentChildReportDetail` currently exposes legacy fields only.
- `_report_detail_from_item` maps DynamoDB report records into the parent response.
- Report records from Phase 9 include generated content, email status, generated timestamps, S3 keys, and error fields.
- Child-specific routes already verify ownership before reading reports.

### Frontend

- `src/types/parentReport.ts` defines `ParentChildReportDetail` and `ParentChildReportState`.
- `src/services/parent/parentReportApi.ts` calls `/parents/me/children/{childId}/report`.
- `src/pages/parent/ChildReportPage.tsx` renders a basic weekly report page from legacy fields.
- Playwright parent dashboard tests already mock available and missing report states.

### Integration Points

- Phase 12 will add backend report flow verification.
- Phase 13 will add frontend generated/missing/email-failed state verification.

</code_context>

<specifics>

## Specific Ideas

- Use existing `stats` object from report records for API/frontend metrics.
- Convert `weak_topics` objects to `{ topic, note }` for frontend display.
- Convert `recommendation_items` into a list and keep legacy `recommendations` string.
- Add e2e mock fields now so the generated display can be verified by existing parent dashboard test.

</specifics>

<deferred>

## Deferred Ideas

- Dedicated route for historical week selection can wait unless Phase 13 tests require it.
- Visual regression/browser screenshot verification can be done after frontend changes if a local server is started.

</deferred>
