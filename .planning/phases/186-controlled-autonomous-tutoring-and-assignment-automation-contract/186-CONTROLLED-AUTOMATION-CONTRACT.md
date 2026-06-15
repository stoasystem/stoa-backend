# Controlled Autonomous Tutoring And Assignment Automation Contract

## Purpose

v5.3 converts adaptive sequencing into controlled assignment automation. The system may suggest, batch, and create reviewed assignments from eligible sources, but it must not publish unreviewed AI-generated work or replace tutor/admin judgment for high-stakes intervention decisions.

## Ownership

| Area | Owner | Responsibility |
|------|-------|----------------|
| Backend automation | `adaptive_learning_service` / new helper if needed | Policy evaluation, candidate batching, idempotent assignment creation, delivery-state metadata |
| AI draft source | `ai_teacher_tools_service` | Accepted practice exercise draft eligibility and review metadata |
| Curriculum source | `curriculum_service` / curriculum repositories | Published exercise eligibility and rollback/unpublished suppression |
| Analytics | `curriculum_analytics_service` | Automation attribution, coverage, refusal, delivery, skip, completion, and intervention metrics |
| Tutor/admin UX | Frontend handoff | Preview, approve, reject, override, pause, resume, and result-history flows |
| Student/parent UX | Frontend handoff | Assignment appearance, target explanation, tutor-approved/automated label, and progress summaries |
| Release | Phase 190 | Focused evidence, rollout state, and remaining-feature update |

## Autonomy Levels

| Level | Meaning | Creates assignments | Student-visible by default |
|-------|---------|---------------------|----------------------------|
| `off` | Automation disabled. | No | No |
| `suggest_only` | Planner returns candidates for tutor/admin review. | No | No |
| `tutor_approved_batch` | Tutor/admin approves a candidate batch before creation. | Yes, after approval | Optional by approved status |
| `auto_create_reviewed` | System creates assignments only from reviewed/eligible sources within approved policy. | Yes | Configurable assignment status |
| `future_auto_deliver` | Future level for unattended delivery. | Deferred | Deferred |

Default rollout should be `suggest_only` or `tutor_approved_batch`.

## Eligible Sources

- Accepted AI practice drafts where `draft_type=practice_exercise`, `status=accepted`, and `student_delivery_status` is not already terminal-delivered.
- Published curriculum exercises returned by the curriculum catalog/exercise APIs with active rollout state.
- v5.2 adaptive recommendation candidates with review-required metadata and sufficient confidence.

## Refusal And Suppression Rules

Candidates must be refused or suppressed when:

- Source content is unpublished, archived, rolled back, or missing.
- Candidate duplicates an active, assigned, started, recently completed, or archived exact source.
- Candidate is stale beyond the policy freshness window.
- Confidence is below policy threshold.
- Policy is paused, student/cohort is out of scope, or subject/topic/source type is excluded.
- Source is an AI draft that is not accepted/reviewed.
- Candidate would expose answer keys or internal ranking internals to student/parent payloads.

## Policy Shape

Minimum policy fields:

- `policyId`, `name`, `status`, `autonomyLevel`.
- `studentIds` or cohort selector.
- `subjectIds`, `topicIds`, and allowed source types.
- `maxAssignmentsPerStudent`, `confidenceThreshold`, `freshnessDays`, `dueInDays`.
- `deliveryMode`: `draft`, `recommended`, `assigned`, or future `delivered`.
- `createdBy`, `createdAt`, `updatedAt`, `pausedReason`.

## Batch Shape

Candidate batch response should include:

- `batchId`, `policyId`, `studentId`, `createdBy`, `createdAt`, `status`.
- `selected`: ordered candidate list with source type/id, title, subject/topic, confidence, rationale, expected impact, and proposed assignment status.
- `refused`: candidate list with refusal code and explanation.
- `summary`: selected/refused counts, top topics, duplicate count, low-confidence count, stale count, and review-required count.

## Assignment Creation And Delivery

Approved batches should:

- Create assignments idempotently by `batchId + candidateId + sourceType + sourceId + studentId`.
- Store automation metadata on assignments: `automationPolicyId`, `automationBatchId`, `automationLevel`, `automationReason`, `automationSourceSignals`.
- Return per-item results: `created`, `assigned`, `delivered`, `skipped`, `refused`, `duplicate`, or `failed`.
- Preserve existing assignment visibility: answer keys only for tutor/admin; parent summary-safe; student sees assignment work and plain explanation.

## Review UX And Family Visibility

Tutor/admin handoff must define:

- Batch preview with selected/refused candidates.
- Approve/reject/override/pause/resume actions.
- Result history and intervention views.

Student/parent handoff must define:

- Why assignment appeared.
- What subject/topic it targets.
- Whether it was tutor-approved or automation-created under policy.
- What to do next, without answer keys or internal ranking details.

## Rollout States

- `contract-ready`: v5.3 contract is accepted.
- `planner-ready`: policy and batch planner are implemented.
- `automation-ready`: approved batches can create assignments.
- `delivery-ready`: assignment delivery states and family/operator visibility are ready.
- `blocked`: strict prerequisite prevents progress.
- `deferred`: feature is intentionally postponed.

## Phase Handoff

- Phase 187 implements or finalizes policy and candidate batch planner behavior.
- Phase 188 implements idempotent assignment creation/delivery worker behavior.
- Phase 189 defines tutor/admin UX contracts and family-visible explanation surfaces.
- Phase 190 verifies release evidence and updates remaining-feature planning.
