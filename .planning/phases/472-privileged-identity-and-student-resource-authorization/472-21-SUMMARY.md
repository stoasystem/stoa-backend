---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 21
subsystem: security
tags: [authorization-audit, hmac, key-rotation, configuration, fail-closed]
requires:
  - phase: 472-16
    provides: independently verified authorization evidence and final review findings
provides:
  - canonical raw, hex, and base64 audit-secret parsing with 256-bit minimum strength
  - uniform active and retained keyring validation with normalized unique IDs and material digests
  - fail-closed cached and direct Dynamo audit sink construction from canonical bytes
affects: [phase-472-verification, phase-474-production-configuration, authorization-evidence]
tech-stack:
  added: []
  patterns: [category-only secret validation errors, canonical validated keyring cache identity]
key-files:
  created: []
  modified:
    - src/stoa/config.py
    - src/stoa/deps.py
    - src/stoa/db/repositories/security_audit_repo.py
    - tests/test_authorization_audit.py
    - .planning/phases/472-privileged-identity-and-student-resource-authorization/472-USER-SETUP.md
key-decisions:
  - "Audit secrets accept explicit strict hex/base64 encodings plus a documented raw compatibility form, but all forms validate the same decoded bytes."
  - "Dependency caching is keyed by normalized IDs and validated bytes, so equivalent configuration cannot create distinct runtime key identities."
  - "Only the exact built-in development default is allowed in non-production; production and direct sink construction remain fail-closed."
patterns-established:
  - "Secret validation errors contain stable category codes and Settings hides submitted inputs in validation output."
  - "Active and every retained key pass one validator before any audit table access or fingerprint generation."
requirements-completed: [V9ACCESS-01, V9ACCESS-03]
duration: 7 min
completed: 2026-07-15
---

# Phase 472 Plan 21: Strong production audit HMAC keyring validation Summary

**Canonical 256-bit audit key parsing, uniform rotation validation, and fail-closed sink caching prevent weak or ambiguous HMAC material from reaching authorization evidence.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-15T16:14:30Z
- **Completed:** 2026-07-15T16:21:36Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added strict raw, `hex:`, and `base64:` parsing with minimum length, diversity, repeated-pattern, common-placeholder, and development-default controls.
- Applied the same validation to active and retained keys, rejecting trimmed-ID collisions and duplicate decoded material by non-reversible digest.
- Made Settings errors input-redacted and made both direct and cached sink construction fail before table access or fingerprint generation.
- Preserved active-key writes and retained-key replay recognition with strong deterministic non-production fixtures.

## Task Commits

Each task was committed atomically:

1. **Task 1: Validate canonical high-entropy key material and unique keyring identity** - `892e14f` (feat)
2. **Task 2: Fail sink startup safely and preserve valid rotation** - `21d93e6` (fix)

## Files Created/Modified

- `src/stoa/config.py` - Canonical parser/keyring validator and redacted Settings validation.
- `src/stoa/deps.py` - Normalizes and validates key material before cached sink construction.
- `src/stoa/db/repositories/security_audit_repo.py` - Defensively validates direct construction and consumes canonical validated keyrings.
- `tests/test_authorization_audit.py` - Weak, malformed, placeholder, duplicate, rotation, replay, redaction, and pre-effect failure coverage.
- `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-USER-SETUP.md` - Production key generation, storage, rotation, and verification checklist.

## Decisions Made

- Explicit encoded forms are strict and malformed data never falls back to raw text; raw compatibility remains only when decoded UTF-8 bytes meet the same strength rules.
- Cache identity uses normalized IDs and decoded bytes, matching the exact HMAC material used by the sink.
- Local development keeps only the explicit built-in default exception; configured local rotations and every production key use the canonical contract.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Pydantic initially included submitted Settings input in its rendered validation error even though the validator message was category-only. Enabled `hide_input_in_errors` and added canary assertions so startup errors cannot echo key material.

## Verification

- `pytest tests/test_authorization_audit.py -k 'production or key or secret or rotation or duplicate or weak or placeholder'`: 17 passed, 13 deselected.
- `pytest tests/test_authorization_audit.py tests/test_identity_authorization.py -k 'audit or key or rotation or replay or outage or redaction'`: 33 passed, 22 deselected.
- Full two-file regression: 55 passed.
- Ruff on all modified Python files: passed.
- `tests/test_external_activation_smoke.py` remained unchanged; no Phase 474 fixture ownership moved.
- No AWS, provider, network, or production mutation was performed.

## User Setup Required

**Production rollout requires manual secret generation and secret-manager configuration.** See [472-USER-SETUP.md](./472-USER-SETUP.md) for:

- Strong active and retained audit key variables
- Unique ID and decoded-material rotation requirements
- Local verification without external access

## Next Phase Readiness

- WR-04 is closed locally and ready for independent Plan 472-22 regression/evidence verification.
- Phase 474 still owns modernization of its 23 strict production Settings fixtures; this plan did not edit them.
- Phase 475 teacher takeover atomicity remains out of scope and unchanged.

## Self-Check: PASSED

- Required artifacts exist on disk.
- Both task commits are present.
- Every task acceptance criterion and plan verification command passed.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
