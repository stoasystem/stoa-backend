---
phase: 474
slug: deterministic-verification-and-gated-delivery
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-07-31
---

# Phase 474 — Validation Strategy

> Per-phase validation contract for the eight retained staging-only plans. Production release-control work is `DEFERRED_OUT_OF_SCOPE`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3, Ruff, mypy, jq, AWS CDK assertions |
| **Config file** | `pyproject.toml`, `/Users/zhdeng/stoa-infra/pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest -q tests/test_release_environment.py tests/test_delivery_workflow_contract.py tests/test_release_delivery.py` |
| **Full suite command** | `.venv/bin/python scripts/verify_phase_474_evidence.py validate-final --input evidence/phase-474/final-evidence.json --reverify-phase473 --expect-zero-source-gaps --expect-production-deferred-out-of-scope` |
| **Estimated runtime** | ~5 minutes locally, excluding owner and provider checkpoints |

---

## Sampling Rate

- **After every task commit:** Run the task's exact automated command from the map below plus Ruff/mypy for changed Python modules.
- **After every plan wave:** Run the quick command and all completed upstream receipt validators.
- **Before `$gsd-verify-work`:** The Plan 474-38 final validator and canonical repository quality gates must be green.
- **Max feedback latency:** 10 minutes for local checks; provider and owner checkpoints are explicitly blocking.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 474-33-01 | 33 | 18 | V9QUAL-06 | T-474-33-S/T/E | Known staging targets may be `SAFE_ABSENT`; unknown or unreadable state blocks. | integration/adversarial | `.venv/bin/python -m pytest -q tests/test_release_environment.py && .venv/bin/python scripts/release_environment.py verify-inventory --receipt evidence/phase-474/environment-baseline-resolution.json --frontend-ref evidence/phase-474/frontend-source-ref.json --infra-ref evidence/phase-474/infra-source-ref.json` | ✅ | ⬜ pending |
| 474-79-01 | 79 | 19 | V9QUAL-06 | T-474-79-S/T/E | Exactly one reviewer-free, main-only `staging` Environment passes; any production or extra staging Environment blocks. | provider/integration | `.venv/bin/python -m pytest -q tests/test_delivery_workflow_contract.py tests/test_release_environment.py && .venv/bin/python scripts/release_environment.py verify-github --baseline evidence/phase-474/environment-baseline-resolution.json --receipt evidence/phase-474/protected-environments-resolution.json --policy docs/security/phase-474-workflow-policy.json` | ✅ | ⬜ pending |
| 474-34-01 | 34 | 19 | V9QUAL-06 | T-474-34-S/T/R/E | Only an owner-confirmed additive `StoaReleaseStaging` diff may apply; three staging roles share one exact OIDC subject; provider readback proves at least 90 days retention and indefinite automatic-deletion exclusion for `current` and `most_recent_verified_known_good`. | provider/integration | `.venv/bin/python scripts/build_lambda_dist.py --dist dist --verify-only && (cd /Users/zhdeng/stoa-infra && uv run pytest -q tests/test_release_topology.py && uv run cdk synth StoaReleaseStaging >/dev/null) && .venv/bin/python scripts/release_environment.py verify-staging --baseline evidence/phase-474/environment-baseline-resolution.json --infra-ref evidence/phase-474/infra-source-ref.json --manifest dist/.stoa-build-manifest.json --receipt evidence/phase-474/staging-substrate.json --policy docs/security/phase-474-workflow-policy.json` | ✅ | ⬜ pending |
| 474-80-01 | 80 | 20 | V9QUAL-06 | T-474-80-S/T/E | Owner verification joins completed GitHub and AWS staging readbacks without granting production authority. | contract/human gate | `jq -e '.status == "OWNER_VERIFIED" and .environment == "staging" and .manual_reviewers == [] and .scope.production_release_control_plane == "DEFERRED_OUT_OF_SCOPE"' evidence/phase-474/owner-staging-verification.json >/dev/null` | ❌ Plan 80 | ⬜ pending |
| 474-35-01 | 35 | 21 | V9QUAL-01..06 | T-474-35-T/E | Staging deploy and smoke use deploy/read roles; controlled rollback restores both pointers through rollback role. | controlled staging/integration | `.venv/bin/python -m pytest -q tests/test_release_delivery.py tests/test_delivery_workflow_contract.py -k 'staging or smoke or compensat or rollback or restored or environment or role' && .venv/bin/python scripts/release_gate.py verify --backend-ref evidence/phase-474/backend-source-ref.json --frontend-ref evidence/phase-474/frontend-source-ref.json --infra-ref evidence/phase-474/infra-source-ref.json --staging-substrate evidence/phase-474/staging-substrate.json --receipt-root evidence/phase-474` | ✅ | ⬜ pending |
| 474-36-01 | 36 | 22 | V9QUAL-01..07 | T-474-36-T/E | Failure matrix rejects extra Environments, production control-plane remnants, role overlap, tampering, and bypass. | adversarial/integration | `.venv/bin/python -m pytest -q tests/test_phase_474_evidence.py tests/test_delivery_workflow_contract.py && .venv/bin/python scripts/verify_phase_474_evidence.py validate-failure-matrix --input evidence/phase-474/failure-matrix.json` | ❌ Plan 36 | ⬜ pending |
| 474-37-01 | 37 | 23 | V9QUAL-01..07 | T-474-37-T/R | Source audit proves one current staging-only contract and consistent `39/47`, eight-retained-plan routing. | source audit | `.venv/bin/python scripts/verify_phase_474_evidence.py validate-source-audit --input evidence/phase-474/source-audit.json --roadmap .planning/ROADMAP.md --requirements .planning/REQUIREMENTS.md --context .planning/phases/474-deterministic-verification-and-gated-delivery/474-CONTEXT.md --research .planning/phases/474-deterministic-verification-and-gated-delivery/474-RESEARCH.md` | ❌ Plan 36 | ⬜ pending |
| 474-38-01 | 38 | 24 | V9QUAL-01..07 | T-474-38-T/R/E | Final evidence has zero source gaps and rejects any current production release-control obligation. | final integration | `.venv/bin/python scripts/verify_phase_474_evidence.py validate-final --input evidence/phase-474/final-evidence.json --reverify-phase473 --expect-zero-source-gaps --expect-production-deferred-out-of-scope` | ❌ Plan 36 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing test infrastructure covers Plans 33, 34, 35, and 79. The following execution-owned artifacts are intentionally created before their first use:

- [ ] `tests/test_phase_474_evidence.py` — created TDD-first by Plan 474-36.
- [ ] `scripts/verify_phase_474_evidence.py` — created by Plan 474-36 and consumed by Plans 37–38.
- [ ] `evidence/phase-474/owner-staging-verification.json` — created at Plan 474-80's blocking owner checkpoint.

No framework installation or watch-mode runner is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Approve the exact additive `StoaReleaseStaging` diff digest | V9QUAL-06 | Applying AWS infrastructure is an external mutation and one-way authority boundary. | Inspect the complete CDK diff; confirm ordinary staging/failed evidence retention is at least 90 days, `current` and `most_recent_verified_known_good` are indefinitely excluded from lifecycle/Object Lock deletion with no automatic deletion path, and there is no replacement/deletion, IAM broadening, unknown resource, wrong account/region, or production resource; respond only with `approve <confirmation_sha256>`. |
| Verify joined GitHub and AWS staging readbacks | V9QUAL-06 | The owner must confirm external provider evidence before staging delivery. | Inspect `protected-environments-resolution.json`, `staging-substrate.json`, and the generated owner receipt; approve only when both upstream receipts are PASS and production is `DEFERRED_OUT_OF_SCOPE`. |

---

## Validation Sign-Off

- [x] All tasks have an `<automated>` verification or an explicit execution-owned prerequisite.
- [x] Sampling continuity: no three consecutive tasks lack automated verification.
- [x] Wave 0 and execution-owned missing references are explicitly mapped.
- [x] No watch-mode flags are used.
- [x] Local feedback latency target is under 10 minutes.
- [ ] `nyquist_compliant: true` is set only after execution evidence validates every row.

**Approval:** pending execution
