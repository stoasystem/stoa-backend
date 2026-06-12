# v4.6 Curriculum Operations Release Gate

**Milestone:** v4.6 Rich Curriculum Authoring And Analytics Foundation
**Status:** Passed - local backend release gate
**Verified at:** 2026-06-12T11:51:32+02:00

## Completed Scope

| Area | Evidence |
|------|----------|
| Curriculum authoring contract | Phase 152 defines stable public IDs, immutable version IDs, separate lifecycles, role boundaries, publish manifests, validation, audit, rollback, archive, and legacy readiness. |
| Admin authoring MVP | Phase 153 adds dedicated `curriculum_ops_repo`, `curriculum_ops_service`, and admin routes for draft, review, approve/request changes, publish, rollback, archive, preview, audit, and worklist behavior. |
| Publish safety | Phase 153 publish/rollback uses expected published-version compare-and-set semantics and idempotent current-pointer handling. |
| Draft isolation | Phase 153 tests prove drafts do not write published projections before publish. Existing student/parent curriculum reads remain on published routes. |
| Archive guard | Phase 153 archive refuses active assignment references and records refusal audit evidence. |
| Analytics | Phase 154 adds bounded signal/metric helpers and aggregate content-quality endpoint with public/version IDs and source segmentation. |
| Privacy | Phase 154 content-quality response is aggregate-only and excludes raw student answers, answer keys, and student identifiers. |
| Compatibility | Existing curriculum rollout, adaptive learning, and admin operations regression tests pass. |

## Verification Commands

| Command | Result | Notes |
|---------|--------|-------|
| `./.venv/bin/pytest -q tests/test_curriculum_ops.py` | Passed | 6 lifecycle/publish/archive/rollback tests. |
| `./.venv/bin/pytest -q tests/test_curriculum_analytics.py` | Passed | 4 signal/privacy tests. |
| `./.venv/bin/pytest -q tests/test_curriculum_rollout.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py tests/test_admin_report_ops.py` | Passed | 128 compatibility/admin tests. |
| `./.venv/bin/pytest -q` | Passed | 369 backend tests. |
| `./.venv/bin/ruff check src tests` | Passed | Full source/test lint gate. |

## Release Decision

v4.6 passes the local backend release gate. It is ready to be treated as locally complete, subject to the known deferred production/editor scope below.

## Deferred Scope

- Rich WYSIWYG or collaborative curriculum editor UI.
- Production content migration/import.
- Warehouse-backed BI or long-horizon analytics.
- Automatic publishing of AI-generated exercise drafts.
- Full adaptive sequencing across all curriculum content.
- Production deployment/live smoke.

## Next Milestone Recommendation

Recommended next milestone: **Payment Production Activation And Provider Automation**.

Reason: v4.4 already built Stripe/TWINT live-readiness foundations but real customer charging remains externally gated. The next highest-risk product dependency is approved live Stripe credentials, TWINT capability/account validation, webhook registration, direct refund execution, provider readiness checks, and finance acceptance. This is more time-sensitive than deeper curriculum analytics because v4.6 now closes the curriculum operations foundation locally.

