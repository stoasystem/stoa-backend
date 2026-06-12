# Feature Landscape

**Domain:** Internal curriculum authoring, QA lifecycle, publication safety, and learning/content analytics for STOA v4.6
**Researched:** 2026-06-12
**Overall confidence:** HIGH for lifecycle/publishing patterns, MEDIUM for analytics prioritization

## Scope Framing

STOA already has the learner-facing curriculum catalog and exercise-bank foundation from v3.8 plus adaptive memory, reviewed assignments, and progress signals from v4.0. v4.6 should not become a general CMS or BI platform. It should add the minimum internal operating model needed to create, review, publish, rollback, archive, and improve curriculum safely.

Typical education products split content into at least two worlds: editable draft content and learner-visible published content. Open edX currently documents draft editing, published content, published-with-pending-edits, preview/live views, role-scoped library access, and explicit sync/review of downstream updates before they affect courses. Moodle currently documents question banks with draft/ready status, version history, colleague comments, usage counts, “needs checking” flags, and psychometric/statistical review surfaces. Those are the right patterns to borrow.

For STOA, the differentiator should not be “more CMS.” It should be using existing STOA learning evidence to tell staff which lesson or exercise is actually underperforming, why it is likely underperforming, and what content should be reviewed next.

## Table Stakes

Features internal curriculum operations products are expected to have. Missing these creates content risk or makes authoring operationally brittle.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|--------------|------------|------------|-------|
| Authoring lifecycle states | Draft content must stay separate from student-visible content. | Medium | v3.8 curriculum content states and catalog visibility filters | Add explicit states for `draft`, `in_review`, `changes_requested`, `approved`, `published`, `archived`, plus `published_with_pending_edits` or equivalent. |
| Role-scoped author/reviewer/publisher permissions | Education teams separate content creation from final publication. | Medium | existing tutor/admin auth roles; likely new internal curriculum roles | Minimum roles: author, reviewer, publisher/admin. Avoid letting every tutor publish directly. |
| Content completeness validation | Staff need automated checks before review or publish. | Medium | existing lesson/exercise schemas and locale metadata | Require topic binding, difficulty, answer key, explanation/hints, content type, visibility metadata, and review notes before publish. |
| Preview vs live rendering | Reviewers need to see draft content exactly as a student would see it before release. | Medium | existing curriculum lesson/exercise detail APIs and preview-aware visibility | Draft preview must never leak into default student/parent catalog routes. |
| Versioned publish with rollback | Published mistakes are inevitable; recovery must be safe and fast. | High | v3.8 content model; STOA’s existing rollback/audit patterns from report operations | Publish should create immutable released versions or snapshots; rollback should repoint to a prior published version, not mutate history in place. |
| Archive/supersede instead of hard delete | Education content often remains referenced by progress, assignments, and analytics. | Medium | v3.8 progress history; v4.0 assignments | “Delete” should usually mean archive/inactivate for future use, while keeping historical references intact. |
| QA review queue | Staff need one place to see what needs review, re-review, or fixing. | Medium | authoring lifecycle; admin/tutor operational surfaces | Queue should show state, reviewer, subject/topic, last changed by, publish blocker count, and priority. |
| Usage and impact visibility | Changing an exercise blindly is dangerous once it is reused. | Medium | curriculum-to-assignment links; lesson/exercise IDs; parent/student progress surfaces | Show whether content is used in lessons, assignments, recommendations, or recent student activity before publishing or archiving. |
| Actionable content analytics | Internal authoring systems need more than CRUD; staff need signals for what to fix. | High | v3.8 progress/mistake data; v4.0 assignments/recommendations; weekly reports/weak topics | Start with bounded descriptive analytics at subject/topic/lesson/exercise level, not institution-wide BI. |
| QA issue flagging from outcomes | High wrong/skip/confusion rates should feed review workflows. | High | practice attempts, assignment outcomes, tutor feedback, moderation/report patterns | Analytics should be able to mark content as “needs checking” without auto-unpublishing it. |
| Publish/audit evidence | Internal publishing needs traceability: who changed what, why, and when. | Medium | existing admin audit/evidence patterns | Store reviewer decision, publisher, change summary, source version, rollback reason, and timestamps. |

## Differentiators

Features that are not strictly required for the first operable system, but are especially valuable for STOA because they leverage already-built adaptive and progress foundations.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Impact-ranked content health queue | Surfaces the highest-value fixes first instead of making staff browse raw reports. | High | Rank by wrong-rate, skip-rate, repeated mistakes, tutor escalations, assignment failures, and recommendation demand. |
| Content issue diagnosis hints | Helps staff distinguish “content is bad” from “topic is just hard.” | High | Example signals: high attempts + low mastery + strong tutor correction rate suggests lesson/exercise confusion; low usage suggests low confidence. |
| Assignment-to-content feedback loop | Makes reviewed assignments a source of curriculum improvement, not only student practice. | Medium | Accepted assignment results and tutor review outcomes should link back to lesson/exercise/topic health. |
| Weak-topic to content-gap mapping | Converts adaptive memory and parent weak-topic signals into authoring backlog. | Medium | Useful when topic weakness exists but lesson coverage or exercise volume is thin/stale. |
| Safe staged rollout | Lets STOA trial new content with controlled visibility before broad release. | High | Prefer subject/grade/tutor-preview rollout first; full cohort experimentation can wait. |
| Reviewer guidance generated from analytics | Speeds review by pre-filling likely issues, missing metadata, and regression risk. | Medium | Good use of STOA’s AI-adjacent foundations, but keep it advisory only. |

## Anti-Features

