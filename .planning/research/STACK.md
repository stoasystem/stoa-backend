# Technology Stack: v4.6 Rich Curriculum Authoring And Analytics Foundation

**Project:** STOA backend
**Researched:** 2026-06-12
**Scope:** Stack additions and changes needed for internal curriculum authoring, QA lifecycle, publication safety, and bounded learning/content analytics in the existing FastAPI/DynamoDB backend.

## Executive Recommendation

v4.6 should stay on the existing Python 3.12 + FastAPI + Pydantic + DynamoDB single-table stack. The backend already has the right architectural shape for this milestone: route contracts in FastAPI, validation in Pydantic, service-layer lifecycle logic, and DynamoDB-backed state machines with audit trails.

The main change is not a new framework. It is a new set of DynamoDB entity families and service modules:

1. A curriculum operations layer for draft/review/publish/archive/rollback.
2. Same-table analytics rollups for content-level signals.
3. Focused admin/tutor APIs that keep published student-facing curriculum reads stable.

Do not add a CMS, warehouse, search engine, or separate analytics database in v4.6. Those would solve problems this milestone does not yet have and would cut across the repo's established patterns.

## Current Stack To Keep

| Technology | Current repo state | v4.6 decision | Purpose | Why |
|------------|--------------------|---------------|---------|-----|
| Python | 3.12 (`pyproject.toml`) | Keep | Runtime | No v4.6 requirement needs a runtime change. |
| FastAPI | Existing dependency (`fastapi>=0.115.0`) | Keep | Admin/tutor/student APIs | Current routers already cleanly separate role-scoped endpoints and match frontend contracts. |
| Pydantic v2 | Existing dependency (`pydantic[email]>=2.7.0`) | Keep | Request/response validation | Lifecycle state models, publish requests, rollback requests, and analytics filters fit the current model style. |
| boto3 / DynamoDB | Existing dependency (`boto3>=1.34.0`) | Keep | Persistence | Existing repos already use point reads, queries, scans, conditional updates, and append-only child items. |
| pytest + pytest-asyncio + moto | Existing dev stack | Keep | Tests | Existing curriculum, admin, and adaptive test patterns are enough for v4.6 coverage. |

## Required Additions Inside The Existing Stack

### 1. Add a Dedicated Curriculum Operations Repository Layer

Do not overload [`src/stoa/db/repositories/practice_repo.py`](src/stoa/db/repositories/practice_repo.py) with authoring lifecycle state. That repo is currently a published-content read model backed by `PK=PRACTICE` and student progress/mistake records. It is optimized for catalog reads, not editorial workflow.

Add a separate repository module, e.g. `curriculum_ops_repo.py`, with same-table entities such as:

| Entity family | Example key shape | Why |
|---------------|-------------------|-----|
| Content meta | `PK=CURRICULUM#<content_id>`, `SK=META` | Current mutable draft/review state, owner, reviewer, latest revision pointer, published pointer, optimistic version. |
| Immutable revisions | `PK=CURRICULUM#<content_id>`, `SK=REVISION#<n>` | Required for publish safety, rollback, and auditability. |
| Audit events | `PK=CURRICULUM#<content_id>`, `SK=AUDIT#<timestamp>#<event_id>` | Matches existing append-only lifecycle patterns already used elsewhere in the repo. |
| Optional review feed rows | `PK=CURRICULUM_REVIEW`, `SK=STATE#<state>#UPDATED#<timestamp>#<content_id>` | Only if internal queue listing needs queryable ordering without a GSI. |

Recommendation:
keep published student-facing lesson/exercise rows in the existing `PRACTICE` projection and publish by writing or updating those projection rows from an approved revision. That preserves the current read path in [`src/stoa/services/curriculum_service.py`](src/stoa/services/curriculum_service.py).

Why this is needed:

- Current curriculum reads already assume published projection data and preview filtering, not editorial state transitions.
- Student visibility is currently controlled by `rollout_state` and `includePreview` in [`src/stoa/routers/practice.py`](src/stoa/routers/practice.py) and [`src/stoa/services/curriculum_service.py`](src/stoa/services/curriculum_service.py).
- v4.6 must keep draft content isolated from student-visible catalog responses.

### 2. Use Conditional Writes And Immutable Revisions, Not A Workflow Engine

No new workflow/orchestration library is needed.

Implement state transitions with:

