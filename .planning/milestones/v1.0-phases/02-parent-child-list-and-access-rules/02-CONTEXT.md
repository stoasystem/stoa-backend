# Phase 2: Parent Child List and Access Rules - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** Smart discuss autonomous

<domain>
## Phase Boundary

This phase implements the first real parent portal backend contract: logged-in parents can call `GET /parents/me/children` and receive only children linked to their resolved local parent profile. The route must reject students, teachers/tutors, and admins from normal parent flows. Existing `/parents/{parent_id}/...` routes should remain available unless a compatibility fix is necessary.

This phase does not implement child summary, child history, report lookup shape changes, frontend integration, report generation, EventBridge targets, SES workflows, PDF generation, or broad frontend redesign.

</domain>

<decisions>
## Implementation Decisions

### Parent Identity

- Use the Phase 1 contract: local DynamoDB parent profile `user_id` is the canonical parent ownership identifier.
- Resolve authenticated parent identity from JWT claims by first trying `user_repo.get_user(user["sub"])`, then resolving Cognito email and using `user_repo.get_user_by_email(email)`.
- Require the resolved profile role to be `parent`; do not admit admin, student, teacher, or tutor through `/parents/me/...`.
- Do not trust client-supplied parent IDs in the normal parent portal flow.

### Child Lookup

- Implement `GET /parents/me/children` with a scan-based MVP lookup for student profile items where `role == "student"` and `parent_id == resolved_parent_user_id`.
- Paginate the scan so child lookup is not limited to the first DynamoDB page.
- Return frontend-friendly shape `{ "items": [...] }`, and return `{ "items": [] }` when no children are linked.
- Child list items should include `id`, `userId`, `name`, `email`, `grade`, `subjects`, and `relationship`.

### Legacy Routes

- Keep `/parents/{parent_id}/children` and `/parents/{parent_id}/reports/{week}` available.
- If legacy parent routes are touched, update their parent authorization to compare requested `parent_id` with the resolved local parent profile ID rather than raw JWT `sub`.
- Keep admin compatibility for legacy path-ID routes only if it already exists; do not allow admin through `/parents/me/...`.

### the agent's Discretion

- Keep helper functions route-local in `src/stoa/routers/parents.py` unless a small repository helper clearly reduces duplication.
- Use existing FastAPI/Pydantic patterns from the current router.
- Add minimal tests now only if they are needed for confidence; broader test/data coverage remains Phase 5.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `src/stoa/deps.py` provides `get_current_user` and `require_role`.
- `src/stoa/routers/students.py` contains `_resolve_profile`, which demonstrates direct profile lookup followed by Cognito email and `GSI-Email` fallback.
- `src/stoa/db/repositories/user_repo.py` provides `get_user` and `get_user_by_email`.
- `src/stoa/db/dynamodb.py` provides the shared DynamoDB table accessor.
- `src/stoa/routers/parents.py` already owns parent routes and child/report response models.

### Established Patterns

- Routers use `APIRouter` and route-local Pydantic models.
- Protected endpoints use FastAPI dependencies, usually `Depends(get_current_user)` or `Depends(require_role(...))`.
- Backend responses may use frontend-facing camelCase where needed.
- Existing parent child lookup scans for `parent_id` and `role=student`; this phase should make that scan paginated and identity-safe.

### Integration Points

- `src/stoa/main.py` already mounts the parents router at `/parents`.
- Frontend parent services expect `/parents/me/children`.
- Phase 3 will consume the parent resolver/ownership helper for child summary/history/report endpoints.
- Phase 4 will remove silent demo fallback and call the route implemented here.

</code_context>

<specifics>
## Specific Ideas

- Prefer a `ResolvedParent` Pydantic-free dataclass or small internal dict for helper return values.
- Add `_resolve_parent_profile(user, settings)` and `_scan_children_for_parent(parent_user_id)` helpers in `parents.py`.
- The route response should be a `ChildListResponse` model with `items: list[ChildSummary]`.
- Normalize child item fields from either `primary_subjects` or `subjects`.
- If a child has no display name, fall back to the email local part.

</specifics>

<deferred>
## Deferred Ideas

- Child summary/history/report routes are Phase 3.
- Frontend service/page updates are Phase 4.
- Full backend/frontend test suite and real test account documentation are Phase 5.
- Dedicated child lookup GSI is deferred unless Phase 2 implementation proves the scan MVP is unacceptable.
- Report S3 access remains deferred until CDK injects `S3_REPORTS_BUCKET` and grants report bucket permissions.

</deferred>
