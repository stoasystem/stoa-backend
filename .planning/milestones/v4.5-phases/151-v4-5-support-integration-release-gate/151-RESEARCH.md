# Phase 151: v4.5 Support Integration Release Gate - Research

**Researched:** 2026-06-12  
**Domain:** Support handoff release-gate evidence, fail-closed verification, and remaining-work closeout  
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Inputs

- **Phase Goal:** `Close v4.5 with support-integration verification, privacy evidence, refusal-path checks, and updated remaining-feature planning.` [VERIFIED: phase context]
- **Completed v4.5 Scope:** [VERIFIED: phase context]
  - `Phase 148 defined the support destination contract, selected internal_queue, and kept third-party destinations refused.`
  - `Phase 149 implemented fail-closed internal_queue delivery, metadata-only delivery records, idempotency independent of package UUIDs, and refused records for contract-defined unapproved destinations.`
  - `Phase 150 implemented admin-only delivery queue/detail visibility, recent feed rows, pre-feed read-through coverage, bounded audit timelines, full lifecycle status visibility, and read-only retry eligibility.`
- **Release Gate Requirements:** [VERIFIED: phase context]
  - `Focused backend/frontend checks pass for the selected delivery path, refusal paths, queue/status visibility, and existing manual fallback.`
  - `Release evidence captures destination configuration status with secrets redacted, provider/write deferral or approval state, and privacy validation results.`
  - `Tests prove unapproved destinations, missing credentials, provider failures, duplicate retries, and privacy violations fail closed.`
  - `Requirements, roadmap, state, feature-gap audit, and remaining-feature queue reflect completed v4.5 scope and unresolved support integration work.`
- **Release Evidence To Produce:** [VERIFIED: phase context]
  - `A v4.5 support integration release gate artifact under this phase directory.`
  - `Verification command results for focused support handoff tests, full admin report ops tests, and Ruff on touched files.`
  - `A concise privacy evidence section covering metadata-only package, delivery, queue, and audit outputs.`
  - `A release posture section:` `internal_queue` implemented but fail-closed behind `SUPPORT_INTERNAL_QUEUE_APPROVED`; third-party destinations remain refused; retry mutation remains deferred; manual `preview`, `copy`, `download`, and `external_write` package-route behavior remains preserved. [VERIFIED: phase context]
- **Gate Decision Bias:** `If verification passes, mark v4.5 locally complete but explicitly note unresolved production/external-provider work. If a privacy or fail-closed test fails, block release completion and fix before milestone audit.` [VERIFIED: phase context]

### the agent's Discretion

- No explicit `## the agent's Discretion` section exists in `151-CONTEXT.md`. [VERIFIED: phase context]

### Deferred Ideas (OUT OF SCOPE)

- No explicit `## Deferred Ideas` section exists in `151-CONTEXT.md`; out-of-scope work remains additional providers, two-way sync, SLA analytics, and broader CRM/customer messaging from `VERIFY-28` future requirements. [VERIFIED: repo docs]
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VERIFY-28 | Close v4.5 with focused verification, redacted release evidence, fail-closed tests, and remaining-feature updates. [VERIFIED: repo docs] | This research defines the exact release-gate artifact sections, the commands to run, the evidence to capture, the one meaningful coverage nuance, and the remaining-work handoff items. [VERIFIED: repo code][VERIFIED: local command] |
</phase_requirements>

## Summary

Phase 151 is a release-gate/docs closeout over an already-implemented backend slice: manual `preview`/`copy`/`download` handoff packages still originate in `support_handoff_service`, while `internal_queue` delivery, refused destination records, queue/detail visibility, pagination, and read-only retry visibility already exist in the current backend code and test suite. [VERIFIED: repo code][VERIFIED: repo tests]

The local gates required by the phase context are currently green: `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` passed with `28 passed, 85 deselected in 1.51s`, `./.venv/bin/pytest -q tests/test_admin_report_ops.py` passed with `113 passed in 4.77s`, and Ruff passed on the touched support files. [VERIFIED: local command]

The main release-gate work is evidence assembly, not new implementation. The artifact should explicitly record the fail-closed posture that is visible in code today: `support_internal_queue_approved` defaults to `False`, contract-defined third-party destinations are refused before evidence reads, retry remains visibility-only, and persisted delivery rows/audit events are metadata-only summaries rather than raw payload snapshots. [VERIFIED: repo code]

