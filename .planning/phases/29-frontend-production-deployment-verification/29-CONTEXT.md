---
phase: 29
phase_name: Frontend Production Deployment Verification
status: ready_for_planning
gathered: 2026-06-04
---

# Phase 29: Frontend Production Deployment Verification - Context

## Phase Boundary

Verify that the admin report operations UI is production-deployable and visible through the production frontend route.

This phase may run frontend build, lint, route checks, and public production route inspection. It does not mutate report records and does not call recovery APIs.

## Locked Decisions

### D-01 Frontend source and SHA

Use `/Users/zhdeng/stoa-frontend` as the frontend source repository. Current frontend SHA at planning time is `1f4b88bfc93dea50c928502333f7e2b8084a12b4`.

### D-02 Production deployment workflow

The frontend production deploy workflow is `/Users/zhdeng/stoa-frontend/.github/workflows/deploy.yml`.

It builds with:

- `VITE_API_MODE=production`
- `VITE_API_BASE_URL=https://api.stoaedu.ch`
- `VITE_ENABLE_DEMO_API=false`
- `VITE_SHOW_DEMO_ACCOUNTS=false`
- `VITE_SHOW_DEMO_BADGES=false`
- `VITE_SHOW_DEMO_SURFACES=false`

It deploys to S3 bucket `stoa-frontend-562923011260` and invalidates CloudFront distribution `E27CVAMQHDMW80`.

### D-03 Production route

The route under verification is `https://app.stoaedu.ch/admin/report-operations`.

The route must serve the production SPA, and evidence should include HTTP status, cache headers or asset identifiers, and whether report operations UI markers appear in deployed assets.

### D-04 Authenticated UI limitation

Admin-authenticated browser verification is required for full `LIVE-03` confidence. If no admin browser session or token is available in the current environment, record the route/bundle evidence and mark authenticated browser verification as not automated rather than inventing success.

## Canonical References

- `.planning/REQUIREMENTS.md` - REL-02, REL-03, LIVE-03 requirements.
- `.planning/ROADMAP.md` - Phase 29 success criteria.
- `.planning/phases/28-release-readiness-and-deployment-contract/28-RELEASE-READINESS.md` - release and evidence contract.
- `.planning/milestones/v1.4-phases/26-admin-report-operations-ui/26-01-SUMMARY.md` - UI implementation summary.
- `.planning/milestones/v1.4-phases/27-report-recovery-verification-and-live-evidence/27-VERIFICATION.md` - previous route and live evidence.
- `/Users/zhdeng/stoa-frontend/.github/workflows/deploy.yml` - production deployment workflow.

## Specific Ideas

Phase 29 should produce a verification artifact with:

- Frontend git status and SHA.
- Deploy workflow production env confirmation.
- Local production build and lint results.
- Production route HTTP response evidence.
- Production bundle/asset evidence for report operations UI.
- Explicit note on authenticated admin browser verification status.

## Deferred Ideas

- Backend authenticated report operations API verification belongs to Phase 30.
- Recovery mutation smoke belongs to Phase 31.
- Full operator runbook belongs to Phase 32.

---
*Phase: 29-frontend-production-deployment-verification*
*Context gathered: 2026-06-04*
