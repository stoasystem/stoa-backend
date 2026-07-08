# Roadmap: v6.3 Learning Outcome And AI Curriculum Quality Sprint

**Status:** Completed
**Created:** 2026-07-07
**Prior milestone:** v6.2 Paid Conversion Usage And Account Reliability Completion

## Goal

Improve the core learning outcome from real pilot evidence: curriculum coverage, exercise quality, adaptive recommendations, AI summaries/exercises, teacher review, parent progress reporting, and first-week learning retention.

## Function Purpose

- Make STOA valuable because students learn, not because operations are merely ready.
- Turn real weak-topic, support, teacher, and parent feedback into curriculum and AI quality fixes.
- Keep curriculum editing and AI autonomy under explicit authorization/review.

## Implementation Strategy

- Prioritize high-frequency learning friction from pilot data.
- Use teacher review and evaluation fixtures for AI-generated summaries, explanations, and exercises.
- Improve family-visible explanations for recommendations and progress.
- Add regression tests and analytics tags for changed learning behavior.

## Phases

- [x] **Phase 387: Learning Outcome Evidence Review** - Analyze completion, retry, weak-topic, help, AI review, parent report, and support evidence.
- [x] **Phase 388: Curriculum Exercise And Explanation Quality Fixes** - Fill priority curriculum/exercise/explanation gaps with authorized review and rollback metadata.
- [x] **Phase 389: AI Teacher Summary And Practice Generation Quality Fixes** - Improve AI summaries, explanations, exercise drafts, refusal/fallback, and teacher review efficiency.
- [x] **Phase 390: Adaptive Recommendation And Parent Progress Clarity** - Improve recommendation freshness, dedupe, assignment explanations, and parent progress reporting.
- [x] **Phase 391: v6.3 Learning Quality Gate** - Decide scale, hold, or continue learning-quality remediation.

## Phase Details

### Phase 387: Learning Outcome Evidence Review

**Goal**: Analyze completion, retry, weak-topic, help, AI review, parent report, and support evidence.
**Depends on**: v6.2 revenue reliability gate.
**Requirements**: V6LEARN-01
**Success Criteria**:

1. Evidence covers completion, retry, mastery/progress, weak topics, teacher help, AI draft review, parent report engagement, and support contacts.
2. Learning problems are separated from account, payment, notification, and onboarding problems.
3. Top issues are ranked by student impact, frequency, severity, and effort.
4. Evidence remains support-safe and does not expose raw private student content.

### Phase 388: Curriculum Exercise And Explanation Quality Fixes

**Goal**: Fill priority curriculum, exercise, explanation, and metadata gaps through authorized content workflow.
**Depends on**: Phase 387.
**Requirements**: V6LEARN-02
**Success Criteria**:

1. Priority lessons, exercises, explanations, and metadata are improved through authorized content workflow.
2. Curriculum edit permissions remain limited to specially authorized operators.
3. Changed content has validation, preview, rollback metadata, and analytics tags.
4. Student/parent flows do not break sequencing or progress reporting.

### Phase 389: AI Teacher Summary And Practice Generation Quality Fixes

**Goal**: Improve AI summaries, explanations, exercise drafts, refusal/fallback, and teacher review efficiency.
**Depends on**: Phase 388.
**Requirements**: V6LEARN-03
**Success Criteria**:

1. AI summaries, explanations, exercise drafts, and teacher tools have updated evaluation fixtures.
2. Low-quality, unsafe, off-topic, or overconfident outputs are caught by review, refusal, or fallback behavior.
3. Teacher review supports accept, edit, reject, explain, and follow-up workflows efficiently.
4. Cost, latency, fallback, and provider errors remain observable.

### Phase 390: Adaptive Recommendation And Parent Progress Clarity

**Goal**: Improve recommendation freshness, dedupe, assignment explanations, and parent progress reporting.
**Depends on**: Phase 389.
**Requirements**: V6LEARN-04
**Success Criteria**:

1. Recommendations account for recent learning, weak topics, completed assignments, content availability, freshness, and duplicate suppression.
2. Parent/student explanations are understandable without exposing internal scoring or prompts.
3. Teachers/admins can correct recommendations and see why they were generated.
4. Parent progress reporting connects activity, outcome, next step, and support recommendation.

### Phase 391: v6.3 Learning Quality Gate

**Goal**: Decide scale learning scope, hold automation, continue remediation, or prepare larger cohort from learning quality evidence.
**Depends on**: Phase 390.
**Requirements**: VERIFY-77
**Success Criteria**:

1. Decision is scale learning scope, hold automation, continue remediation, or prepare larger cohort.
2. Decision uses learning outcome, parent comprehension, teacher review, AI quality, and support evidence.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. v6.4 receives remaining reliability and operations risks.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6LEARN-01 | Phase 387 | Completed |
| V6LEARN-02 | Phase 388 | Completed |
| V6LEARN-03 | Phase 389 | Completed |
| V6LEARN-04 | Phase 390 | Completed |
| VERIFY-77 | Phase 391 | Completed |