**Primary recommendation:** Produce a `151-RELEASE-GATE.md` that cites the three passing local gates, captures redacted package/delivery/audit evidence, records the rollout posture verbatim, and either adds or explicitly defers one provider-failure transition test before claiming strict `VERIFY-28` completion. [VERIFIED: local command][VERIFIED: repo code][ASSUMED]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Manual package fallback verification | API / Backend | Browser / Client | The authoritative behavior is the admin package route in `src/stoa/routers/admin.py`; any browser/UI proof is secondary and not represented in this backend workspace. [VERIFIED: repo code][ASSUMED] |
| Approved delivery-path gating (`internal_queue`) | API / Backend | Database / Storage | The router/service layer enforces destination allowlists and approval gates, while `report_repo` persists metadata-only summary/feed/audit rows. [VERIFIED: repo code] |
| Queue/detail visibility and audit pagination | API / Backend | Database / Storage | List/detail routes shape operator-visible responses from persisted summary/feed/audit rows and scoped page tokens. [VERIFIED: repo code] |
| Release posture and remaining-feature closeout | API / Backend | — | The release claims are justified by backend behavior plus planning docs, not by a new storage or browser tier. [VERIFIED: repo code][VERIFIED: repo docs] |

## Release Gate Artifact Contents

### Required Sections

1. `Status / Requirement / Recorded at` with a clear local-only vs production posture statement. Reuse the pattern from Phase 69 rather than inventing a new format. [VERIFIED: repo docs]
2. `Quality Gates` with the exact commands below and their literal results. [VERIFIED: local command]
3. `Release Posture` with these four facts verbatim: `internal_queue` implemented but gated by `SUPPORT_INTERNAL_QUEUE_APPROVED`; third-party destinations refused; retry mutation deferred/read-only; manual `preview`/`copy`/`download`/`external_write` package behavior preserved. [VERIFIED: phase context][VERIFIED: repo code]
4. `Privacy Evidence` showing that package, delivery summary, queue list, and audit detail remain metadata-only and redact credential/artifact markers. [VERIFIED: repo code][VERIFIED: repo tests]
5. `Fail-Closed Evidence Matrix` covering unapproved destination, approval-missing delivery, privacy failure, contract-defined refused destinations, unknown destination rejection, duplicate idempotent request, and read-only retry visibility. [VERIFIED: repo tests]
6. `Doc Closeout Checklist` naming `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`, and `.planning/NEXT-MILESTONES.md` as the docs Phase 151 must update on pass. [VERIFIED: repo docs]
7. `Remaining Feature Queue` listing additional providers, two-way synchronization/webhooks, SLA analytics, and broader CRM/customer messaging automation as future work. [VERIFIED: repo docs]

### Commands To Cite

| Command | Purpose | Current Result / Capture Requirement |
|---------|---------|--------------------------------------|
| `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` | Focused support handoff, refusal, queue/detail, and manual fallback regression gate. [VERIFIED: repo tests] | Current run: `28 passed, 85 deselected in 1.51s`; capture command, date, and output line. [VERIFIED: local command] |
| `./.venv/bin/pytest -q tests/test_admin_report_ops.py` | Full admin report operations regression guard. [VERIFIED: repo tests] | Current run: `113 passed in 4.77s`; capture command, date, and output line. [VERIFIED: local command] |
| `./.venv/bin/ruff check src/stoa/services/support_handoff_service.py src/stoa/services/support_destination_service.py src/stoa/routers/admin.py src/stoa/db/repositories/report_repo.py tests/test_admin_report_ops.py` | Static check for the touched v4.5 implementation/test surface. [VERIFIED: repo scope] | Current run: `All checks passed!`; capture command and output. [VERIFIED: local command] |

### Non-Command Evidence To Capture

