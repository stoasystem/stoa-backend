# Roadmap: v5.21 AI Teaching Quality Cost And Safety Operations

**Status:** Completed
**Created:** 2026-07-06
**Prior milestone:** v5.20 Native Build Distribution And Device QA

## Goal

Move AI teacher tools, automatic summaries, draft explanations, practice generation, and assignment suggestions from reviewed local features into measurable quality, cost, safety, escalation, and teacher-oversight operations.

## Why This Follows v5.20

AI teaching flows already exist in reviewed/bounded form, but fully autonomous behavior remains deliberately deferred. After web, backend, observability, and native distribution are stable, the next risk is not adding more AI surfaces blindly; it is making existing AI behavior measurable, controllable, support-visible, and safe enough for broader product use.

## Product Purpose

- Teachers can trust AI summaries and generated exercises because quality is measured against rubrics and golden fixtures.
- Operators can see AI provider cost, latency, failure, refusal, and fallback behavior.
- Students and parents get AI-supported learning that remains bounded by teacher oversight and clear escalation paths.

## Implementation Strategy

- Start with a reality audit of every AI generation, summary, assignment, tutoring, and fallback path.
- Keep review-before-use as the default unless a specific autonomy level is approved and measured.
- Add evaluation fixtures before expanding generation scope.
- Add provider cost/latency/failure observability and budget controls.
- Close with AI release evidence that separates quality failure, provider blocker, safety refusal, and product regression.

## Phases

- [x] **Phase 277: AI Workflow Reality Audit And Autonomy Boundary** - Map all AI teacher, summary, exercise, assignment, fallback, and manual-review paths. (completed 2026-07-06)
- [x] **Phase 278: AI Quality Rubrics And Regression Fixtures** - Add golden fixtures, rubric scoring, review outcomes, and regression checks for summaries/exercises/explanations. (completed 2026-07-06)
- [x] **Phase 279: AI Cost Latency Provider Observability** - Add provider cost, latency, fallback, refusal, and budget-status summaries without raw prompt exposure. (completed 2026-07-06)
- [x] **Phase 280: AI Safety Escalation And Teacher Oversight** - Tighten safety boundaries, escalation states, teacher review queues, and student/parent explanations. (completed 2026-07-06)
- [x] **Phase 281: v5.21 AI Operations Release Gate** - Close with eval evidence, cost/safety evidence, known limitations, and next milestone decision. (completed 2026-07-06)

## Phase Details

### Phase 277: AI Workflow Reality Audit And Autonomy Boundary

**Goal**: Map all AI teacher, summary, exercise, assignment, fallback, and manual-review paths.
**Requirements**: AIOPS-01
**Success Criteria**:

1. AI-backed summaries, draft explanations, exercise generation, assignment suggestions, fallback content, and student-facing outputs are mapped to code/tests/owners/UI surfaces.
2. Each workflow is classified as reviewed, auto-visible, auto-assigned, support-only, fallback, blocked, or deprecated.
3. Paths that affect student work, quota, entitlement, teacher queue, or parent-visible progress have explicit autonomy levels.
4. Fully autonomous tutoring remains blocked unless approved criteria and evidence exist.

### Phase 278: AI Quality Rubrics And Regression Fixtures

**Goal**: Add golden fixtures, rubric scoring, review outcomes, and regression checks for summaries/exercises/explanations.
**Requirements**: AIOPS-02
**Success Criteria**:

1. Golden fixtures cover summary, explanation, exercise generation, assignment suggestion, refusal, fallback, and multilingual behavior.
2. Rubrics score correctness, age-appropriateness, curriculum alignment, language, hallucination risk, and actionable teacher value.
3. Review outcomes are support-safe.
4. Regression checks fail on missing fixtures, unsafe output, unreviewed publication, or unsupported autonomy claims.

### Phase 279: AI Cost Latency Provider Observability

**Goal**: Add provider cost, latency, fallback, refusal, and budget-status summaries without raw prompt exposure.
**Requirements**: AIOPS-03
**Success Criteria**:

1. AI provider calls expose bounded metadata for provider, model, workflow, latency, token/cost estimate, fallback, retry, refusal, and failure class.
2. Operator summaries show budget status, cost trend, latency/error trend, provider blocker, and fallback rate.
3. Evidence excludes raw prompts, student answers, tutoring transcripts, secrets, provider payloads, and high-cardinality private identifiers.
4. Runbook defines budget threshold, provider incident, fallback, and disable/rollback behavior.

### Phase 280: AI Safety Escalation And Teacher Oversight

**Goal**: Tighten safety boundaries, escalation states, teacher review queues, and student/parent explanations.
**Requirements**: AIOPS-04
**Success Criteria**:

1. Safety/refusal states are visible to teachers/operators without exposing raw unsafe content.
2. Teacher review queue distinguishes draft-ready, needs-review, refused, provider-blocked, stale, and failed states.
3. Student/parent copy explains AI limits and escalation status without technical leakage.
4. Human takeover/escalation integrates with teacher-help and support operations.

### Phase 281: v5.21 AI Operations Release Gate

**Goal**: Close with eval evidence, cost/safety evidence, known limitations, and next milestone decision.
**Requirements**: VERIFY-55
**Success Criteria**:

1. AI quality fixtures, regression checks, cost/latency summaries, safety escalation evidence, and teacher-oversight evidence are recorded.
2. Roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.
3. Remaining autonomy, provider, prompt-quality, language coverage, and production rollout blockers are explicit.
4. No new unreviewed student-facing AI publication is enabled without release approval.

## Future Milestone Directions

- **v5.22 Support CRM Customer Messaging And Lifecycle Automation**: use improved AI/support state to make parent onboarding, support messaging, and customer lifecycle operations usable.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AIOPS-01 | Phase 277 | Complete |
| AIOPS-02 | Phase 278 | Complete |
| AIOPS-03 | Phase 279 | Complete |
| AIOPS-04 | Phase 280 | Complete |
| VERIFY-55 | Phase 281 | Complete |