Features v4.6 should explicitly not build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Full collaborative CMS with comments, mentions, inline multi-user editing, and document-style discussions | Too much workflow/UI scope for the first internal authoring milestone. | Keep a simple author-reviewer lifecycle with review notes and decision history. |
| Broad BI/data warehouse/report builder | Expensive, open-ended, and not required to make curriculum operations usable. | Ship bounded operational analytics with fixed questions: what content is weak, stale, risky, or high-impact. |
| Automatic publication of AI-generated exercises or analytics-flagged edits | Unsafe for education quality and contradicts STOA’s reviewed-draft posture. | Allow AI or analytics to suggest drafts and review priorities; require human approval before publish. |
| Hard delete of published lessons/exercises | Breaks historical assignments, progress, analytics, and auditability. | Archive or supersede content and preserve historical IDs/version references. |
| Automatic propagation of changed content into all live downstream uses without review | Risks silent regressions in student-visible flows. | Use explicit publish plus accept/ignore or scoped sync for downstream usage. |
| Per-student surveillance dashboards for authors | Creates privacy risk and is unnecessary for content operations. | Keep author analytics aggregated; allow drilldown only when a tutor/admin already has legitimate role access. |
| General experimentation platform | Adds statistical and ethics complexity before the core authoring workflow is stable. | If needed later, start with manual staged rollout and explicit staff preview. |

## Complexity And Dependency Notes

- The hardest technical boundary is separating draft state from learner-visible published state without breaking existing v3.8 catalog, lesson detail, and progress APIs.
- Publication safety depends on versioning, not just status flags. A plain `state=published` toggle is not enough once assignments and analytics refer back to older content.
- Analytics should reuse existing STOA evidence first:
  - `curriculum_service.get_progress_summary`
  - `practice_repo.get_progress` and `practice_repo.get_mistakes`
  - adaptive memory snapshots and next-practice recommendations
  - reviewed assignment creation/progress/skip/archive flows
  - parent weak-topic and weekly report aggregation patterns
- Reviewer alerts can later integrate with notification infrastructure from v4.2, but notification delivery is not a hard dependency for the MVP.
- Publication audit and rollback flows should copy the design discipline from report operations: append-only evidence, explicit operator reason, rollback to prior version, and fail-closed behavior.
- Content analytics complexity grows quickly if STOA tries to infer pedagogy automatically. v4.6 should stay descriptive-first with some prioritization, not full predictive learning analytics.

## Feature Dependencies

```text
v3.8 curriculum catalog/content states
  -> v4.6 authoring lifecycle and draft storage
  -> QA review queue and publish validation
  -> versioned publish / rollback / archive safety

v4.0 adaptive memory + reviewed assignments
  -> content health analytics
  -> weak-topic / recommendation-demand signals
  -> assignment-to-content feedback loop

publish/version history
  -> safe rollback
  -> trustworthy analytics by published version
  -> future staged rollout
```

## MVP Recommendation

Prioritize:

1. Authoring lifecycle plus role-scoped permissions.
2. Publish validation, preview/live separation, and versioned publish/rollback/archive safety.
3. QA queue with review decisions, blockers, and audit history.
4. Bounded content analytics dashboard for topic/lesson/exercise health.

Defer:

- Collaborative commenting/workflow depth.
- Broad export/report builder work.
- Automatic rollout experiments.
- Full predictive analytics or warehouse-scale metrics.

## Recommended v4.6 Feature Shape

For STOA specifically, v4.6 should work like this:

1. An admin or authorized tutor creates or edits a lesson/exercise in draft.
2. The system validates completeness and refuses review/publish while critical fields are missing.
3. A reviewer previews the draft as a learner would see it, records approval or requested changes, and can reference analytics or prior issues.
4. Publishing creates a released version for student-facing catalog/assignment usage while preserving the draft/edit history.
5. If an issue appears later, staff can archive future use or roll back to a prior published version without rewriting history.
6. Analytics continuously rank topics, lessons, and exercises by confusion, weak-topic correlation, skip/failure rate, and assignment outcomes so staff know what to review next.

## Sources

- Internal project context:
  - `.planning/PROJECT.md`
  - `.planning/REQUIREMENTS.md`
  - `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`
  - `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`
  - `.planning/milestones/v3.8-ROADMAP.md`
  - `.planning/milestones/v4.0-ROADMAP.md`
- STOA codebase:
  - `src/stoa/services/curriculum_service.py`
  - `src/stoa/services/adaptive_learning_service.py`
  - `src/stoa/routers/adaptive.py`
- Official documentation:
  - Open edX, Publish Library content: https://docs.openedx.org/en/latest/educators/how-tos/course_development/publish_library_content.html
  - Open edX, Sync a Library update to your course: https://docs.openedx.org/en/latest/educators/how-tos/course_development/sync_a_library_update_to_your_course.html
  - Open edX, Preview Draft Content: https://docs.openedx.org/en/latest/educators/how-tos/preview_content.html
  - Open edX, View Published and Released Content: https://docs.openedx.org/en/latest/educators/how-tos/view_published_released_content.html
  - Open edX, Manage Course Beta Testing: https://docs.openedx.org/en/latest/educators/how-tos/releasing-course/manage_beta_testing.html
  - Open edX, Manage Library User Access: https://docs.openedx.org/en/latest/educators/how-tos/course_development/add_users_to_libraries.html
  - Moodle, Question banks: https://docs.moodle.org/502/en/Question_bank
  - Moodle, Analytics: https://docs.moodle.org/502/en/Learning_analytics
  - Moodle, Quiz statistics report: https://docs.moodle.org/502/en/Quiz_statistics_report
