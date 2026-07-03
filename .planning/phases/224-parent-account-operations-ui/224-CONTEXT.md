# Phase 224: Parent Account Operations UI - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, accepted recommended decisions

<domain>
## Phase Boundary

Expose the v5.9 `/parents/me/account-operations` backend response in the web parent experience. This phase adds typed frontend client/query support, a parent-visible account operations page, a dashboard entry/summary, and focused tests for ready, attention, blocked, empty, loading, and error states.

</domain>

<decisions>
## Implementation Decisions

### Route And Placement
- Add a dedicated `/parent/account-operations` parent route protected by the existing parent role route.
- Add a compact dashboard card/entry that links to the detailed account operations page.
- Keep existing subscription operations card intact; account operations is a consolidated status view, not a replacement for plan change workflows.
- Do not add broad admin support behavior in this phase; admin detail belongs to Phase 225.

### Data Contract
- Add a typed `ParentAccountOperations` response matching backend fields: parent profile, billing, children, usage, and supportState.
- Add `parentQueryKeys.accountOperations()` and a `useParentAccountOperationsQuery` hook with `retry: false`.
- Do not add demo fallback for account operations. API failures should render explicit unavailable/error states.
- Support optional backend fields gracefully because the aggregation service is intentionally metadata-first.

### UI States
- Ready state should communicate that the account is operational.
- Attention state should list warnings in user-friendly language.
- Blocked state should list blockers and explain what needs action.
- No-child state should explain that no linked child is available.
- Inactive billing, unverified email, non-active child binding, and unreconciled usage must be visible without exposing provider internals.

### Visual Approach
- Use existing dashboard/page components, cards, badges, and restrained operational styling.
- Prefer dense but readable operational status panels over marketing copy.
- Keep child rows scannable: verification, binding, effective plan, consumed/remaining usage.
- Avoid nested cards and decorative hero treatment.

### the agent's Discretion
- Exact component decomposition and helper names.
- Whether dashboard entry uses the same query data or a lighter presentation of the full response.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/services/parent/parentApi.ts` contains parent endpoint clients.
- `src/services/parent/parentQueryKeys.ts` owns parent query key structure.
- `src/hooks/parent/useParentSubscriptionOperations.ts` provides the closest query hook pattern.
- `src/pages/parent/ParentDashboardPage.tsx` is the parent dashboard integration point.
- UI primitives include `Card`, `Badge`, `Button`, and existing parent dashboard cards.

### Established Patterns
- Parent pages use `DashboardLayout` and `PageContainer`.
- Parent route protection is configured in `src/app/router/AppRouter.tsx` under `RoleRoute allowedRoles={['parent']}`.
- E2E tests use Playwright route interception and `loginAs(page, 'parent')`.
- Parent-critical flows should not silently fall back to demo data.

### Integration Points
- Backend route: `GET /parents/me/account-operations`.
- Existing route group: `/parent`, `/parent/reports`, `/parent/children/:childId`.
- Existing parent dashboard can link to `/parent/account-operations`.

</code_context>

<specifics>
## Specific Ideas

- Surface support state as a top status band with blocker/warning chips.
- Render billing summary and child rows in the detail page.
- Include an empty-state panel when `children.length === 0`.
- Include loading skeleton text and an explicit API-error state.

</specifics>

<deferred>
## Deferred Ideas

- Admin account operations console is Phase 225.
- Production read-only smoke checklist is Phase 226.
- Native/mobile account operations UX remains future scope.

</deferred>