- optimistic version fields on `META` items
- DynamoDB conditional writes for legal transitions
- append-only audit child rows
- publish/rollback operations that repoint the published projection from a specific revision

This matches the repo's existing operational style better than adding Temporal, Step Functions, or a generic state-machine library.

Recommended lifecycle states:

- `draft`
- `in_review`
- `changes_requested`
- `approved`
- `published`
- `archived`

Recommended publish contract:

1. Validate the revision payload.
2. Confirm the current `META` version and allowed transition with a conditional write.
3. Write the published `PRACTICE` projection from that revision.
4. Append an audit event.

Rollback should not mutate arbitrary fields in place. It should republish a prior immutable revision into the published projection and record a new audit event.

### 3. Add Same-Table Content Analytics Rollups

This is the most important data change for v4.6.

The current learning evidence is mostly keyed per student:

- `PROGRESS#<user_id>` lesson completion rows
- `MISTAKES#<user_id>` wrong-attempt rows
- adaptive assignments and memory snapshots per student

That is good for per-student reads, but weak for operational analytics like:

- "Which exercises are most confusing across students?"
- "Which lessons go stale after publish?"
- "Which topics produce many skips or assignment failures?"

Do not solve that by adding a warehouse. Solve it with lightweight rollups in the same DynamoDB table.

Recommended rollup entities:

| Rollup scope | Example key shape | Counters |
|--------------|-------------------|----------|
| Exercise daily | `PK=CURRICULUM_ANALYTICS#EXERCISE#<exercise_id>`, `SK=DAY#YYYY-MM-DD` | attempts, wrong_attempts, correct_attempts, skips, assignments_completed |
| Lesson daily | `PK=CURRICULUM_ANALYTICS#LESSON#<lesson_id>`, `SK=DAY#YYYY-MM-DD` | completions, assignments_started, assignments_completed |
| Topic daily | `PK=CURRICULUM_ANALYTICS#TOPIC#<topic_id>`, `SK=DAY#YYYY-MM-DD` | weak_signals, practice_volume, assignment_failures |
| Publish snapshot | `PK=CURRICULUM_ANALYTICS#PUBLISH#<content_id>`, `SK=REVISION#<n>` | first_seen_at, publish_at, archive_at, last_activity_at |

Implementation guidance:

- Update these counters synchronously in the existing write paths.
- Reuse DynamoDB atomic counter patterns already present in the repo.
- Keep rows small and additive. v4.6 needs operational ranking, not raw event replay.

Best integration points:

- [`src/stoa/db/repositories/practice_repo.py`](src/stoa/db/repositories/practice_repo.py): lesson completion and wrong-attempt writes
- [`src/stoa/services/adaptive_learning_service.py`](src/stoa/services/adaptive_learning_service.py): assignment start/complete/skip/archive transitions
- new curriculum authoring service: publish/archive/rollback lifecycle signals

### 4. Add A Curriculum Analytics Service, Not A New Analytics Platform

Add a backend service module, e.g. `curriculum_analytics_service.py`, that combines:

- same-table rollups
- published curriculum metadata
- bounded existing adaptive or learning-profile signals when needed

Recommended outputs for v4.6:

- weak topics by subject
- confusing exercises by wrong-answer rate or repeated assignment failure
- stale lessons by published age versus low activity
- content gaps by high weak-topic volume with low published exercise coverage

This service should return privacy-safe aggregates only. No individual student detail is needed for v4.6 admin/tutor analytics.

## Existing Patterns To Reuse Directly

### Published vs preview visibility

The current curriculum APIs already separate published and preview access:

- [`src/stoa/routers/practice.py`](src/stoa/routers/practice.py) gates `includePreview` and `rolloutState`
- [`src/stoa/services/curriculum_service.py`](src/stoa/services/curriculum_service.py) only treats `active` content as visible by default

That means v4.6 does not need a new publication framework. It needs a stronger source-of-truth behind the existing visibility gate.

### Reviewable lifecycle items

The tutor AI draft workflow already demonstrates a useful pattern:

- explicit statuses
- reviewer identity and timestamps
- immutable regenerate behavior
- archive without delete

Reuse that editorial shape for curriculum content, but with stronger publish/rollback guarantees.

### Structured content validation

If lesson explanations, hints, or review notes need richer structure, use validated JSON blocks like the teacher reply formatter instead of introducing raw HTML or markdown parsing infrastructure. The repo already has a formula-safe structured content pattern.

