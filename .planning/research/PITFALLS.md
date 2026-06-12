# Domain Pitfalls

**Domain:** STOA v4.6 Rich Curriculum Authoring And Analytics Foundation
**Researched:** 2026-06-12
**Confidence:** HIGH for STOA integration risks, MEDIUM for external analytics-pattern guidance

## Critical Pitfalls

### Pitfall 1: Re-keying published lessons or exercises breaks existing progress, assignments, and memory
**What goes wrong:** Authoring/publish work introduces new `lesson_id` or `challenge_id` values for edited content, or replaces old rows instead of versioning them.
**Why it happens:** STOA already stores student progress and mistakes against lesson/challenge identifiers in `practice_repo`, and adaptive assignments store `source_id`, `lesson_id`, and `exercise_id` directly. The v3.8 compatibility contract explicitly requires old identifiers to keep working.
**Consequences:** Students lose visible completion history, parents see inconsistent progress, adaptive memory stops matching current content, and archived assignments become unresolvable.
**Prevention:** Treat published content IDs as stable public IDs. Introduce separate immutable `version_id` values for authoring/publish history. Publish by moving a `published_version_id` pointer, not by changing the public lesson/exercise ID. Persist content version metadata on assignments and analytics events.
**Detection:** A publish of an edited lesson changes student-visible IDs, existing assignment links 404, or historical progress counts drop after publish.
**Primary phase:** Phase 152
**Must be enforced in:** Phase 153 and Phase 155

### Pitfall 2: Draft or reviewed content leaks into student/parent APIs
**What goes wrong:** Draft, seed, or review-only curriculum items appear in normal catalog, lesson detail, parent progress, or assignment flows.
**Why it happens:** STOA currently stores curriculum content in one shared `PRACTICE` space and relies on application-side visibility checks. `curriculum_service` only treats `active` as student-visible, while preview access is controlled by `include_preview`.
**Consequences:** Students can see incomplete exercises, wrong answer keys, or internal QA content; parents get progress against content that was never truly published; trust in the catalog drops quickly.
**Prevention:** Make published visibility an explicit contract, not just a filter flag. Add dedicated authoring/admin endpoints for non-published content. Keep student/parent endpoints reading only published projections or published-version pointers. Add tests that every non-`active` state is hidden from student/parent routes even when related entities are published.
**Detection:** A draft lesson appears in student catalog, exercise counts differ between catalog and lesson detail, or preview-only items show up in parent summaries.
**Primary phase:** Phase 152
**Must be enforced in:** Phase 153 and Phase 155

### Pitfall 3: Publish and rollback are multi-row, non-atomic, and leave mixed curriculum states
**What goes wrong:** A lesson publishes but some exercises stay old; rollback flips lesson metadata without restoring matching exercises; a partial failure leaves half the hierarchy on one version and half on another.
**Why it happens:** STOA stores subjects, topics, units, lessons, and challenges as separate rows. Current read paths assemble content by querying prefixes and filtering in code, so a naive publish can mutate several rows without one authoritative bundle boundary.
**Consequences:** Students see mismatched prompts and answer keys, analytics attribute attempts to the wrong content, and operators cannot trust rollback safety.
**Prevention:** Define a publish unit and version manifest in Phase 152. In Phase 153, implement preview/apply semantics with compare-and-set checks and append-only audit evidence, following the same safety pattern already used for report edit/rollback workflows. Publish should validate the whole bundle first, then switch one published pointer or manifest reference.
**Detection:** Lesson metadata `updated_at` changes without synchronized exercise changes, rollback restores only part of a lesson, or publish retries create duplicate “current” rows.
**Primary phase:** Phase 152
**Must be enforced in:** Phase 153 and Phase 155

### Pitfall 4: Content lifecycle and assignment lifecycle get conflated
**What goes wrong:** The system reuses generic states like `draft`, `reviewed`, `assigned`, or `archived` across curriculum content, AI drafts, and reviewed assignments without a single transition contract.
**Why it happens:** STOA already has content states from v3.8 and separate assignment states from v4.0. v3.7 AI exercise drafts also exist as another pre-publish artifact path.
**Consequences:** Illegal transitions slip through, authoring endpoints behave differently from assignment endpoints, and “reviewed” starts meaning different things in different APIs.
**Prevention:** Separate state machines by entity type in Phase 152:
- curriculum content lifecycle
- QA/review outcome lifecycle
- assignment lifecycle
- AI draft acceptance lifecycle

Define allowed transitions, required actor roles, refusal reasons, and audit fields for each. Do not overload assignment status fields to represent content publication state.
**Detection:** An accepted AI draft becomes publishable without curriculum review, archived assignments hide published content, or APIs disagree on what `reviewed` means.
**Primary phase:** Phase 152
**Must be enforced in:** Phase 153

