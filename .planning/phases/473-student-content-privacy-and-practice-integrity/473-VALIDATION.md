---
phase: 473
slug: student-content-privacy-and-practice-integrity
status: local_gates_complete
nyquist_compliant: true
testedSourceSha: b3964d52eb483f4e80a4bca0366bbbcd79468059
updated: 2026-07-16
---

# Phase 473 — Final validation observations

All successful local observations below derive from the clean immutable `testedSourceSha` above. This document does not mark the phase independently verified or complete; the orchestrator verifier owns that decision.

## Source lock and observed gates

| Gate | Exact command | Observed result |
| --- | --- | --- |
| Pre-lock inventory | `PYTHONPATH=src .venv/bin/python scripts/generate_route_authorization_inventory.py --output /tmp/phase473-inventory-a.json` followed by the same command for `inventory-b`, `cmp` against each other and the checked JSON, then generator `--check` | PASS — both 106,534-byte generations and checked inventory were identical |
| Phase 473 combined matrix | `.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py tests/test_questions.py tests/test_conversations.py tests/test_practice.py tests/test_practice_privacy.py tests/test_curriculum_rollout.py tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` | PASS — 342 passed in 5.16s |
| Phase 472 exact 21-module regression | `.venv/bin/python -m pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_public_identity_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | PASS — 636 passed in 10.10s |
| Full suite | `.venv/bin/python -m pytest -q` | PASS — 1,344 passed in 42.38s; zero failures. Successful rerun used unrestricted process monitoring after the restricted sandbox environmentally interrupted the first identical run. |
| Targeted Ruff | `.venv/bin/ruff check src/stoa/db/repositories/attachment_repo.py src/stoa/services/attachment_service.py src/stoa/jobs/upload_cleanup.py src/stoa/security/attachment_errors.py src/stoa/routers/files.py src/stoa/routers/conversations.py tests/test_attachment_security.py tests/test_files.py tests/test_conversations.py` | PASS — zero findings across every actual and plan-declared Plan 12/13 Python path |
| Diff hygiene | `git diff --check` | PASS — zero findings |
| Post-lock inventory | generate twice to `/tmp/phase473-inventory-post-a.json` and `/tmp/phase473-inventory-post-b.json`, byte-compare each other and checked JSON, then run generator `--check` | PASS — both generations identical; checked inventory SHA-256 `9a3be6b628af5b08cc2ea918a7f775221d1c3f272b603fffd61f982008413b03` |
| Final inventory | generate twice to `/tmp/phase473-inventory-check-a.json` and `/tmp/phase473-inventory-check-b.json`, compare and run generator `--check` | PASS — final copies remained byte-identical to the checked inventory |
| Privacy denylist | `! rg -F -i -f /tmp/phase473-private-denylist.txt` over every captured test log, all pre/post/final generated inventories, checked inventory, evidence, validation, and manifest | PASS — 74 seeded values; zero matches |

The candidate remained `b3964d52eb483f4e80a4bca0366bbbcd79468059`, with a clean tree, throughout all source/test/static gates. Focused, Phase 472, and full log SHA-256 values are `675a89da21582e461f1015cf7fdf800efccb8e6065b4de337ecb6ec2d77748bc`, `5ea164361181abff14edb33a34d2f331c8084db2ee0080be714987ac6a095245`, and `66dc8ed47496de923260d8d6b612222b10f6babfc994c6ef24cf67e4c67b0f9b` respectively.

## Finding and requirement adjudication

| Item | Result | Executable control |
| --- | --- | --- |
| CR-007 | PASS locally | `tests/test_attachment_security.py::test_validated_cleanup_deletes_staging_and_immutable_exact_versions_before_complete` and stale-operation restart controls passed |
| WR-006 | PASS locally | `tests/test_attachment_security.py::test_deterministic_fresh_attachment_ids_preserve_exact_order_and_keys` and lost-response exact-key control passed |
| WR-007 | PASS locally | `tests/test_files.py::test_complete_gateway_dependency_matrix_is_one_redacted_safe_503` and chunk dependency matrix passed |
| WR-008 | PASS locally | validation and extraction exact-body close-on-every-exit matrices passed |
| V9PRIV-01 | PASS locally | Actor-owned opaque question attachment and atomic association controls passed |
| V9PRIV-02 | PASS locally | exact upload validation, structured errors, restart-safe recovery, and complete exact-version cleanup controls passed |
| V9PRIV-03 | PASS locally | answer-free preview, durable attempt-before-reveal, and scoped privileged answer matrices passed |

The evidence document contains a single machine-checkable decision table with one executable-result row for every decision from 01 through 22. No endpoint-presence-only assertion is treated as decision proof.

## Artifact integrity

`docs/security/phase-473-evidence-manifest.json` uses schema version 1, repeats the exact tested source SHA, and hashes only the final evidence and validation bytes. Its digest and byte-size fields are reproducible after both narrative documents are finalized. The docs-only commit after the tested source changes exactly:

- `.planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md`
- `docs/security/phase-473-evidence.md`
- `docs/security/phase-473-evidence-manifest.json`

No evidence artifact embeds the future docs-only commit SHA.

## Manual/external observations

| Behavior | Status | Reason |
| --- | --- | --- |
| Real S3 version/multipart/promotion/overwrite/recovery behavior | **NOT RUN** | No approved non-production storage environment or credentials |
| Deployed cleanup schedule/EventBridge/Lambda/IaC and alarms | **NOT RUN** | Authoritative deployment evidence is unavailable and outside this plan's mutation scope |
| Production/deployed log capture | **NOT RUN** | Production access/provider execution not approved; local captured-log proof only |

No external result is inferred from local fakes. Final independent phase verification/completion remains an orchestrator responsibility.
