# Phase 64 - UI Review

**Audited:** 2026-06-06
**Baseline:** ROADMAP.md Phase 64 criteria and abstract 6-pillar standards
**Screenshots:** not captured (no dev server on localhost:3000, 5173, or 8080)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Labels are operator-oriented, but validation failures are collapsed into counts instead of actionable messages. |
| 2. Visuals | 2/4 | The release panel fits the existing card language, but raw JSON dominates the dense operations surface. |
| 3. Color | 3/4 | Token usage is consistent, with limited accent use, but failure severity is not visually differentiated enough. |
| 4. Typography | 3/4 | Type scale is restrained, but repeated uppercase micro-labels and JSON blocks reduce scan speed. |
| 5. Spacing | 2/4 | Responsive grids and overflow are present, but another two-column, JSON-heavy panel increases vertical density. |
| 6. Experience Design | 2/4 | Read-only endpoints are wired and tested, but privacy-safe rendering depends on backend output and hides fixture refusal details. |

**Overall: 15/24**

---

## Top 3 Priority Fixes

1. **Stop rendering the validated bundle as raw JSON** - A backend regression could display S3 keys, tokens, raw payload fields, or customer markers directly in the UI. Render an allowlisted summary of request IDs, commit SHAs, deploy run IDs, statuses, and validation failures instead.
2. **Expose validation and fixture failure details as structured lists** - Operators currently get counts for missing fields and violations without seeing what to fix. Show `missing_required_fields`, `schema_errors`, `status_errors`, `fixture_errors`, privacy violations, and mutation refusal booleans in compact, copyable rows.
3. **Reduce release panel footprint in the operations page** - The new panel adds a large editable JSON textarea and preview before the report table. Collapse advanced JSON input behind a disclosure or move it below the status summary so the dense admin workflow remains scannable.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)

- **WARNING:** `Release evidence automation`, `Read only`, `Fixture safe`, `Validate release evidence`, and `Check fixture status` are clear enough for admin operators and match Phase 64's non-mutating intent in [ReportOperationsPage.tsx:1014](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1014)-[1042](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1042).
- **WARNING:** Validation messages only report coarse status strings, for example `Release evidence validation: ${result.status}` in [ReportOperationsPage.tsx:657](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:657). The UI does not translate missing fields, schema errors, privacy violations, or fixture errors into operator-facing remediation copy.
- **WARNING:** The default JSON uses placeholder values like `pending-backend-sha`, `pending-api-request-id`, and `pending` in [ReportOperationsPage.tsx:112](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:112)-[118](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:118). That is useful as a template, but it can look like a passing production bundle because all default statuses are `passed`.

### Pillar 2: Visuals (2/4)

- **WARNING:** The new section uses the existing admin visual language: bordered section, compact badges, icon-leading controls, and metric pills in [ReportOperationsPage.tsx:1011](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1011)-[1074](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1074). It does not introduce a visually inconsistent marketing surface.
- **WARNING:** The primary visual object is a large raw JSON textarea plus raw JSON preview. In a dense operations page, this makes the operator parse implementation shape rather than a release status hierarchy.
- **WARNING:** Release status shows only fixture status, fixture name, current version, expected baseline, and report id in [ReportOperationsPage.tsx:1054](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1054)-[1069](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1069). It omits visually prominent backend/frontend/infra/API/browser/privacy pass-fail rows even though those are the Phase 64 evidence fields.

### Pillar 3: Color (3/4)

- **WARNING:** No hardcoded hex or RGB colors were found in the audited page. The implementation uses design tokens such as `bg-card`, `bg-muted`, `text-muted-foreground`, `border-border`, and focus ring tokens.
- **WARNING:** Accent use is moderate. `text-primary` appears on six section icons, and `border-primary` appears in focus or selected states in the audited file. This is not broad accent flooding.
- **WARNING:** Failure states are under-signaled in the release panel. Validation violations and missing-field counts are displayed through the same neutral `MetricPill` styling at [ReportOperationsPage.tsx:1047](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1047)-[1051](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1051), so a nonzero violation count is not visually urgent.

### Pillar 4: Typography (3/4)