- Approval-default proof: `support_internal_queue_approved: bool = False` in settings. [VERIFIED: repo code]
- Allowlist/refusal proof: manual package modes, `external_write` refusal, and contract-defined refused destinations. [VERIFIED: repo code]
- Privacy proof: sample response fields should show `payload_summary`, `privacy`, `evidence_reference_ids`, `refusal_reasons`, and `failure_reasons`, but no raw payload, report artifact keys, presigned URLs, cookies, or auth headers. [VERIFIED: repo code][VERIFIED: repo tests]
- Queue/detail proof: one list example and one detail example with audit pagination token behavior. [VERIFIED: repo code][VERIFIED: repo tests]
- Frontend note: because this workspace contains backend code only, the Phase 151 artifact should either reference existing support-handoff UI evidence from the earlier support-handoff release gate or attach separate frontend/browser smoke from the frontend repo before claiming full frontend completion. [VERIFIED: repo docs][ASSUMED]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `src/stoa/services/support_handoff_service.py` | repo current | Metadata-only manual package composition, privacy validation, and package audit writing. [VERIFIED: repo code] | This remains the authoritative manual fallback and privacy boundary for Phase 151 evidence. [VERIFIED: repo code] |
| `src/stoa/services/support_destination_service.py` | repo current | Fail-closed delivery/refusal orchestration, idempotency, lifecycle shaping, and retry visibility. [VERIFIED: repo code] | This is the authoritative source for release posture and delivery-state evidence. [VERIFIED: repo code] |
| `src/stoa/routers/admin.py` | repo current | Admin-only package, delivery, queue, and detail endpoints. [VERIFIED: repo code] | This is the authoritative entry-point surface for the release gate. [VERIFIED: repo code] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `src/stoa/db/repositories/report_repo.py` | repo current | Delivery summary/feed/audit persistence plus scoped pagination. [VERIFIED: repo code] | Use for queue/detail evidence and idempotent duplicate behavior. [VERIFIED: repo code] |
| `pytest` | `9.0.3` | Local verification runner for focused and full admin-report regressions. [VERIFIED: local command] | Use for the required release-gate command evidence. [VERIFIED: local command] |
| `ruff` | `0.15.14` | Focused static analysis gate on touched v4.5 files. [VERIFIED: local command] | Use for the required lint evidence. [VERIFIED: local command] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| A brand-new release-gate format | Reuse the Phase 69 release-gate structure and tailor the posture/evidence sections. [VERIFIED: repo docs] | Reuse keeps milestone artifacts consistent and reduces planning drift. [VERIFIED: repo docs] |
| A new bespoke verification suite | Reuse `tests/test_admin_report_ops.py` as the single gate surface and add only one missing edge test if needed. [VERIFIED: repo tests] | This preserves narrow scope and avoids duplicating existing coverage. [VERIFIED: repo tests] |

**Installation:** No new packages are required for Phase 151 research or closeout. [VERIFIED: repo scope]

**Version verification:** Local tool versions confirmed in this workspace: `pytest 9.0.3`, `ruff 0.15.14`, `node v26.0.0`. [VERIFIED: local command]

## Architecture Patterns

### System Architecture Diagram

```text
Admin request
  -> POST /admin/reports/support-handoff-package
     -> build_package()
     -> private_marker_hits()
     -> write_audit_event()
     -> metadata-only package response

Admin request
  -> POST /admin/reports/support-handoff-delivery
     -> reject unknown destination (422)
     -> refuse contract-defined unapproved destination OR approval-missing delivery
     -> build_package()
     -> deliver_internal_queue()
     -> persist summary + feed + audit
     -> metadata-only delivery response

Admin request
  -> GET /admin/reports/support-handoff-deliveries
     -> feed query + pre-feed fallback scan
     -> support_handoff_delivery_response()

Admin request
  -> GET /admin/reports/support-handoff-deliveries/{delivery_id}
     -> summary point read + bounded audit query
     -> support_handoff_delivery_audit_response()
```

### Recommended Project Structure

```text
.planning/phases/151-v4-5-support-integration-release-gate/
├── 151-CONTEXT.md        # locked phase goal and required release evidence
├── 151-RESEARCH.md       # this research artifact
└── 151-RELEASE-GATE.md   # recommended closeout artifact to produce in execution

src/stoa/
├── routers/admin.py                     # package/delivery/list/detail endpoints
├── services/support_handoff_service.py  # manual package/privacy boundary
├── services/support_destination_service.py
└── db/repositories/report_repo.py

tests/
└── test_admin_report_ops.py             # focused/full verification surface
```

### Pattern 1: Refuse Before Evidence Reads
**What:** Reject unknown destinations with `422`, and persist refused records for contract-defined-but-unapproved destinations before recovery evidence is queried. [VERIFIED: repo code]  
**When to use:** Any unsupported or not-yet-approved support destination. [VERIFIED: repo code]  
**Example:**
```python
# Source: src/stoa/routers/admin.py:1330
if destination not in contract_defined_destinations:
    raise HTTPException(status_code=422, detail=f"Unsupported destination mode: {destination or 'missing'}")

if destination in support_destination_service.CONTRACT_DEFINED_REFUSED_DESTINATIONS:
    delivery = support_destination_service.refuse_destination(...)
    return {"package": None, "delivery": delivery}
```