### Pitfall 5: Analytics are computed from mutable content rows instead of immutable learning events
**What goes wrong:** Dashboards use current lesson/challenge rows and current progress rows as if they were historical facts. Editing or archiving content changes historical analytics retroactively.
**Why it happens:** Current STOA analytics-style signals are derived from mutable progress and mistake records. `mark_lesson_completed` overwrites a single completion row per lesson, and `record_attempt` only stores wrong attempts. That is enough for current product features, but not for content-quality analytics or rollback-safe reporting.
**Consequences:** “Confusing exercise” metrics drift after edits, improvement/regression trends become untrustworthy, and rollback can rewrite the story of past learning behavior.
**Prevention:** Introduce append-only learning/content interaction events in Phase 154. Every meaningful event should capture student, content public ID, content version ID, subject/topic, action, outcome, and timestamp. Build dashboards from rollups over those events, not by re-reading mutable content rows. This is an inference from xAPI/Caliper-style event models, not a requirement to adopt either standard directly.
**Detection:** Historical analytics change after content edits, published rollback alters last month’s weak-topic counts, or repeated reads of the same time range produce different numbers without new events.
**Primary phase:** Phase 154
**Must be prepared in:** Phase 152

### Pitfall 6: Operational analytics hammer the main DynamoDB table
**What goes wrong:** Admin analytics pages scan or wide-query the transactional table for every request.
**Why it happens:** Current STOA patterns already include broad prefix queries and at least one table `scan` for assignments. Adding analytics naively on top of the same table will amplify cost and latency.
**Consequences:** Student-facing reads slow down, admin dashboards time out, and traffic spikes from analytics starve core learning flows.
**Prevention:** In Phase 152, decide the read model before adding endpoints. In Phase 154, write analytics to a dedicated aggregate table or GSI-backed summary model through async rollups. Keep heavy recomputation out of request paths. Use pagination and bounded windows only. Do not ship a “live analytics” page backed by table scans.
**Detection:** Admin analytics endpoints show high p95 latency, `ProvisionedThroughputExceeded` or throttling appears during content dashboard use, or simple filters require full-table scans.
**Primary phase:** Phase 154
**Must be designed in:** Phase 152

### Pitfall 7: Archive or rollback breaks active assignments and parent/report history
**What goes wrong:** An exercise is archived or rolled back while students still have active assignments or while parent/report views still expect the old metadata.
**Why it happens:** STOA’s parent/report/adaptive flows already consume practice progress and assignment references. Archive safety is more than hiding catalog rows; history and active work still need a resolvable content snapshot.
**Consequences:** Students open dead assignments, parents see blank progress labels, weekly reports lose context, and operators cannot safely clean up bad content.
**Prevention:** Make archive a soft state for published content. Block archive when active assignments exist unless there is an explicit migration/repoint flow. Keep archived published versions readable for historical context. Rollback must restore a resolvable version manifest, not just toggle status flags.
**Detection:** Archived content still has open assignments, parent history shows empty titles/topic labels, or reports reference content IDs with no matching published snapshot.
**Primary phase:** Phase 153
**Must be verified in:** Phase 155

### Pitfall 8: Analytics expose sensitive student detail instead of operational aggregates
**What goes wrong:** Curriculum QA dashboards include raw student answers, named weak areas for very small cohorts, or answer-key-like detail in analytics exports.
**Why it happens:** v4.6 explicitly wants actionable analytics, and the easiest way to make them actionable is often to over-share row-level data. STOA also already allows preview roles to see answer keys in curriculum contexts.
**Consequences:** Parent/student trust is damaged, tutor/admin roles get more individual data than intended, and internal analytics become hard to expose safely.
**Prevention:** Treat analytics as a separate privacy surface in Phase 154. Use minimum cohort thresholds, aggregate by subject/topic/content version, redact free-text answers from dashboards, and keep detailed QA views admin-only. Preserve the existing “no answer keys for students/parents” boundary in every new analytics route.
**Detection:** Dashboard rows can be traced back to a single student, exports include raw response text, or tutor-visible analytics expose data that parents/students cannot already infer from existing product flows.
**Primary phase:** Phase 154
**Must be verified in:** Phase 155

## Moderate Pitfalls

### Pitfall 1: Legacy v3.8 curriculum is incomplete for a stricter authoring workflow
**What goes wrong:** Existing lessons/exercises from the v3.8 rollout fail new authoring validation because they lack hints, answer-key normalization, difficulty metadata, or language coverage fields expected by v4.6.
**Prevention:** Phase 152 should define required versus optional fields separately for legacy content and new authoring. Phase 153 should include a backfill/readiness report and a “needs remediation” state rather than forcing mass publish or mass archive.
**Primary phase:** Phase 152

