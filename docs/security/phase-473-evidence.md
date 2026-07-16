# Phase 473 final privacy and practice-integrity evidence

`testedSourceSha`: `b3964d52eb483f4e80a4bca0366bbbcd79468059`

Evidence date: 2026-07-16 UTC. Environment: local offline test processes in `/Users/zhdeng/stoa-backend`. The tested source was a clean committed tree containing Plans 473-12 and 473-13 plus the checked authorization inventory. The inventory was generated twice before the source lock and twice after all test/static gates; every generated copy was byte-identical to the checked JSON. HEAD and tree cleanliness were unchanged throughout the successful observation set.

No production mutation, live AWS/provider call, object upload/delete, deployed scheduler invocation, identity/billing effect, or student-data mutation was performed. Provider, table, object, content, actor, concurrency, and failure effects were deterministic local fakes only.

## Immutable source and blocking gates

| Gate | Exact command | Observed result |
| --- | --- | --- |
| Phase 473 matrix | `.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py tests/test_questions.py tests/test_conversations.py tests/test_practice.py tests/test_practice_privacy.py tests/test_curriculum_rollout.py tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` | PASS — 342 passed in 5.16s |
| Phase 472 authorization regression | `.venv/bin/python -m pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_public_identity_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | PASS — 636 passed in 10.10s |
| Full repository suite | `.venv/bin/python -m pytest -q` | PASS — 1,344 passed in 42.38s; zero failures. The identical command was rerun outside the restricted process-monitor sandbox after the first process was environmentally interrupted at 42%. |
| Targeted static analysis | `.venv/bin/ruff check src/stoa/db/repositories/attachment_repo.py src/stoa/services/attachment_service.py src/stoa/jobs/upload_cleanup.py src/stoa/security/attachment_errors.py src/stoa/routers/files.py src/stoa/routers/conversations.py tests/test_attachment_security.py tests/test_files.py tests/test_conversations.py` | PASS — all Plan 12/13 actual and declared Python paths checked; zero findings |
| Diff hygiene | `git diff --check` | PASS — zero findings |
| Deterministic authorization inventory | `PYTHONPATH=src .venv/bin/python scripts/generate_route_authorization_inventory.py --check` | PASS — four generated copies and checked JSON were identical; SHA-256 `9a3be6b628af5b08cc2ea918a7f775221d1c3f272b603fffd61f982008413b03`, 106,534 bytes |
| Fixed-string privacy denylist | `! rg -F -i -f /tmp/phase473-private-denylist.txt <all test logs, all generated/checked inventories, and all three evidence artifacts>` | PASS — 74 seeded values; zero matches after final artifact generation |

Captured log SHA-256 values: focused `675a89da21582e461f1015cf7fdf800efccb8e6065b4de337ecb6ec2d77748bc`; Phase 472 `5ea164361181abff14edb33a34d2f331c8084db2ee0080be714987ac6a095245`; full suite `66dc8ed47496de923260d8d6b612222b10f6babfc994c6ef24cf67e4c67b0f9b`.

## Gap-finding closure

| Finding | Exact command / selector | Observed result |
| --- | --- | --- |
| CR-007 | `tests/test_attachment_security.py::test_validated_cleanup_deletes_staging_and_immutable_exact_versions_before_complete` and `tests/test_attachment_security.py::test_stale_operation_cleanup_recovers_exact_targets_and_preserves_unrelated` | PASS — both selectors passed in the 342-test matrix; exact unreferenced staging/immutable versions are deleted before completion and restart recovery preserves unrelated versions |
| WR-006 | `tests/test_attachment_security.py::test_deterministic_fresh_attachment_ids_preserve_exact_order_and_keys` and `tests/test_attachment_security.py::test_lost_transaction_retry_rebuilds_identical_attachment_and_association_keys` | PASS — both selectors passed; command-derived IDs and durable keys remain exact across retry |
| WR-007 | `tests/test_files.py::test_complete_gateway_dependency_matrix_is_one_redacted_safe_503` and `tests/test_files.py::test_chunk_gateway_dependency_matrix_is_one_redacted_safe_503` | PASS — both parameterized matrices passed; dependency stages converge on one structured retryable response |
| WR-008 | `tests/test_attachment_security.py::test_validation_provider_body_closes_once_on_every_read_exit` and `tests/test_conversations.py::test_conversation_exact_version_body_closes_once_on_every_extraction_exit` | PASS — both parameterized matrices passed; the exact provider body closes once on every tested exit |

## Requirement proof

| Requirement | Exact command / selector | Observed result |
| --- | --- | --- |
| V9PRIV-01 | `tests/test_attachment_security.py::test_question_fresh_upload_reservation_and_commit_are_conditional_and_atomic` | PASS — selector passed in the 342-test matrix; Actor-owned opaque input, immutable OCR coordinates, and atomic association retained |
| V9PRIV-02 | `tests/test_attachment_security.py::test_validated_cleanup_deletes_staging_and_immutable_exact_versions_before_complete` | PASS — selector and the complete upload validation/error/cleanup matrix passed; CR-007 and WR-007 are locally closed |
| V9PRIV-03 | `tests/test_practice_privacy.py::test_every_practice_preview_route_recursively_omits_answer_canaries` | PASS — selector and role matrix passed; preview routes remain structurally answer-free and reveal requires a recorded attempt |

## Decision results

| Decision | Exact command / selector | Observed result |
| --- | --- | --- |
| D-01 | `tests/test_attachment_security.py::test_validate_supported_bytes` | PASS — all parameter cases passed within the 342 passed matrix; question-image acceptance remains JPEG/PNG only |
| D-02 | `tests/test_attachment_security.py::test_validate_rejects_mime_magic_dimension_archive_and_utf8_failures` | PASS — image size/dimension and bounded-content negatives passed within 342 passed |
| D-03 | `tests/test_attachment_security.py::test_validate_supported_bytes` | PASS — conversation JPEG/PNG/PDF/DOCX/PPTX/XLSX/TXT/MD cases passed within 342 passed |
| D-04 | `tests/test_attachment_security.py::test_fifty_mib_document_promotion_uses_bounded_spool_and_exact_version` | PASS — exact 50 MiB boundary passed within 342 passed; max-plus-one negative also passed |
| D-05 | `tests/test_attachment_security.py::test_validate_rejects_mime_magic_dimension_archive_and_utf8_failures` | PASS — extension/MIME/magic/container/integrity cases passed within 342 passed |
| D-06 | `tests/test_attachment_security.py::test_upload_contract_constants_are_locked` | PASS — exact 1,800-second intent expiry assertion passed within 342 passed |
| D-07 | `tests/test_attachment_security.py::test_lost_transaction_retry_rebuilds_identical_attachment_and_association_keys` | PASS — exact retry keys passed within 342 passed; synchronized regular/SSE convergence also passed |
| D-08 | `tests/test_questions.py::test_terminal_ocr_failure_invalidates_without_question_write` | PASS — terminal invalidation and transient retry controls passed within 342 passed |
| D-09 | `tests/test_attachment_security.py::test_validated_cleanup_deletes_staging_and_immutable_exact_versions_before_complete` | PASS — exact cleanup-before-completion selector passed within 342 passed |
| D-10 | `tests/test_attachment_security.py::test_reference_release_preserves_multi_reference_then_deletes_last_once` | PASS — durable reference retention and explicit last-release deletion passed within 342 passed |
| D-11 | `tests/test_attachment_security.py::test_storage_quota_uses_authoritative_entitlement_tiers` | PASS — exact 5 GiB/15 GiB tier assertions passed within 342 passed |
| D-12 | `tests/test_attachment_security.py::test_saved_attachment_reuse_does_not_mutate_storage_usage` | PASS — owner-scoped logical reuse with zero extra storage charge passed within 342 passed |
| D-13 | `tests/test_attachment_security.py::test_upload_contract_rejects_client_selected_owner_and_storage_fields` | PASS — all client owner/storage-coordinate parameter cases passed within 342 passed |
| D-14 | `tests/test_files.py::test_missing_and_foreign_complete_have_same_safe_shape` | PASS — missing/foreign equivalence passed within 342 passed |
| D-15 | `tests/test_attachment_security.py::test_attachment_error_registry_is_exhaustive_and_retry_is_bounded` | PASS — `upload_expired` status/action contract passed within 342 passed |
| D-16 | `tests/test_files.py::test_complete_gateway_dependency_matrix_is_one_redacted_safe_503` | PASS — structured dependency outcome matrix passed within 342 passed; distinct validation/quota codes also passed |
| D-17 | `tests/test_attachment_security.py::test_ai_private_telemetry_excludes_input_output_and_provider_canaries` | PASS — local response/log privacy control passed within 342 passed; deployed log capture remains NOT RUN |
| D-18 | `tests/test_practice.py::test_answer_is_revealed_only_after_every_attempt_is_persisted` | PASS — both correct/incorrect write-before-reveal cases passed within 342 passed |
| D-19 | `tests/test_practice.py::test_hint_requires_approval_and_rejects_answer_or_explanation_canaries` | PASS — directional-only hint controls passed within 342 passed |
| D-20 | `tests/test_practice_privacy.py::test_every_practice_preview_route_recursively_omits_answer_canaries` | PASS — all student preview families passed within 342 passed |
| D-21 | `tests/test_student_authorization_matrix.py::test_assigned_teacher_and_active_admin_read_only_curriculum_answers` | PASS — exact assigned-teacher and narrow admin read positives passed within 342 passed |
| D-22 | `tests/test_practice_privacy.py::test_privileged_answer_route_hides_unassigned_stale_wrong_scope_and_roles` | PASS — anonymous/student/parent/unassigned and stale/wrong-scope role negatives passed within 342 passed |

Canonical role vocabulary remains exactly `student|parent|teacher|admin`; one account has one role. Public failures expose only stable structured code, safe message, server correlation, and bounded recovery guidance.

## External evidence boundaries

| External item | Status | Boundary |
| --- | --- | --- |
| Real S3 chunk, multipart, version, promotion, overwrite, restart-recovery, and immutable-read behavior | **NOT RUN** | No separately approved non-production bucket or credentials; local deterministic fakes do not prove deployed provider policy |
| Deployed cleanup scheduler/EventBridge/Lambda/IaC, retries, and alarms | **NOT RUN** | Authoritative deployment/IaC evidence is unavailable and remains Phase 479-owned |
| Production/deployed log-redaction capture | **NOT RUN** | Production access/provider execution was not approved; only local captured-log proof exists |

These boundaries are limitations, not passes. This document intentionally contains no SHA for the later docs-only commit that contains it.