### Pattern 2: Persist Metadata-Only Delivery Summaries
**What:** Store digests, reference IDs, privacy summaries, and lifecycle status, but not raw package sections or outbound payload bodies. [VERIFIED: repo code]  
**When to use:** Every delivery summary and audit event returned to operators or cited in release evidence. [VERIFIED: repo code]  
**Example:**
```python
# Source: src/stoa/services/support_destination_service.py:276
record = {
    "delivery_id": delivery_id,
    "package_id": package_id,
    "status": status,
    "privacy": privacy,
    "evidence_reference_ids": evidence_reference_ids,
    "payload_digest": payload_digest,
    "payload_summary": {
        "schema_version": payload["schema_version"],
        "tags": payload["tags"],
        "section_summaries": payload["section_summaries"],
    },
}
```

### Anti-Patterns to Avoid

- **Claiming live provider delivery:** `support_internal_queue_approved` defaults to false, so Phase 151 must not present queueing as live external-provider rollout. [VERIFIED: repo code]
- **Treating retry visibility as retry mutation:** the code exposes retry metadata only; no retry endpoint exists in `admin.py`. [VERIFIED: repo code]
- **Capturing raw payloads in the release artifact:** operator responses are intentionally reduced to metadata-only fields, and the release artifact should preserve that boundary. [VERIFIED: repo code][VERIFIED: repo tests]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Privacy scanning for release-gate evidence | A new ad-hoc denylist pass in the release artifact. [VERIFIED: repo scope] | Existing `_redact_text()` / `_safe_text()` plus `release_evidence_service.private_marker_hits()`. [VERIFIED: repo code] | The current implementation already drives package and delivery privacy refusal behavior. [VERIFIED: repo code] |
| Duplicate-delivery suppression | A manual release-gate spreadsheet of duplicates. [ASSUMED] | Existing deterministic `idempotency_key` and `put_support_handoff_delivery_record()` semantics. [VERIFIED: repo code] | Idempotency is already the runtime contract and is covered by tests. [VERIFIED: repo code][VERIFIED: repo tests] |
| Retry execution workflow | A Phase 151 retry mutation endpoint or script. [VERIFIED: repo code] | Keep retry visibility read-only and defer mutation to a later lifecycle-worker phase. [VERIFIED: repo code][VERIFIED: repo docs] | Phase 150 explicitly kept retry mutation out of scope. [VERIFIED: repo docs] |
| Third-party destination adapters | Partial Zendesk/Freshdesk/Help Scout wiring in a release-gate phase. [VERIFIED: repo docs] | Keep the contract-defined third-party modes refused until a separate secret-backed provider phase. [VERIFIED: repo code][VERIFIED: repo docs] | The milestone requirement explicitly keeps broader provider work future-scoped. [VERIFIED: repo docs] |

**Key insight:** Phase 151 should validate the existing fail-closed runtime contract and document the remaining queue, not widen the integration surface. [VERIFIED: repo code][VERIFIED: repo docs]

## Common Pitfalls

### Pitfall 1: Over-claiming Frontend Completion
**What goes wrong:** The release artifact says `backend/frontend checks pass` even though this workspace contains backend code only. [VERIFIED: repo docs][ASSUMED]  
**Why it happens:** `VERIFY-28` carries frontend wording forward from broader milestone closeout language, but the phase inputs and executable surface here are backend-only. [VERIFIED: repo docs][ASSUMED]  
**How to avoid:** Either attach separate frontend/browser smoke from the frontend repo or explicitly reference prior support-handoff UI evidence instead of implying new frontend validation happened here. [VERIFIED: repo docs][ASSUMED]  
**Warning signs:** No frontend command, repo path, or artifact is present in the Phase 151 workspace. [VERIFIED: repo scope][ASSUMED]

### Pitfall 2: Treating Approval-Missing As Credential-Backed Delivery
**What goes wrong:** `internal_queue` is described as enabled even when the rollout flag is false. [VERIFIED: repo code]  
**Why it happens:** The route persists a refused delivery row for approval-missing requests, which can be mistaken for a queued success. [VERIFIED: repo code]  
**How to avoid:** Always pair delivery evidence with the settings-default proof and the refused-response proof. [VERIFIED: repo code]  
**Warning signs:** `package` is `null`, `status` is `refused`, and `package_id` is `null` in the response. [VERIFIED: repo tests]

