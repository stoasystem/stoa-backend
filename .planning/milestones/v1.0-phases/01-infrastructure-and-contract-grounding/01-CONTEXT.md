# Phase 1: Infrastructure and Contract Grounding - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** Smart discuss autonomous infrastructure path

<domain>
## Phase Boundary

This phase confirms CDK-backed resource assumptions and parent identity/lookup contracts before backend route implementation. It must produce implementation-ready evidence for DynamoDB table/indexes, Cognito groups/app clients, Lambda environment variables, report storage/permissions, parent-child lookup feasibility, and the canonical identifier path for parent ownership checks.

This phase does not implement parent API routes, frontend service changes, report generation, EventBridge targets, SES weekly email workflows, PDF generation, or broad frontend redesign.

</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion

- Use the existing CDK source in `/Users/zhdeng/stoa-infra` as the authority for AWS resource shape.
- Use the existing backend configuration pattern in `src/stoa/config.py` and AWS access patterns in `src/stoa/deps.py` / `src/stoa/db/dynamodb.py` when evaluating environment variables.
- Prefer existing DynamoDB single-table indexes over new infrastructure. If no suitable parent-child lookup index exists, document whether scan-based MVP lookup is acceptable or whether a CDK-backed GSI is required.
- Treat Cognito `sub` versus local user ID mismatch as a required decision. The output must identify the canonical path or compatibility fallback that later phases should implement.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- Backend settings are centralized in `src/stoa/config.py` with `pydantic-settings`.
- DynamoDB table access is centralized in `src/stoa/db/dynamodb.py`.
- Cognito JWT validation, role resolution, and role guards live in `src/stoa/deps.py`.
- Parent child listing and report lookup currently live in `src/stoa/routers/parents.py`.
- User, question, practice, and report repositories already exist under `src/stoa/db/repositories/`.

### Established Patterns

- FastAPI routes use `APIRouter` modules included from `src/stoa/main.py`.
- Auth-protected endpoints use `Depends(get_current_user)` or `Depends(require_role(...))`.
- Backend role names include `student`, `parent`, `teacher`, and `admin`; frontend `tutor` maps to backend `teacher`.
- DynamoDB uses single-table key prefixes such as `USER#`, `QUESTION#`, `PROGRESS#`, `MISTAKES#`, and `REPORT#`.
- Query-based access is preferred when keys or GSIs exist, but scans are already used in some aggregate/list flows.

### Integration Points

- Infrastructure/CDK source: `/Users/zhdeng/stoa-infra/stacks/auth_stack.py`, `database_stack.py`, `storage_stack.py`, `api_stack.py`, `notification_stack.py`, and `monitoring_stack.py`.
- Backend environment variable consumers: `src/stoa/config.py`, `src/stoa/db/dynamodb.py`, `src/stoa/services/notify_service.py`, and route modules that use settings.
- Parent portal downstream phases depend on the output of this phase for ownership lookup and parent-child access pattern choices.

</code_context>

<specifics>
## Specific Ideas

- Confirm whether CDK defines a `GSI-ParentId` or equivalent access path for parent-owned child lookup.
- Confirm whether `GSI-ParentId` is report-specific, user/profile-specific, or generic enough for child lookup.
- Confirm whether the Lambda receives all backend resource names through environment variables.
- Confirm whether report bucket resources and permissions already exist even though weekly report generation is out of scope.
- Document the safest identifier strategy for parent ownership when user profiles may use local UUIDs but JWTs use Cognito `sub`.

</specifics>

<deferred>
## Deferred Ideas

- Backend `/parents/me/...` route implementation belongs to Phase 2 and Phase 3.
- Frontend parent service and page changes belong to Phase 4.
- Backend/frontend test implementation and real test data documentation belong to Phase 5.
- Weekly report automation, EventBridge target wiring, SES weekly emails, PDF generation, and monitoring/retry behavior remain deferred to a follow-up milestone.

</deferred>
