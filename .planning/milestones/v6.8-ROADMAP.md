# Roadmap: v6.8 Learning Outcome And Curriculum Quality Expansion

**Status:** Completed
**Created:** 2026-07-09
**Prior milestone:** v6.7 Revenue Retention And Controlled Growth Execution

## Goal

Improve learning outcomes from real cohort evidence and prepare curriculum/AI quality for controlled growth. v6.8 focuses on student progress, weak topics, exercises, curriculum coverage, AI summaries/explanations, teacher tools, adaptive recommendations, and parent progress clarity.

## Function Purpose

- Make growth depend on visible learning value, not just operational readiness.
- Convert real student/parent/teacher/support evidence into curriculum and AI quality improvements.
- Keep special authorization and reviewed AI boundaries intact.

## Implementation Strategy

- Rank learning issues by frequency, severity, student impact, teacher effort, and parent confusion.
- Use authorized curriculum workflows and AI evaluation fixtures.
- Improve parent-visible progress and next-step explanations.
- Close with learning scale, hold, remediation, or content/AI freeze.

## Phases

- [x] **Phase 412: Real Learning Outcome And Weak Topic Analysis** - Analyze completion, retry, mastery/progress, weak topics, help, AI review, parent report, and support evidence.
- [x] **Phase 413: Curriculum Exercise Explanation Quality Release** - Ship authorized curriculum, exercise, explanation, metadata, sequencing, and rollback improvements.
- [x] **Phase 414: AI Teacher Summary Practice Quality Release** - Improve AI summaries, explanations, exercise drafts, refusal/fallback, teacher review, and cost/latency observability.
- [x] **Phase 415: Adaptive Recommendation And Parent Progress Release** - Improve recommendations, assignment explanations, parent progress reporting, corrections, and freshness/dedupe.
- [x] **Phase 416: v6.8 Learning Expansion Decision Gate** - Decide learning scale, hold, remediation, or content/AI freeze.

## Phase Details

### Phase 412: Real Learning Outcome And Weak Topic Analysis

**Goal**: Analyze completion, retry, mastery/progress, weak topics, teacher help, AI review, parent report, and support evidence.
**Depends on**: v6.7 revenue growth decision gate.
**Requirements**: V6LEARNEXEC-01
**Success Criteria**:

1. Evidence covers completion, retry, mastery/progress, weak topics, teacher help, AI draft review, parent report engagement, and support contacts.
2. Learning problems are separated from account, billing, notification, support, and onboarding problems.
3. Top issues are ranked by student impact, frequency, severity, and effort.
4. Evidence remains support-safe and excludes raw private student content.

### Phase 413: Curriculum Exercise Explanation Quality Release

**Goal**: Ship authorized curriculum, exercise, explanation, metadata, sequencing, and rollback improvements.
**Depends on**: Phase 412.
**Requirements**: V6LEARNEXEC-02
**Success Criteria**:

1. Priority lessons, exercises, explanations, metadata, and sequencing are improved through authorized content workflow.
2. Curriculum edit permissions remain specially authorized.
3. Changed content has validation, preview, rollback metadata, and analytics tags.
4. Student/parent flows preserve progress and recommendation integrity.

### Phase 414: AI Teacher Summary Practice Quality Release

**Goal**: Improve AI summaries, explanations, exercise drafts, refusal/fallback, teacher review, and cost/latency observability.
**Depends on**: Phase 413.
**Requirements**: V6LEARNEXEC-03
**Success Criteria**:

1. AI summaries, explanations, exercise drafts, and teacher tools have updated evaluation fixtures.
2. Low-quality, unsafe, off-topic, or overconfident outputs are caught by review, refusal, or fallback behavior.
3. Teacher review supports accept, edit, reject, explain, and follow-up workflows efficiently.
4. Cost, latency, fallback, refusal, and provider errors remain observable.

### Phase 415: Adaptive Recommendation And Parent Progress Release

**Goal**: Improve recommendations, assignment explanations, parent progress reporting, corrections, and freshness/dedupe.
**Depends on**: Phase 414.
**Requirements**: V6LEARNEXEC-04
**Success Criteria**:

1. Recommendations account for recent learning, weak topics, completed assignments, content availability, freshness, and duplicate suppression.
2. Parent/student explanations are understandable without exposing internal scoring or prompts.
3. Teachers/admins can correct recommendations and see why they were generated.
4. Parent progress reporting connects activity, outcome, next step, and support recommendation.

### Phase 416: v6.8 Learning Expansion Decision Gate

**Goal**: Decide learning scale, hold, remediation, or content/AI freeze.
**Depends on**: Phase 415.
**Requirements**: VERIFY-82
**Success Criteria**:

1. Decision is learning scale, hold, remediation, or content/AI freeze.
2. Decision uses learning outcome, parent comprehension, teacher review, AI quality, support load, and retention evidence.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. v6.9 receives market-readiness risks separately from learning-quality risks.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6LEARNEXEC-01 | Phase 412 | Completed |
| V6LEARNEXEC-02 | Phase 413 | Completed |
| V6LEARNEXEC-03 | Phase 414 | Completed |
| V6LEARNEXEC-04 | Phase 415 | Completed |
| VERIFY-82 | Phase 416 | Completed |
