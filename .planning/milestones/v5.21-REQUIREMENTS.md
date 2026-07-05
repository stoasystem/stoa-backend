# Requirements: v5.21 AI Teaching Quality Cost And Safety Operations

**Milestone:** v5.21
**Status:** Active
**Created:** 2026-07-06
**Prior milestone:** v5.20 Native Build Distribution And Device QA

## Purpose

Make AI teaching operations trustworthy before expanding autonomy. v5.21 should define autonomy boundaries, quality evaluation, provider cost/latency observability, safety escalation, teacher oversight, and release evidence for summaries, explanations, practice generation, and assignment suggestions.

## Requirements

### AIOPS-01 AI Workflow Reality Audit And Autonomy Boundary

Acceptance criteria:

- All AI-backed summaries, draft explanations, exercise generation, assignment suggestions, fallback content, and student-facing outputs are mapped to code, tests, owners, and UI surfaces.
- Each workflow is classified as reviewed, auto-visible, auto-assigned, support-only, fallback, blocked, or deprecated.
- Any path that can affect student work, quota, entitlement, teacher queue, or parent-visible progress has an explicit autonomy level.
- Deferred fully autonomous tutoring remains blocked unless approved criteria and evidence exist.

### AIOPS-02 AI Quality Rubrics And Regression Fixtures

Acceptance criteria:

- Golden fixtures cover at least summary, explanation, exercise generation, assignment suggestion, refusal, fallback, and multilingual behavior.
- Rubrics score correctness, age-appropriateness, curriculum alignment, language, hallucination risk, and actionable teacher value.
- Review outcomes are stored or exported in support-safe form.
- Regression checks fail on missing fixtures, unsafe output, unreviewed publication, or unsupported autonomy claims.

### AIOPS-03 AI Cost Latency Provider Observability

Acceptance criteria:

- AI provider calls expose bounded metadata for provider, model, workflow, latency, token/cost estimate, fallback, retry, refusal, and failure class.
- Operator summaries show budget status, cost trend, latency/error trend, provider blocker, and fallback rate.
- Evidence excludes raw prompts, student answers, tutoring transcripts, secrets, provider payloads, and high-cardinality private identifiers.
- Runbook defines budget threshold, provider incident, fallback, and disable/rollback behavior.

### AIOPS-04 AI Safety Escalation And Teacher Oversight

Acceptance criteria:

- Safety/refusal states are visible to teachers/operators without exposing raw unsafe content.
- Teacher review queue distinguishes draft-ready, needs-review, refused, provider-blocked, stale, and failed states.
- Student/parent copy explains AI limits and escalation status without technical leakage.
- Human takeover/escalation integrates with existing teacher-help and support operations.

### VERIFY-55 AI Operations Release Gate

Acceptance criteria:

- AI quality fixtures, regression checks, cost/latency summaries, safety escalation evidence, and teacher-oversight evidence are recorded.
- Roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.
- Remaining autonomy, provider, prompt-quality, language coverage, and production rollout blockers are explicit.
- No new unreviewed student-facing AI publication is enabled without release approval.

## Out of Scope

- Fully autonomous tutoring or auto-assignment without approved autonomy criteria.
- Raw prompt/answer warehouse exports.
- Replacing human teacher review for high-impact learning decisions.
- New AI providers that require unapproved credentials or data-processing agreements.
- Broad model training/fine-tuning.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AIOPS-01 | Phase 277 | Planned |
| AIOPS-02 | Phase 278 | Planned |
| AIOPS-03 | Phase 279 | Planned |
| AIOPS-04 | Phase 280 | Planned |
| VERIFY-55 | Phase 281 | Planned |