### Pitfall 3: Claiming Stronger Provider-Failure Coverage Than Exists
**What goes wrong:** The release artifact claims provider-failure fail-closed coverage even though v4.5 has no live third-party adapter and no focused test currently exercises `transition_delivery_status(status="failed", failure_reasons=[...])`. [VERIFIED: repo code][VERIFIED: repo tests]  
**Why it happens:** The queue/detail suite displays `failed` lifecycle states, but display coverage is weaker than an executed failure transition. [VERIFIED: repo tests]  
**How to avoid:** Add one targeted lifecycle failure test or explicitly note that current v4.5 proves queued/refused/idempotent behavior while provider failure remains a simulated future-provider concern. [VERIFIED: repo code][VERIFIED: repo tests][ASSUMED]  
**Warning signs:** The only explicit lifecycle transition test currently uses `status="retried"`. [VERIFIED: repo tests]

## Code Examples

Verified patterns from the current codebase:

### Manual Fallback Route Stays Separate From Delivery
```python
# Source: src/stoa/routers/admin.py:1261
@router.post("/reports/support-handoff-package")
async def create_support_handoff_package(...):
    ...
    support_handoff_service.write_audit_event(...)
    return package
```

### Retry Visibility Is Explicitly Read-Only
```python
# Source: src/stoa/services/support_destination_service.py:331
if record.get("destination_mode") != INTERNAL_QUEUE_DESTINATION:
    return {"enabled": False, "reason": "destination is not approved for retry", "count": retry_count}
if status in {"refused"}:
    return {"enabled": False, "reason": "refused deliveries are not retryable", "count": retry_count}
if not retryable:
    return {"enabled": False, "reason": "delivery state is not retryable", "count": retry_count}
```

