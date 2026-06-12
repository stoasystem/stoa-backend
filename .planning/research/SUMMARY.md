# Project Research Summary

**Project:** STOA backend
**Domain:** Internal curriculum authoring and bounded curriculum analytics
**Researched:** 2026-06-12
**Confidence:** HIGH

## Executive Summary

v4.6 is not a CMS rebuild and not a BI milestone. It is an internal curriculum operations foundation for STOA's existing learner-facing curriculum system: draft, review, publish, rollback, archive, and bounded analytics that tell staff what content is underperforming. The correct shape is to keep student-visible curriculum on the current FastAPI + Pydantic + DynamoDB single-table architecture, add a separate authoring lifecycle layer in the same table, and materialize analytics as small aggregate models tied to existing learning events.

The key implementation decision is to preserve stable public lesson and exercise IDs while introducing immutable authoring versions and explicit published-version pointers. Published content must remain the only thing readable from normal student and parent routes. Authoring state, preview overlays, review queues, and audit evidence should live in dedicated admin/tutor paths. Analytics should stay descriptive and operational: confusing exercises, weak topics, stale lessons, and content gaps. Do not add a CMS, warehouse, search stack, workflow engine, or collaborative editing system in this milestone.

The main risks are draft leakage into student APIs, partial publish/rollback across multi-row curriculum bundles, and analytics built from mutable rows or request-time scans. Mitigation is clear from the research: separate read models, use immutable versions plus conditional publish/rollback, keep archived published snapshots resolvable, and build analytics from append-only signals with bounded rollups.

## Key Findings

### Recommended Stack

Keep the existing backend stack and extend it with new repositories, services, and models rather than new infrastructure. The milestone fits the current service/repository architecture and DynamoDB operational style.

**Core technologies:**
- Python 3.12: runtime baseline — no v4.6 need for a runtime change.
- FastAPI: admin/tutor/student route contracts — already matches the repo's role-scoped API structure.
- Pydantic v2: authoring, review, publish, rollback, and analytics schemas — keeps validation explicit and testable.
- DynamoDB single-table via boto3: published projection, authoring state, audit, and rollups — preserves current persistence model and avoids a second data plane.
- pytest + pytest-asyncio + moto: lifecycle, visibility, rollback, and analytics tests — existing test stack is sufficient.

**Required additions inside the stack:**
- `curriculum_ops_repo.py` and `curriculum_authoring_service.py` for draft/review/publish/archive/rollback.
- `curriculum_analytics_repo.py` and `curriculum_analytics_service.py` for signal ingestion and aggregate reads.
- Dedicated curriculum ops models and a dedicated admin curriculum router.

**Critical stack decision:**
- Do not add a CMS, warehouse, search engine, background job system, stream pipeline, or workflow engine in v4.6.

### Expected Features

v4.6 needs the minimum internal operating model required to change curriculum safely and prioritize fixes using existing STOA learning evidence.

**Must have (table stakes):**
- Authoring lifecycle states with explicit draft, review, approved, published, archived semantics.
- Role-scoped author, reviewer, and publisher permissions.
- Completeness validation before review or publish.
- Preview vs live separation with no draft leakage into student or parent APIs.
- Versioned publish with rollback and append-only audit evidence.
- Archive or supersede instead of hard delete.
- QA worklist with blockers, state, reviewer, ownership, and priority.
- Usage and impact visibility before publish or archive.
- Bounded content analytics and QA issue flagging from outcomes.

**Should have (high-value differentiators for STOA):**
- Impact-ranked content health queue.
- Weak-topic to content-gap mapping using adaptive and assignment signals.
- Assignment-to-content feedback loop.
- Staged rollout hooks and reviewer guidance from analytics, if they fit without expanding scope.

**Defer (explicit v2+ scope):**
- Collaborative CMS features like comments, mentions, and multi-user editing.
- Broad BI/report builder or warehouse-scale analytics.
- Automatic AI publication or analytics-driven auto-unpublish.
- General experimentation platform.
- Rich text/WYSIWYG infrastructure and heavy editor translation layers.

### Architecture Approach

The recommended architecture is a three-layer extension of the current backend: keep published curriculum in the existing `PRACTICE` read model, add a separate curriculum operations layer for draft/version/audit/worklist state in the same DynamoDB table, and add a bounded analytics layer that records signals on existing write paths and serves aggregate admin/tutor views.

**Major components:**
1. Published curriculum read model — existing `practice` routes, `curriculum_service`, and `practice_repo` continue serving student-visible content only.
2. Curriculum operations layer — new admin curriculum router, authoring service, and ops repository manage draft, review, publish, rollback, archive, preview overlay, and audit.
3. Curriculum analytics layer — new analytics service and repository record append-only signals and materialize aggregate topic/lesson/exercise/subject metrics.

**Key patterns:**
- Published projection plus draft overlay for authorized preview only.
- Immutable versions plus conditional publish/rollback instead of in-place mutation.
- Signal-on-write analytics instead of request-time scans.
- Explicit action endpoints for publish/archive/rollback, not a generic state patch.

### Critical Pitfalls

