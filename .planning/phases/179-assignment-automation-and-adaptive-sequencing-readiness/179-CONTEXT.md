# Phase 179 Context: Assignment Automation And Adaptive Sequencing Readiness

## Why This Phase Exists

STOA already supports adaptive memory summaries, next-practice recommendations, reviewed assignment workflows, curriculum progress, and aggregate content-quality analytics. Phase 179 defines how those foundations should support controlled assignment automation and future adaptive sequencing without bypassing review gates.

## Phase Boundary

This phase defines readiness and handoff. It does not enable fully autonomous tutoring, automatic publication of generated exercises, or broad warehouse-backed sequencing.

## Implementation Decisions

### Automation Posture

- Automation may propose assignments, but generated content remains review-gated.
- Reviewed curriculum exercises can be assigned directly by tutor/admin roles through existing assignment paths.
- Student/parent UI must distinguish recommendations from assigned work.
- Archived, rolled-back, draft, or review-only curriculum must not be newly assigned.

### Sequencing Signals

- Use curriculum progress, mistakes, adaptive memory snapshots, assignment outcomes, AI draft outcomes, tutor review state, and aggregate content-quality signals.
- Prefer deterministic eligibility and duplicate prevention before ranking sophistication.
- Treat long-term fully adaptive sequencing as future scope unless a later milestone selects it.

### Visibility

- Students see assigned/recommended work and their own progress.
- Parents see progress signals and assigned/completed counts for linked children.
- Tutors/admins see rationale, source, review state, and override controls.

## Existing Code Insights

- `adaptive_learning_service.create_assignment` creates reviewed assignments from `curriculum_exercise` or accepted AI draft sources.
- Assignment lifecycle supports draft, recommended, assigned, started, completed, skipped, and archived.
- Assignment completion/skipping records practice progress and aggregate content-quality signals.
- `curriculum_ops_service.archive` refuses active assignment references.
- `curriculum_analytics_service` records assignment completed/skipped and content quality signals.

## Deferred Ideas

- Fully autonomous sequencing engine.
- Warehouse-backed historical modeling.
- Automatic AI draft publication.
- Multi-armed bandit or ML ranking.
- Native/offline assignment queue.
