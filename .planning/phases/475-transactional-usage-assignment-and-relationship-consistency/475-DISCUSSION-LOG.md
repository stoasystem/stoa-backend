# Phase 475: Transactional Usage Assignment And Relationship Consistency - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-21
**Phase:** 475-Transactional Usage Assignment And Relationship Consistency
**Areas discussed:** Question submission and recovery, concurrent teacher takeover, parent/student relationship and profile concurrency, rate limits/mistakes/delivery/deletion replay

---

## Question Submission And Recovery

| Question | Options considered | Selected |
|----------|--------------------|----------|
| Ambiguous submission result | Recoverable processing state; immediate rollback failure; visible failure with silent background recovery | Recoverable processing state |
| Long-running recovery | Durable processing item and background convergence; force user to wait; hide after timeout | Durable processing item and background convergence |
| Proven terminal failure | Restore question allowance, reverse ledger, retain uploaded attachment; delete attachment; retain charge for admin repair | Restore allowance and retain reusable attachment |
| Changed retry payload | Reject reuse and require a new submission identity; overwrite original; silently ignore changed content | Reject reuse and require a new identity |

**User's choices:** `1, 1, 1, 1`
**Notes:** The user selected the recommended convergence behavior in every question. Successfully uploaded attachments remain durable library resources and continue to count toward storage quota.

---

## Concurrent Teacher Takeover

| Question | Options considered | Selected |
|----------|--------------------|----------|
| Winner selection | First successful atomic backend claim; client click timestamp; multiple provisional owners | First successful atomic backend claim |
| Losing side effects | None; read-only session; attempted-takeover notification | None |
| Failure after ownership claim | Preserve winner and auto-complete missing effects; reopen competition; manual repair | Preserve winner and auto-complete missing effects |
| Winner identity visibility | Hidden from ordinary teachers and visible to admin; visible to all teachers; generic failure only | Hidden from ordinary teachers and visible to admin |

**User's choices:** `1, 1, 1, 1`
**Notes:** The partial-failure choice was restated with a concrete teacher-A example before confirmation: ownership remains with teacher A while the missing unique session/notification is completed safely.

---

## Parent/Student Relationships And Profile Concurrency

| Question | Options considered | Selected |
|----------|--------------------|----------|
| One-sided relationship authorization | Deny until both directions agree; authorize from either side; temporary grace authorization | Deny until both directions agree |
| Conflicting parent identities | Report for administrator decision; trust student row; trust parent row | Report for administrator decision |
| Repair execution | Preview, confirm, recheck versions, skip changed rows, idempotent replay; immediate mutation; preview count then overwrite | Preview, confirm, version-safe idempotent apply |
| Profile write/scrub race | Field-owned narrow changes with sensitive scrub winning same-field conflict; whole-record last writer wins; fail both | Field-owned changes with sensitive scrub priority |

**User's choices:** `1, 1, 1, 1`
**Notes:** `dry-run` was clarified as “只预览，不修改”; apply occurs only after administrator confirmation and does not overwrite records changed since preview.

---

## Rate Limits, Mistake Answers, Delivery, And Deletion Replay

| Question | Options considered | Selected |
|----------|--------------------|----------|
| Rate-limit counting | One count per admitted logical request, rejected/retried requests add none; count only complete answers; count every click | One count per admitted logical request |
| Legacy mistake answer | Explicit “not saved” unknown; hide answer section; substitute correct answer | Explicit unknown |
| Delivery-begin lookup failure | Terminalize only proven deletion and retry dependencies; cancel on any lookup failure; send regardless | Retry transient dependencies; cancel only proven deletion |
| Completed deletion replay | Return stored deleted receipt with no effects; account-not-found; create new deletion task | Return stored receipt with no effects |

**User's choices:** `1, 1, 1, 1`
**Notes:** Rate limiting was clarified with a 20-per-hour example: an admitted twentieth logical request counts once, its retry remains the twentieth, and rejected new requests do not inflate the counter.

## the agent's Discretion

- Internal transaction and command schemas, reconciliation scheduling, retry/lease values, exact safe code names and Web copy, and bounded submitted-answer normalization.

## Deferred Ideas

- Billing recovery remains Phase 476.
- Web presentation and complete browser role journeys remain Phases 477 and 478.
- Native/mobile work remains outside v9.0 until the Web product is stable.
