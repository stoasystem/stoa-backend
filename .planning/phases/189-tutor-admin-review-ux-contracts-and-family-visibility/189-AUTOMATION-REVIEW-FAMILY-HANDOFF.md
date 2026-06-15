# Assignment Automation Review And Family Visibility Handoff

## Scope

This handoff defines how frontend, tutor/admin, student, parent, and operator surfaces should integrate controlled assignment automation from `stoa-backend`.

The backend is authoritative for candidate eligibility, duplicate prevention, assignment creation, delivery state, answer-key visibility, and role-scoped automation metadata. Frontend clients should not recreate ranking or duplicate rules client-side.

## API Contract

### Preview Batch

`POST /adaptive/students/{studentId}/assignment-automation/batches/preview`

Request:

```json
{
  "policy": {
    "policyId": "policy-linear-practice",
    "name": "Linear equations practice",
    "status": "active",
    "autonomyLevel": "tutor_approved_batch",
    "studentIds": ["student-1"],
    "subjectIds": ["math"],
    "topicIds": ["linear-equations"],
    "sourceTypes": ["ai_draft", "curriculum_exercise"],
    "maxAssignmentsPerStudent": 2,
    "confidenceThreshold": "medium",
    "freshnessDays": 14,
    "dueInDays": 7,
    "deliveryMode": "recommended"
  },
  "subject": "math"
}
```

Use `selected` for approvable rows and `refused` for non-actionable rows. Display `summary.refusalCounts`, `duplicateCount`, `lowConfidenceCount`, `staleCount`, and `reviewRequiredCount` as operator evidence.

Preview rows include:

- `candidateId`
- `sourceType`
- `sourceId`
- `title`
- `subject`
- `topicId` / `topicIds`
- `confidence`
- `rationale`
- `expectedImpact`
- `reviewStatus`
- `proposedStatus`
- `dueAt`
- `reviewRequired`
- `autonomousDecision`

Manager-only diagnostic fields such as `sourceSignals` may be shown in compact operator detail panels, but should not be copied into family-facing text.

### Execute Batch

`POST /adaptive/students/{studentId}/assignment-automation/batches/execute`

Request:

```json
{
  "batchId": "batch-abc123",
  "approved": true,
  "policy": { "...": "same policy used for preview" },
  "subject": "math",
  "candidates": [{ "...": "selected preview candidate" }]
}
```

Execution rules:

- `approved` must be explicit and true.
- If preview used `subject`, execute must submit the same `subject` so server-side preview binding compares the same candidate scope.
- `batchId` and candidate fields must match the current server-generated preview.
- A stale preview returns `409 Automation batch preview is stale`; the frontend should refetch preview and preserve operator notes locally until the operator decides again.
- Per-item statuses are `created`, `assigned`, `delivered`, `skipped`, `refused`, `duplicate`, or `failed`.
- Duplicate results are successful no-op outcomes, not fatal errors.
- Unsupported assignment sources such as memory-only planning candidates can appear as `refused`.

### Assignments And Progress

Use existing assignment routes after execution:

- `GET /adaptive/students/{studentId}/assignments?includeArchived=true`
- `GET /adaptive/assignments/{assignmentId}`
- `GET /adaptive/students/me/assignments`
- `GET /adaptive/parents/me/children/{studentId}/progress`

Manager assignment responses include `answerKey` and expanded `automation.sourceSignals`/`automation.resultEvidence`. Student and parent views must not display answer keys or manager-only source signals.

## Tutor/Admin Review UX

### Primary Flow

1. Select student/cohort, subject, topic, source types, max count, confidence threshold, freshness window, due window, and delivery mode.
2. Preview batch.
3. Review selected candidates with source, confidence, expected impact, due date, and review status.
4. Review refused candidates with refusal code and reason.
5. Optionally remove selected candidates locally by setting candidate `approved: false`.
6. Execute the batch with explicit approval.
7. Show per-item results and link to created assignments.
8. Refetch assignments and preview after execution.

### Controls

- Preview: available when policy status is `active`.
- Approve/execute: enabled only when selected candidates exist and operator has reviewed the current preview timestamp.
- Reject/remove: client-side candidate `approved: false`; backend records `skipped`.
- Override: change policy fields and rerun preview; do not mutate selected rows by hand except `approved`.
- Pause: set policy `status: paused` with `pausedReason`.
- Resume: set policy `status: active` and rerun preview.
- Off: set `autonomyLevel: off` or `status: off`; the preview should show refusal evidence and no execution control.
- Retry: resubmit the same execute payload only for network uncertainty; duplicate/refused/skipped replay is a safe terminal result.

### Empty And Error States

- No recommendations: "No reviewed next-work candidates are available from current learning signals."
- All refused: show refusal breakdown and the top actionable fix, such as lower max freshness, enable curriculum exercises, or resolve duplicate active work.
- Policy paused: show `pausedReason` and a resume action.
- Stale preview: refetch preview; do not auto-execute a changed batch.
- Duplicate/source conflict: treat as complete no-op and link to the existing assignment if returned.
- Failed source: show the item failure, keep other item results, and allow a new preview after source data is corrected.

## Family Visibility

### Student Explanation

Students may see `assignment.automation.explanation`, `deliveryState`, `reviewRequired`, and `autonomousDecision`.

Recommended display text:

- "Tutor-approved practice was assigned for {topic} based on recent learning signals."
- "Reviewed practice was prepared for {topic} based on recent learning signals."

Do not expose:

- `answerKey`
- raw `sourceSignals`
- ranking score or internal confidence math
- draft answer keys or teacher-only notes
- policy IDs as primary copy

### Parent Explanation

Parent surfaces should summarize:

- what topic the assignment targets
- whether the assignment is assigned/recommended/completed/skipped
- that the work was reviewed or tutor-approved
- progress counts and freshness from parent progress

Parent surfaces should not expose:

- answer keys
- student raw answers
- AI draft internals
- hidden ranking internals
- manager-only automation evidence

## Operator Analytics Contract

Operator dashboards should aggregate from preview/execute/assignment responses:

- automation coverage: students with active policies and recent previews
- selected/refused candidate counts
- refusal counts by code
- delivery result counts: created, assigned, delivered, skipped, refused, duplicate, failed
- assignment lifecycle outcomes: started, completed, skipped, archived
- duplicate/source conflict counts
- stale-preview counts
- intervention candidates: repeated low confidence, repeated stale evidence, high refusal counts, or assignments skipped after automation

Do not claim live warehouse/BI deployment from this handoff. Phase 189 defines the product contract; live BI integration remains a future frontend/analytics task.

## Frontend Follow-Up

In `/Users/zhdeng/stoa-frontend`, add or update:

- adaptive automation API client methods for preview and execute
- tutor/admin batch review page or panel
- policy editor controls
- selected/refused candidate table
- execute result drawer
- assignment detail automation explanation
- parent/student assignment explanation display
- no-demo-fallback handling for preview, execute, and assignment automation state

## Release Gates

Frontend/operator work is ready when:

- Preview and execute use backend-returned batch and candidate fields without client ranking.
- Stale previews require refetch and fresh approval.
- Duplicate/refused/skipped outcomes render as terminal item results.
- Student and parent views never show answer keys or manager-only automation evidence.
- Empty/no-automation/paused/off states are visible and non-blocking.
- Route and canonical value handling preserves backend locale metadata.
