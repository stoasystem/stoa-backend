---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 16
subsystem: ai-billing
tags: [bedrock, count-tokens, provider-usage, iam, redaction]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Canonical ProviderUsageEvidence and exact allowance ledger from Plan 15
provides:
  - Strict AIProviderResult content/usage boundary with actual provider input/output counts
  - Exact configured-profile admission counting through the observed Bedrock Runtime CountTokens capability
  - Exhaustive user-allowance versus provider-cost-only InvokeModel caller inventory
  - Non-mocked source/configuration/IAM-bound redacted CountTokens preflight evidence
affects: [476-17, 476-18, ai-admission, allowance-finalization, provider-cost-evidence]

tech-stack:
  added: []
  patterns:
    - Derive the foundation model from the configured system inference profile and bind both identities in evidence
    - Require exact runtime integers, HTTP success, and provider correlation before admitting a count or usage result
    - Keep Mantle available only through an explicit verified endpoint selection; never guess a fallback

key-files:
  created:
    - src/stoa/services/bedrock_token_count_service.py
    - scripts/probe_bedrock_token_count.py
    - tests/test_bedrock_usage_evidence.py
    - docs/security/phase-476-bedrock-token-count-preflight.json
  modified:
    - src/stoa/services/ai_service.py

key-decisions:
  - "Count the configured EU inference profile through Bedrock Runtime using its derived foundation model ID, while binding both model and profile identities in redacted evidence."
  - "Never infer Mantle from a CRIS prefix or automatically fall back after a Runtime failure; endpoint capability must be explicit and failure remains provider_token_count_unavailable."
  - "Return validated content separately from canonical ProviderUsageEvidence, and leave allowance reservation/finalization entirely outside ai_service."

patterns-established:
  - "Provider counts accept only exact nonnegative integers; bool, fraction, string, negative, missing, non-200, and uncorrelated responses fail closed."
  - "Preflight evidence contains only digests, exact synthetic count, action, source SHA, response classification, and timestamp."

requirements-completed: [V9BILL-04]

duration: 46min
completed: 2026-07-24
---

# Phase 476 Plan 16: Bedrock Token Evidence Boundary Summary

**Configured-profile admission now uses the observed exact Bedrock Runtime CountTokens path, while AI results carry strict provider-reported usage and a redacted source/configuration/IAM-bound receipt proves the capability.**

## Performance

- **Duration:** 46 min across an authentication checkpoint
- **Started:** 2026-07-24T11:18:12Z
- **Completed:** 2026-07-24T12:04:11Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Added a count-only Bedrock adapter that derives `anthropic.claude-sonnet-4-6` from the configured `eu.anthropic.claude-sonnet-4-6` profile, sends the identical InvokeModel body to Runtime `CountTokens`, and never estimates from characters or quota burndown.
- Changed the AI provider boundary to return frozen `AIProviderResult` values containing validated content plus canonical `ProviderUsageEvidence`, exact model/profile/correlation/stop/effect coordinates, and actual provider input/output counts.
- Rejected missing, boolean, fractional, negative, string, oversized, non-200, uncorrelated, or otherwise malformed counts with stable fail-closed categories before any allowance finalization.
- Classified all four direct `InvokeModel` callers: answer and hint are user allowance; title and weekly report are provider cost only. An AST inventory test fails on any unclassified addition.
- Captured a real count-only preflight with the approved non-production Identity Center profile. It returned exactly 37 synthetic input tokens and produced a passing, non-mocked, redacted receipt bound to source commit `f2a78337`.
- Proved that `ai_service.py` imports the Plan 15 `ProviderUsageEvidence` model and contains no reservation, provider observation, finalization, restoration, or allowance repository mutation.

## Task Commits

TDD execution and the provider-capability correction produced four focused commits:

1. **Task 476-16-01 RED: Add failing Bedrock usage evidence contract** - `85c73703` (test)
2. **Task 476-16-01 GREEN: Capture authoritative Bedrock token evidence** - `8f739b9c` (feat)
3. **Task 476-16-01 FIX: Count EU profile tokens through Bedrock Runtime** - `f2a78337` (fix)
4. **Task 476-16-01 EVIDENCE: Record Bedrock token count preflight** - `402f7f8a` (docs)

## Files Created/Modified

- `src/stoa/services/bedrock_token_count_service.py` - Exact count adapter, strict response parsing, Runtime selection, explicit Mantle capability, and stable unavailable error.
- `src/stoa/services/ai_service.py` - Typed provider result, canonical usage parsing, model/profile/message/stop evidence, and closed invocation classification.
- `scripts/probe_bedrock_token_count.py` - Count-only STS/IAM/config/source-bound capture and offline verification.
- `tests/test_bedrock_usage_evidence.py` - Provider shape, strict integer, endpoint selection, no-fallback, caller inventory, no-finalization, redaction, and source-drift selectors.
- `docs/security/phase-476-bedrock-token-count-preflight.json` - Passing redacted receipt containing no credentials, content, raw identity, request ID, or full model/profile ID.