1. **Changing public lesson or exercise IDs during publish** — keep stable public IDs and introduce separate immutable `version_id` values; publish by moving a published-version pointer.
2. **Draft or review content leaking into student/parent APIs** — keep student reads on published projections only and add deny-by-default visibility tests.
3. **Partial publish or rollback across lesson/exercise rows** — define a publish unit and manifest, then use conditional writes and append-only audit evidence.
4. **Analytics derived from mutable rows or wide request-time scans** — record append-only signals and read from bounded aggregate rows.
5. **Archive or rollback breaking active assignments and historical progress/report views** — block unsafe archive, preserve resolvable published snapshots, and keep historical references intact.

## Implications for Roadmap

Based on research, v4.6 should be planned as four tightly ordered phases. Lifecycle contract and publish safety come before analytics. Analytics depends on stable IDs, version semantics, and clean role boundaries.

### Phase 1: Authoring Contract And Lifecycle Model
**Rationale:** This locks the public ID vs version contract, state machines, validation rules, and publish unit before any endpoints mutate curriculum.
**Delivers:** Curriculum ops schemas, transition matrix, draft/review/publish/archive/rollback contract, legacy-readiness rules, and audit requirements.
**Addresses:** Authoring lifecycle, permissions, completeness validation, publish evidence.
**Avoids:** ID breakage, overloaded state machines, legacy-content validation failures.

### Phase 2: Admin Authoring MVP And Publish Safety
**Rationale:** Internal authoring becomes usable only after publish and rollback are safe and published reads remain stable.
**Delivers:** Admin curriculum router, ops repo, authoring service, worklist, preview overlay, immutable versions, conditional publish/rollback, archive guards, published projection writers.
**Addresses:** Preview/live separation, rollback safety, QA queue, audit trail, usage visibility.
**Avoids:** Draft leakage, partial publish, stale post-publish reads, archive breaking active assignments.

### Phase 3: Curriculum Analytics Foundation
**Rationale:** Analytics should instrument stable lifecycle and content identifiers, not shape them.
**Delivers:** Append-only curriculum signals, aggregate rollups, analytics service, admin/tutor analytics endpoints, impact ranking for confusing exercises, weak topics, stale lessons, and coverage gaps.
**Addresses:** Actionable content analytics, QA issue flagging, assignment-to-content feedback, weak-topic mapping.
**Avoids:** Mutable-history analytics, full-table-scan dashboards, mixed-source metrics, privacy leakage.

### Phase 4: Release Gate, Backfill, And Verification
**Rationale:** The milestone is operationally sensitive and must prove compatibility with v3.8 curriculum and v4.0 assignment behavior before release.
**Delivers:** Backfill or recompute path for analytics verification, role-boundary tests, publish idempotency tests, rollback/archive verification, draft-isolation coverage, and docs updates.
**Addresses:** Release confidence and operational readiness.
**Avoids:** Happy-path-only validation, broken historical references, silent analytics drift.

### Phase Ordering Rationale

- Stable content identity and lifecycle semantics are prerequisites for every later decision.
- Publish safety must exist before staff can use authoring against live curriculum.
- Analytics should consume the finalized lifecycle and projection model, not compete with it.
- Release verification must explicitly cover regressions against existing student, parent, progress, and assignment flows.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Legacy content readiness and exact validation rules for existing v3.8 lessons/exercises need repo-specific auditing.
- **Phase 2:** Publish-unit boundaries and rollback semantics for lesson-plus-exercise bundles need careful code-level mapping.
- **Phase 3:** Event granularity, cohort-threshold privacy rules, and source-type segmentation need explicit design choices.

Phases with standard patterns:
- **Phase 2 router/service/repository split:** Established by current admin/report operation patterns.
- **Phase 4 verification:** Established by current pytest + moto testing style and existing curriculum rollout tests.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Strongly grounded in the current repo and clear non-requirement for new infrastructure. |
| Features | HIGH | Table stakes align with established education-platform patterns and STOA's milestone scope. |
| Architecture | HIGH | Direct fit with existing route/service/repository boundaries and current DynamoDB usage. |
| Pitfalls | HIGH | Major risks were derived from concrete STOA data-model and lifecycle interactions. |

**Overall confidence:** HIGH

### Gaps to Address

- Legacy v3.8 content may not satisfy stricter publish validation; planning should include a readiness audit and remediation path.
- The exact publish bundle boundary for lesson/exercise hierarchies must be defined before implementation begins.
- Analytics needs an explicit decision on synchronous same-table rollups versus a later backfill/recompute helper; v4.6 should start synchronous unless testing proves it unsafe.
- Role mapping for author, reviewer, and publisher should be validated against existing tutor/admin auth capabilities before route implementation.

## Sources

### Primary
- `.planning/research/STACK.md`
- `.planning/research/FEATURES.md`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/PITFALLS.md`
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `src/stoa/routers/admin.py`
- `src/stoa/routers/practice.py`
- `src/stoa/services/curriculum_service.py`
- `src/stoa/services/adaptive_learning_service.py`
- `src/stoa/db/repositories/practice_repo.py`
- `src/stoa/db/repositories/report_repo.py`
- `tests/test_curriculum_rollout.py`
- `tests/test_admin_report_ops.py`

### External references reflected in the research
- Open edX publishing, preview, and library update documentation
- Moodle question bank and quiz statistics documentation
- AWS DynamoDB best-practice and read-consistency documentation
- xAPI and Caliper event-model references for immutability guidance

---
*Research completed: 2026-06-12*
*Ready for roadmap: yes*