Recommendation:
keep v4.6 authoring payloads as structured JSON and plain text fields. Defer WYSIWYG/editor-format translation.

## Small Code-Level Changes Worth Making

These are not new dependencies, but they are worthwhile stack adjustments for v4.6:

| Change | Decision | Why |
|--------|----------|-----|
| New `curriculum_ops_repo.py` | Add | Keeps editorial workflow separate from published catalog reads. |
| New `curriculum_authoring_service.py` | Add | Concentrates transition rules, validation, publish, rollback, and audit logic. |
| New `curriculum_analytics_service.py` | Add | Keeps analytics aggregation out of routers and `practice_repo`. |
| Pydantic models for authoring and analytics | Add | Needed for lifecycle requests, validation errors, and admin/tutor response contracts. |
| Reuse existing test stack | Keep | No new test framework is justified. |

## What Does Not Need To Be Added In v4.6

### Do not add a new runtime dependency just for v4.6

No new library is clearly required for:

- state machines
- workflow orchestration
- analytics math
- admin validation
- curriculum payload serialization

The current stack is enough.

### Do not add new infrastructure yet

Defer all of the following:

| Category | Do not add now | Why |
|----------|----------------|-----|
| CMS | Strapi, Directus, Wagtail, custom editorial UI backend framework | v4.6 is internal authoring MVP on an already opinionated FastAPI backend. |
| Analytics warehouse | Redshift, BigQuery, Snowflake, Athena lakehouse pipeline | Requirement explicitly says keep analytics bounded before BI/warehouse work. |
| Search/secondary store | OpenSearch, Elasticsearch, separate Postgres read model | Authoring and analytics needs do not justify an extra persistence plane yet. |
| Background job stack | Celery, Redis, separate worker fleet | Synchronous rollups and admin operations are enough for this scope. |
| Stream pipeline | DynamoDB Streams + Lambda analytics fanout | Useful later, but premature before analytics shapes stabilize. |
| Rich text/rendering stack | Markdown parser, WYSIWYG conversion libs, HTML sanitization layer for authoring | Structured JSON fields are safer and simpler for MVP. |
| Pandas/NumPy | Dataframe-style aggregation in API path | Overkill for bounded operational counters. |

## GSI And Infra Guidance

Recommended default:
do not add a new GSI in the first v4.6 implementation if review queues stay small.

Reason:

- the repo already accepts bounded scans for some internal/admin operations
- this milestone is internal-only and research-first
- one more GSI is cheaper than a new database, but still an infra change that should be justified by a concrete access pattern

If scan pain appears, add only one targeted index first:

| Candidate index | Use | When to add |
|-----------------|-----|-------------|
| `GSI-CurriculumWorkflow` (`workflow_state` + `updated_at`) | list drafts/review queues across all content | Add only if scan-based internal queue listing becomes slow or operationally noisy. |

Do not add an analytics GSI first. Model analytics as queryable rollup partitions instead.

## Testing Stack Decision

Keep the current testing stack and extend it with focused v4.6 suites:

- route contract tests for authoring and analytics endpoints
- service tests for lifecycle transitions and refusal paths
- repository tests for conditional publish/rollback and rollup counters
- visibility tests proving draft content never leaks into student catalog reads

No new test library is required. Existing pytest + moto patterns are enough.

## Final Recommendation

Build v4.6 entirely inside the current FastAPI/DynamoDB architecture.

Add:

- a separate curriculum operations repository/service layer
- immutable revision and audit items in the existing single table
- same-table analytics rollups written from existing learning and authoring events

Do not add:

- a CMS
- a warehouse
- a second database
- a workflow engine
- a background job system
- new runtime dependencies without a concrete gap

The first scale escape hatch, if v4.6 proves successful, should be one targeted workflow GSI or a stream-driven rollup pipeline later. It should not be a platform rewrite now.

## Sources

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `pyproject.toml`
- `src/stoa/routers/admin.py`
- `src/stoa/routers/practice.py`
- `src/stoa/db/repositories/practice_repo.py`
- `src/stoa/db/repositories/adaptive_learning_repo.py`
- `src/stoa/services/curriculum_service.py`
- `src/stoa/services/adaptive_learning_service.py`
- `src/stoa/services/ai_teacher_tools_service.py`
- `src/stoa/services/teacher_reply_service.py`
- `src/stoa/services/rate_limit.py`
- `tests/test_curriculum_rollout.py`