### Recommended Verification Commands
```bash
./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff
./.venv/bin/pytest -q tests/test_admin_report_ops.py
./.venv/bin/ruff check src/stoa/services/support_handoff_service.py src/stoa/services/support_destination_service.py src/stoa/routers/admin.py src/stoa/db/repositories/report_repo.py tests/test_admin_report_ops.py
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual package generation only (`preview`/`copy`/`download`) [VERIFIED: repo code] | One approved `internal_queue` delivery path plus persisted delivery summaries/audits. [VERIFIED: repo code] | Phase 149 completed 2026-06-12. [VERIFIED: repo docs] | v4.5 can close one controlled destination path without enabling third-party writes. [VERIFIED: repo docs] |
| `external_write` as the only refused mode surfaced to operators. [VERIFIED: repo code] | Contract-defined refused third-party destinations are persisted as refused delivery records. [VERIFIED: repo code] | Phase 149 completed 2026-06-12. [VERIFIED: repo docs] | Unapproved provider attempts now become auditable refusal evidence. [VERIFIED: repo code] |
| No operator queue/detail visibility for handoffs. [VERIFIED: repo docs] | Feed-backed recent list, detail view, audit pagination, lifecycle vocabulary, and pre-feed backfill. [VERIFIED: repo code] | Phase 150 completed 2026-06-12. [VERIFIED: repo docs] | Phase 151 can cite recent activity/status evidence instead of only package audit rows. [VERIFIED: repo code] |

**Deprecated/outdated:**

- Treating `external_write` as the only refused destination is outdated; Phase 149 introduced a larger contract-defined refused set. [VERIFIED: repo code][VERIFIED: repo docs]
- Treating retry as an executable operator action in v4.5 is outdated; Phase 150 kept it visibility-only. [VERIFIED: repo code][VERIFIED: repo docs]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The frontend portion of `VERIFY-28` must be satisfied by separate frontend/browser evidence or by explicitly referencing prior support-handoff UI verification, because no frontend code is in scope in this workspace. [ASSUMED] | Release Gate Artifact Contents; Common Pitfalls | The release gate could over-claim completion or miss a required browser smoke step. |
| A2 | The current duplicate-idempotency test is acceptable evidence for `duplicate retries` because retry mutation itself is deferred in v4.5. [ASSUMED] | Summary; Common Pitfalls | The planner may need to add an explicit retry-transition duplicate test or reword the closeout claim. |
| A3 | `VERIFY-28`'s provider-failure wording can be satisfied either by one added lifecycle failure test or by an explicit caveat that no live provider adapter exists in v4.5. [ASSUMED] | Summary; Open Questions | If a strict interpretation is required, the release gate would remain incomplete without an additional test. |

## Open Questions

1. **Should Phase 151 create a dedicated `151-RELEASE-GATE.md` file, or is a verification report plus summary enough?**
   - What we know: the context explicitly asks for `A v4.5 support integration release gate artifact under this phase directory`. [VERIFIED: phase context]
   - What's unclear: the exact filename is not prescribed in the inputs. [VERIFIED: phase context]
   - Recommendation: use `151-RELEASE-GATE.md` to stay consistent with prior release-gate milestones. [VERIFIED: repo docs]

2. **How should the team satisfy the `frontend` wording in `VERIFY-28` from this backend workspace?**
   - What we know: the current repo inputs, code, and commands are backend-only. [VERIFIED: repo scope]
   - What's unclear: whether the planner should treat prior frontend evidence as sufficient or require a fresh browser smoke from the frontend repo. [ASSUMED]
   - Recommendation: require an explicit decision in planning; do not silently omit it from the final artifact. [ASSUMED]

3. **Is one more support-handoff test needed before claiming full pass?**
   - What we know: current tests cover approval-missing, contract-defined refusal, privacy failure, duplicate idempotent creation, queue/detail visibility, invalid tokens, and retried transition visibility. [VERIFIED: repo tests]
   - What's unclear: whether `provider failures fail closed` needs a dedicated `status="failed"` transition test with non-empty `failure_reasons`. [ASSUMED]
   - Recommendation: add that single test if strict requirement language must be matched literally; otherwise document the caveat in the release artifact. [ASSUMED]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `pytest` | Focused/full admin verification | ✓ | `9.0.3` [VERIFIED: local command] | — |
| `ruff` | Touched-file lint gate | ✓ | `0.15.14` [VERIFIED: local command] | — |
| `node` | Existing GSD/planning helper commands | ✓ | `v26.0.0` [VERIFIED: local command] | — |
| Python project config | Test framework and tool settings | ✓ | `>=3.12` in `pyproject.toml` [VERIFIED: repo pyproject] | — |

**Missing dependencies with no fallback:**

- None for the backend-only Phase 151 research and local verification surface. [VERIFIED: local command][VERIFIED: repo pyproject]

**Missing dependencies with fallback:**

- Frontend/browser verification is outside this workspace; the fallback is to reference prior frontend support-handoff evidence if no fresh frontend smoke can be run. [VERIFIED: repo docs][ASSUMED]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.3` [VERIFIED: local command] |
| Config file | `pyproject.toml` with `tool.pytest.ini_options` [VERIFIED: repo pyproject] |
| Quick run command | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` [VERIFIED: local command] |
| Full suite command | `./.venv/bin/pytest -q tests/test_admin_report_ops.py` [VERIFIED: local command] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VERIFY-28 | Selected delivery path, refusal paths, queue/detail visibility, and manual fallback. [VERIFIED: repo docs] | integration | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` | ✅ [VERIFIED: local command] |
| VERIFY-28 | Full admin report ops regression coverage over the touched support surface. [VERIFIED: repo docs] | integration | `./.venv/bin/pytest -q tests/test_admin_report_ops.py` | ✅ [VERIFIED: local command] |
| VERIFY-28 | Touched-file lint/shape gate for the release surface. [VERIFIED: repo docs] | static | `./.venv/bin/ruff check src/stoa/services/support_handoff_service.py src/stoa/services/support_destination_service.py src/stoa/routers/admin.py src/stoa/db/repositories/report_repo.py tests/test_admin_report_ops.py` | ✅ [VERIFIED: local command] |

### Sampling Rate

- **Per task commit:** `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` [VERIFIED: local command]
- **Per wave merge:** `./.venv/bin/pytest -q tests/test_admin_report_ops.py` [VERIFIED: local command]
- **Phase gate:** Focused support-handoff pytest, full admin-report pytest, and touched-file Ruff all green before writing the release artifact. [VERIFIED: local command]

### Wave 0 Gaps