### Pitfall 2: Metrics mix teacher-assigned work, recommendations, and organic practice
**What goes wrong:** “Weak topic” or “confusing content” dashboards combine student-initiated practice, teacher-assigned work, and AI-draft-sourced assignments as one metric.
**Prevention:** Phase 154 should segment every event and aggregate by source type: catalog self-practice, reviewed assignment, AI-draft assignment, skip, retry, and lesson completion. Do not compare these populations without labeling them.
**Primary phase:** Phase 154

### Pitfall 3: Publish confirmation reads stale data and operators mistrust the workflow
**What goes wrong:** An author publishes content, immediately re-reads, and sees old state or partial state.
**Why it happens:** DynamoDB reads are eventually consistent by default, and GSI reads are always eventually consistent.
**Prevention:** Phase 153 should use strongly consistent reads where post-publish confirmation depends on the base table, plus explicit version numbers in responses. Phase 155 should test read-after-publish and read-after-rollback behavior.
**Primary phase:** Phase 153

## Minor Pitfalls

### Pitfall 1: Admin router scope balloons into an unmaintainable mixed operations surface
**What goes wrong:** Curriculum authoring, QA, analytics, moderation, billing, and support operations all pile into one router/service shape.
**Prevention:** Phase 153 should split curriculum operations into dedicated router/service modules instead of expanding `admin.py` further.
**Primary phase:** Phase 153

### Pitfall 2: “Deeper analytics” scope sneaks into the foundation milestone
**What goes wrong:** v4.6 tries to become a data warehouse or BI milestone instead of an operational analytics milestone.
**Prevention:** Keep Phase 154 limited to decision-support dashboards for content quality, weak topics, stale lessons, and coverage gaps. Defer institutional reporting, cohort science, and broad warehouse pipelines.
**Primary phase:** Phase 154

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 152: Curriculum Authoring Contract And QA Workflow | Stable content IDs not separated from content versions | Define `public_id` vs `version_id`, publish manifest, and compatibility rules before writing endpoints |
| Phase 152: Curriculum Authoring Contract And QA Workflow | One overloaded state machine for content, QA, assignments, and AI drafts | Define separate lifecycles and transition matrices per entity type |
| Phase 152: Curriculum Authoring Contract And QA Workflow | New validation rules invalidate most v3.8 content | Add legacy-readiness audit and remediation state |
| Phase 153: Admin Lesson And Exercise Authoring MVP | Draft leakage into normal catalog/progress APIs | Route student/parent reads through published-only projections and add deny-by-default tests |
| Phase 153: Admin Lesson And Exercise Authoring MVP | Partial publish/rollback across lesson/exercise rows | Use preview/apply plus compare-and-set and append-only audit evidence |
| Phase 153: Admin Lesson And Exercise Authoring MVP | Archive breaks active assignments or history | Block archive with active dependencies; keep archived published versions resolvable |
| Phase 154: Learning Analytics And Content Quality Signals | Dashboards built from mutable rows and wide scans | Emit append-only events and async rollups into aggregate read models |
| Phase 154: Learning Analytics And Content Quality Signals | Metrics are misleading because source types are mixed | Segment by assignment source, recommendation source, and organic practice |
| Phase 154: Learning Analytics And Content Quality Signals | Analytics leak student-sensitive detail | Add cohort thresholds, role scoping, and no raw-answer exports |
| Phase 155: Curriculum Operations Release Gate | Only happy-path authoring is tested | Prove draft isolation, publish idempotency, rollback correctness, archive refusal, and analytics stability on edited content |

## Recommended Risk Order

1. Lock ID/version/publish semantics first in Phase 152.
2. Build safe authoring/publish/archive/rollback mechanics in Phase 153.
3. Only then add analytics in Phase 154, using immutable events and bounded aggregates.
4. Use Phase 155 to verify old v3.8/v4.0 behavior still works after authoring changes.

## Sources

### STOA repository
- `.planning/milestones/v3.8-phases/120-full-curriculum-rollout-contract-and-content-model/120-CURRICULUM-ROLLOUT-CONTRACT.md` lines 22-29, 71-90
- `.planning/milestones/v4.0-phases/128-adaptive-learning-memory-and-assignment-contract/128-ADAPTIVE-MEMORY-ASSIGNMENT-CONTRACT.md` lines 25-66
- `src/stoa/db/repositories/practice_repo.py` lines 37-104, 120-176
- `src/stoa/services/curriculum_service.py` lines 10-13, 15-99, 102-125, 143-148, 251-259
- `src/stoa/services/adaptive_learning_service.py` lines 32-67, 70-116, 119-195, 198-216
- `src/stoa/db/repositories/adaptive_learning_repo.py` lines 16-38, 41-86

### External references
- AWS DynamoDB best practices for query vs scan: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-query-scan.html
- AWS DynamoDB read consistency: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html
- 1EdTech Caliper Analytics overview: https://www.1edtech.org/standards/caliper
- ADL xAPI data model, especially statement permanence/immutability concepts: https://raw.githubusercontent.com/adlnet/xAPI-Spec/master/xAPI-Data.md