## Decisions Made

- The configured EU system inference profile is an invocation coordinate, while its derived foundation model is the working Runtime CountTokens coordinate. Both are cryptographically bound in evidence so tokenization cannot drift from the invoked model/profile.
- A CRIS prefix does not by itself prove Mantle availability. Runtime is the observed configured capability; Mantle remains explicit for a separately verified model/account/region only.
- Runtime failure never triggers endpoint guessing or a local estimate. Governed admission receives `provider_token_count_unavailable`.
- Provider content remains in the in-memory content path. Durable usage evidence retains only canonical digests, exact counts, closed status, effect identity, and observation time.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the CRIS-wide Mantle endpoint assumption**
- **Found during:** Task 476-16-01 live count-only preflight
- **Issue:** The initial implementation forced every cross-Region inference profile through `bedrock-mantle`. In the approved account and `eu-central-2`, Mantle endpoints/projects returned 404 and Runtime CountTokens rejected the profile ID, while Runtime CountTokens with the profile's derived foundation model returned HTTP 200 and the official model capability supported token counting.
- **Fix:** Default configured-profile counting to Runtime with the derived foundation model, validate the profile/model binding, require HTTP 200 plus exact correlated usage, and keep Mantle only behind explicit selection with no automatic fallback.
- **Files modified:** `src/stoa/services/bedrock_token_count_service.py`, `scripts/probe_bedrock_token_count.py`, `tests/test_bedrock_usage_evidence.py`
- **Verification:** Runtime/profile binding, malformed Runtime response, no-fallback, explicit Mantle, live capture, and offline source/config verification selectors.
- **Commit:** `f2a78337`

---

**Total deviations:** 1 auto-fixed bug.
**Impact on plan:** The correction uses the provider capability actually available for the exact configured model while strengthening fail-closed endpoint selection and evidence binding.

## Authentication Gates

- **Task 476-16-01:** Execution paused before any real provider access because the original run authorized mocked/fixture tests only.
- **Resolution:** The user later authorized count-only validation with the active `stoa` Identity Center profile in `eu-central-2`.
- **Outcome:** STS identity resolution and Bedrock Runtime CountTokens succeeded. No InvokeModel/generation, production mutation, estimate, or private prompt was used.

## Security Verification

- `AIProviderResult.usage` is exactly the Plan 15 `ProviderUsageEvidence` model; prompt and answer bytes are absent from its serialized form.
- Provider usage parsing requires exact nonnegative input/output integers and validates message, model, stop, HTTP request, effect, and observation coordinates.
- Configured admission uses Runtime `CountTokens` against the exact InvokeModel body and the derived model bound to the configured profile.
- Runtime malformed/unavailable cases never call the explicit Mantle capability and never fabricate zero or an estimate.
- The probe dependency exposes count only; generation is unavailable in production and fail-if-called in fixtures.
- The published receipt is `passing`, `mocked=false`, uses `bedrock:CountTokens`, records 37 exact synthetic input tokens, and binds source/configuration/model/profile/IAM/correlation only through approved redacted fields.
- AST inventory proves every source `InvokeModel` caller has exactly one closed allowance class.
- `ai_service.py` contains no allowance counter mutation or debit finalization.

## Known Stubs

None.

## Issues Encountered

- The researched Mantle route was not available for this account/model/region combination. The source and evidence now use the successful official Runtime CountTokens capability instead.
- The first count-only capture attempt was blocked by sandbox network isolation; the authorized escalated count-only retry passed without expanding to generation or production operations.

## User Setup Required

- The approved `stoa` Identity Center profile and `eu-central-2` region were used only for this preflight.
- Re-run capture after any change to the count adapter, AI provider boundary, probe source, configured region, model, inference profile, or AWS identity. Offline verification fails closed on drift.

## Next Phase Readiness

- Plan 17 can count and reserve question input before provider invocation, then persist `AIProviderResult.usage` and finalize only with its durable replayable result.
- Plan 18 can apply the same boundary to conversations and hints while using the closed inventory to keep title/report/background effects provider-cost-only.
- Governed admission remains blocked automatically if the receipt is absent, mocked, stale, non-passing, misconfigured, malformed, or no longer authorized.

## Self-Check: PASSED

- FOUND: `src/stoa/services/bedrock_token_count_service.py`
- FOUND: `src/stoa/services/ai_service.py`
- FOUND: `scripts/probe_bedrock_token_count.py`
- FOUND: `tests/test_bedrock_usage_evidence.py`
- FOUND: `docs/security/phase-476-bedrock-token-count-preflight.json`
- FOUND: `85c73703`
- FOUND: `8f739b9c`
- FOUND: `f2a78337`
- FOUND: `402f7f8a`
- PASS: combined provider-evidence and allowance verification (`54 passed`)
- PASS: Ruff exact-file verification
- PASS: exact-file mypy verification
- PASS: non-mocked source/configuration/IAM-bound receipt verification

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