- [ ] Optional but recommended: add one focused support-handoff test for `transition_delivery_status(status="failed", failure_reasons=[...])` if the team wants literal proof for `provider failures fail closed`. [VERIFIED: repo code][VERIFIED: repo tests][ASSUMED]
- [ ] Planning decision: explicitly resolve how frontend/browser verification is satisfied for `VERIFY-28`. [VERIFIED: repo docs][ASSUMED]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes [VERIFIED: repo code] | Admin routes depend on authenticated `require_role("admin")`. [VERIFIED: repo code] |
| V3 Session Management | no new phase-specific session work [VERIFIED: repo scope] | Reuse existing application auth/session behavior. [VERIFIED: repo scope] |
| V4 Access Control | yes [VERIFIED: repo code] | Package, delivery, queue, and detail endpoints are admin-only. [VERIFIED: repo code] |
| V5 Input Validation | yes [VERIFIED: repo code] | Destination allowlists, bounded query params, and scoped pagination token decoding. [VERIFIED: repo code] |
| V6 Cryptography | no new secret-handling or crypto protocol surface [VERIFIED: repo code] | Existing SHA-256 digests are audit correlation fingerprints, not a new credential/security protocol. [VERIFIED: repo code] |

### Known Threat Patterns for the Current Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Raw artifact or secret leakage in handoff evidence | Information Disclosure | `_redact_text()`, `_safe_text()`, metadata-only response shaping, and `private_marker_hits()` checks. [VERIFIED: repo code] |
| Unsupported destination writes | Tampering | Router destination allowlists plus contract-defined refusal records before evidence reads. [VERIFIED: repo code] |
| Duplicate delivery creation or retry abuse | Tampering / DoS | Deterministic idempotency key, conditional summary persistence, and read-only retry visibility. [VERIFIED: repo code] |
| Pagination token tampering | Tampering | Scoped token encoding/decoding with payload validation before repo access. [VERIFIED: repo code] |

## Sources

### Primary (HIGH confidence)

- `src/stoa/services/support_handoff_service.py` - manual fallback modes, privacy validation, and package audit flow. [VERIFIED: repo code]
- `src/stoa/services/support_destination_service.py` - refused destinations, approval gate behavior, idempotency, lifecycle shaping, retry visibility, and metadata-only delivery summaries. [VERIFIED: repo code]
- `src/stoa/routers/admin.py` - admin-only package/delivery/list/detail endpoints and pre-evidence refusal logic. [VERIFIED: repo code]
- `src/stoa/db/repositories/report_repo.py` - delivery summary/feed/audit persistence, pagination, and pre-feed fallback behavior. [VERIFIED: repo code]
- `tests/test_admin_report_ops.py` - focused regression evidence for queueing, refusal, privacy, idempotency, queue/detail visibility, invalid tokens, retry visibility, and manual package fallback. [VERIFIED: repo tests]
- Local commands run on 2026-06-12 - focused pytest, full pytest, Ruff, and tool-version checks. [VERIFIED: local command]

### Secondary (MEDIUM confidence)

- `.planning/milestones/v2.4-phases/69-v2.4-release-gate-and-live-verification/69-RELEASE-GATE.md` - prior release-gate artifact structure to reuse. [VERIFIED: repo docs]
- `.planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md` - destination/readiness contract and rollout posture baseline. [VERIFIED: repo docs]
- `.planning/phases/149-support-evidence-export-destination-integration/149-VERIFICATION.md` and `.planning/phases/150-operator-queue-and-handoff-status-visibility/150-VERIFICATION.md` - prior phase verification truths and command history. [VERIFIED: repo docs]

### Tertiary (LOW confidence)

- Frontend verification interpretation for `VERIFY-28`; this research could not inspect a frontend workspace in the current session. [ASSUMED]
- Strict interpretation of `provider failures` and `duplicate retries` relative to the current v4.5 read-only retry scope. [ASSUMED]

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH - the phase relies on stable repo-local modules and locally verified tool versions. [VERIFIED: repo code][VERIFIED: local command]
- Architecture: HIGH - the route/service/repository data flow is explicit and directly inspectable. [VERIFIED: repo code]
- Pitfalls: MEDIUM - the remaining ambiguity is around frontend evidence ownership and the strictness of the provider-failure requirement wording. [VERIFIED: repo docs][ASSUMED]

**Research date:** 2026-06-12  
**Valid until:** 2026-07-12 for repo-local architecture; revisit sooner if Phase 151 adds new provider adapters or frontend acceptance steps. [VERIFIED: repo scope][ASSUMED]
