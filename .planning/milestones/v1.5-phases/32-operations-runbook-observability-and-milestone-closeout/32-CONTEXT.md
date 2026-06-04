# Phase 32: Operations Runbook, Observability, and Milestone Closeout - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase turns the v1.5 production rollout and live smoke evidence into operator-ready documentation and final milestone closure evidence. It delivers an operations runbook, observability commands, rollback and escalation checklists, final verification, and the v1.5 milestone audit.

This phase does not add new report recovery functionality, create new production fixtures, or run customer-affecting mutation tests. Any live checks are read-only or previously approved safe smoke evidence.

</domain>

<decisions>
## Implementation Decisions

### Runbook Shape
- Organize the runbook around operator actions: inspect report operations, retry generation, resend one report, selected bulk resend, and stop/escalate.
- Keep commands copy-pasteable and tied to the production identifiers from Phase 28.
- Record safe target criteria and privacy expectations before any mutation workflow.
- Treat incident-wide async jobs, immutable audit storage, PDFs, multilingual report delivery, and report editing as out of scope.

### Observability
- Prefer CloudWatch Logs Insights queries and AWS CLI checks that an operator can run immediately.
- Include Lambda health, API health, SES delivery investigation, DynamoDB report lookup, and S3 artifact existence checks.
- Preserve the Phase 31 lesson that `stoa-api` send paths need scoped SES permission and that CDK can redeploy stale `../stoa-backend/dist` if the package is not rebuilt.

### Rollback And Stop Conditions
- Reuse Phase 28 rollback entry points for backend Lambda code, frontend assets, and infra drift.
- Add specific escalation paths for failed smoke, repeated resend failure, unexpected artifact state, unauthorized access findings, and stale Lambda package drift.
- Stop support operators from retrying when a report is not in the required failed state.
- Require cleanup confirmation for any non-customer smoke fixture.

### Verification
- Final verification should prove documentation completeness and current deployment health without mutating customer records.
- Backend focused report operations tests and ruff are required.
- Frontend build, lint, and admin report operations e2e are reused as the UI regression gate.
- CDK diff must be clean after the final package/IAM alignment.

### the agent's Discretion
The agent may choose concise table layouts and exact wording for runbook sections as long as OPSRUN and VERIFY requirements are traceable.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/routers/admin.py` defines admin report operations list/detail, retry generation, single resend, and selected bulk resend endpoints.
- `src/stoa/db/repositories/report_repo.py` owns report lookup, admin list access, and pagination token handling.
- `src/stoa/services/report_service.py`, `report_artifact_service.py`, and `notify_service.py` own report generation, artifact storage, and SES send behavior.
- Phase 28-31 verification artifacts contain the live evidence required for closeout.

### Established Patterns
- Planning artifacts use phase-scoped `CONTEXT`, `PLAN`, `SUMMARY`, and `VERIFICATION` files.
- Production evidence records exact commands, HTTP status, Lambda state, code SHA, and cleanup outcomes.
- Report artifact privacy is enforced by metadata-only API responses and no direct S3 URL/key exposure in UI bundles.

### Integration Points
- API base URL: `https://api.stoaedu.ch`
- Frontend route: `https://app.stoaedu.ch/admin/report-operations`
- AWS profile: `stoa`
- AWS region: `eu-central-2`
- API Lambda: `stoa-api`
- Weekly report Lambda: `stoa-weekly-report`
- Reports bucket: `stoa-reports-562923011260`
- DynamoDB table: `stoa-main`
- SES identity: `stoaedu.ch`

</code_context>

<specifics>
## Specific Ideas

- Use Phase 31 safe fixture identifiers only as examples of what safe smoke data looked like; do not leave them active.
- Include a warning that CDK deploys package `../stoa-backend/dist` and can overwrite Lambda code with stale assets.
- Include final cleanup evidence and final `cdk diff StoaApiStack` evidence in verification.

</specifics>

<deferred>
## Deferred Ideas

- Incident-wide async recovery jobs.
- Immutable report operation audit log beyond mutable fields on report records.
- Support ticket integration.
- Manual report editor and report content refresh workflow.
- PDF, multilingual report delivery, and billing-gated report access.

</deferred>