- **WARNING:** Type usage is relatively restrained for a dense admin surface: `text-xs` appears 53 times, `text-sm` 29 times, `text-base` 4 times, plus two small arbitrary sizes (`text-[10px]`, `text-[11px]`). Weights are mainly `font-semibold` and `font-medium`, with one `font-mono` JSON editor.
- **WARNING:** The release bundle textarea uses `font-mono text-xs` in [ReportOperationsPage.tsx:1023](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1023)-[1027](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1027), which is appropriate for JSON, but the panel currently leans on code-shaped text as the main UI.
- **WARNING:** The repeated `uppercase tracking-wide` micro-label pattern supports scanning in small doses, but here it compounds across filters, release evidence, evidence export, detail panels, job controls, and metrics. The Phase 64 panel would benefit from fewer all-caps labels and stronger semantic grouping.

### Pillar 5: Spacing (2/4)

- **WARNING:** The implementation uses responsive grids and overflow controls, including `xl:grid-cols-[minmax(0,1fr),420px]` for the release panel and `max-h-48 overflow-auto` for the preview in [ReportOperationsPage.tsx:1012](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1012)-[1068](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1068).
- **WARNING:** The page already has filter controls, async recovery job controls, recovery evidence export, the report table, detail panel, and jobs panel. Adding another always-expanded JSON-heavy section before the table increases scroll distance and weakens the existing operations workflow.
- **WARNING:** Arbitrary sizing is present for operational constraints: `min-w-[980px]`, `max-w-[220px]`, `max-w-[180px]`, `text-[10px]`, and `text-[11px]`. Most are defensible, but the new release panel's `420px` side rail plus JSON editor can crowd tablet and small laptop layouts.

### Pillar 6: Experience Design (2/4)

- **WARNING:** The Phase 64 controls are read-only at the API level: validation posts a bundle to `/admin/reports/release-evidence/validate`, and fixture status performs a GET against `/admin/reports/release-evidence/fixture-status` in [adminApi.ts:815](/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts:815)-[835](/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts:835). This satisfies the non-mutation requirement.
- **WARNING:** Privacy-safe rendering is fragile. `ReleaseEvidenceValidationResult.bundle` is typed as `Record<string, unknown>` in [adminApi.ts:463](/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts:463)-[477](/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts:477), then rendered wholesale via `JSON.stringify(validation.bundle, null, 2)` in [ReportOperationsPage.tsx:1009](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1009)-[1069](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx:1069). The UI has no client-side denylist, allowlist, or redaction guard before display.
- **WARNING:** Fixture status has privacy and mutation-refusal fields in the type at [adminApi.ts:480](/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts:480)-[512](/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts:512), but the UI does not render `identity`, `mutation_refusal`, `privacy.passed`, or `privacy.violations` beyond count-like metrics. Operators cannot verify refusal behavior or privacy evidence from the panel.
- **WARNING:** Accessibility selectors are mostly stable because visible labels wrap inputs and buttons have text names. The E2E test uses role and label selectors for the new controls in [admin-report-operations.spec.ts:1045](/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts:1045)-[1054](/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts:1054), which is good. However, the JSON textarea has no `aria-describedby` for validation errors or privacy warnings.
- **WARNING:** Test coverage checks happy-path evidence/status rendering and a body-level denylist for `weekly-reports/`, `json_s3_key`, `html_s3_key`, `presignedUrl`, and `https://s3` in [admin-report-operations.spec.ts:1076](/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts:1076)-[1078](/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts:1078). It does not cover validation failure rendering, admin-only denial for the new endpoints, fixture privacy violations, or raw payload-shaped fields returned by the validation endpoint.

---

## Files Audited

- [ROADMAP.md](/Users/zhdeng/stoa-backend/.planning/ROADMAP.md)
- [ReportOperationsPage.tsx](/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx)
- [admin-report-operations.spec.ts](/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts)
- [adminApi.ts](/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts)
- [useAdminReportOperations.ts](/Users/zhdeng/stoa-frontend/src/hooks/admin/useAdminReportOperations.ts)

Registry audit: skipped; no `components.json` found in the audited frontend or backend roots, and no Phase 64 UI-SPEC third-party registry table exists.
