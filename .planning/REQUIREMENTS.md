# Requirements: v3.4 Learning Expansion Foundation

**Milestone:** v3.4
**Status:** Active
**Created:** 2026-06-08

## Goal

Prepare Phase 2 learning expansion without jumping directly into a broad curriculum rollout. This milestone adds the foundation for multiple subjects, stable topic taxonomy, prompt behavior by subject, and student learning profile seeds from existing usage data. It is a product-building milestone; verification focuses on functional behavior and basic regression coverage.

## Requirements

### LEARN-01 Multi-Subject Taxonomy And Prompt Contract

Implementers have a precise subject/topic taxonomy, prompt behavior contract, and rollout boundary before backend changes.

Acceptance criteria:

- Contract defines supported subject identifiers for `math`, `physics`, `german`, and `english`, with MVP display labels and rollout states.
- Contract defines topic/knowledge-point taxonomy shape that can support weak-topic reporting and future exercises.
- Contract defines AI prompt behavior by subject, including language expectations and non-goals for full curriculum mastery.
- Contract defines how existing math-only question flows remain backward compatible.
- Contract confirms no new infrastructure is needed unless current DynamoDB access patterns cannot support topic/profile seeds.

### LEARN-02 Backend Subject/Topic Support And Student Profile Seeds

Backend records and exposes learning expansion foundations.

Acceptance criteria:

- Question submission validates supported subject identifiers and preserves existing math behavior.
- AI answer path receives subject-specific prompt context from the taxonomy contract.
- Backend stores normalized subject/topic metadata from AI responses and teacher/admin corrections where available.
- Student summary/profile APIs expose subject-level counts, weak-topic seeds, feedback averages, and teacher-escalation indicators.
- Focused tests cover subject validation, backward compatibility, summary/profile aggregation, and prompt context selection.

### UI-19 Student And Parent Learning Profile UI

Frontend exposes learning expansion foundations without pretending a full curriculum rollout is complete.

Acceptance criteria:

- Student question flow shows supported subject choices with rollout-aware labels.
- Parent/student profile views show subject-level activity, weak-topic seeds, and learning trend placeholders from real backend data.
- UI copy distinguishes active support from planned/future subject support.
- Empty/loading/error states are implemented for subject/profile data.
- Targeted browser verification confirms the workflow is usable.

### VERIFY-17 v3.4 Functional Release Gate And Expansion Audit

v3.4 closes with lightweight functional evidence and updated Phase 2 gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to learning expansion pass.
- Deploy/build evidence and commit SHAs are recorded if code ships in this milestone.
- Gap audit marks multi-subject foundation and student profile seeds as active/closed and records residual broad curriculum work.
- Final audit lists remaining Phase 2 product expansions: Stripe/TWINT, full curriculum rollout, AI teacher tools, realtime notifications, mobile/multilingual polish, and support integrations.

## Future Requirements

- Stripe/TWINT payment-provider integration.
- Full multi-subject curriculum content and exercises.
- Student memory/personalization beyond profile seeds.
- AI teacher assistance tools such as summaries and exercise generation.
- WebSocket realtime notifications.
- Mobile responsive polish and full multilingual rollout.

## Out of Scope

- Full physics/German/English curriculum content authoring.
- Automatic exercise generation.
- Long-term student memory/personalization decisions beyond profile seeds.
- Payment-provider implementation.
- Extensive security/compliance testing beyond functional role gating and data sanity checks.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| LEARN-01 | Phase 104 | Complete |
| LEARN-02 | Phase 105 | Complete |
| UI-19 | Phase 106 | Complete |
| VERIFY-17 | Phase 107 | Planned |
