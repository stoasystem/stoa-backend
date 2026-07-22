# Phase 475 checked transactional consistency evidence

Immutable source candidate: `cc709c17a9ff4cbec4c3aabf51660f52e571b5dc`. Phase base: `901cb26626cb0f06b7f51a72b95e04aa4f7f4ebf`.
All passing behavioral observations are local deterministic tests/fakes. Live AWS, provider effects, deployment, and production smoke remain exact NOT RUN obligations.

## Gate receipts

| Gate | Kind | Nodes | Exit | Privacy | Result |
| --- | --- | ---: | ---: | ---: | --- |
| `P475-QUESTION` | pytest | 22 | 0 | 0 | PASS |
| `P475-TAKEOVER` | pytest | 9 | 0 | 0 | PASS |
| `P475-RELATIONSHIP` | pytest | 25 | 0 | 0 | PASS |
| `P475-RATE` | pytest | 7 | 0 | 0 | PASS |
| `P475-MISTAKE` | pytest | 9 | 0 | 0 | PASS |
| `P475-DELIVERY` | pytest | 24 | 0 | 0 | PASS |
| `P475-DELETION` | pytest | 49 | 0 | 0 | PASS |
| `P475-INHERITED-AUTH-PRIVACY` | pytest | 327 | 0 | 0 | PASS |
| `P475-PHASE474-FORMAL-EXTENSION` | pytest | 2466 | 0 | 0 | PASS |
| `RUFF-PHASE475` | ruff | — | 0 | 0 | PASS |
| `MYPY-PHASE475-CHANGED-LINES` | mypy | — | 0 | 0 | PASS |

The final backend aggregate uses the fixed Phase 474 full-suite argv prefix, strict Python 3.12 node accounting, fixed clock/seed, denied ambient AWS credentials, and socket denial. It extends the authoritative backend gate to this candidate; it does not relabel this local run as the historical two-environment Linux/cross-repository release receipt.

## Closed coverage

### Requirements

| ID | Exact observed nodes | Result |
| --- | --- | --- |
| `V9DATA-01` | `tests/test_phase475_question_admission.py::test_concurrent_identical_keys_commit_one_complete_admission`<br>`tests/test_phase475_question_admission.py::test_commit_then_timeout_reconciles_to_resume`<br>`tests/test_phase475_question_reconciliation.py::test_each_terminal_transaction_boundary_fails_without_partial_compensation`<br>`tests/test_phase475_question_reconciliation.py::test_terminal_reversal_is_exact_once_and_attachment_storage_are_unchanged` | PASS |
| `V9DATA-02` | `tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser`<br>`tests/test_phase475_teacher_takeover_effect.py::test_begin_dependency_failure_then_retry_creates_one_notification`<br>`tests/test_phase475_teacher_takeover_effect.py::test_losing_claim_never_reaches_notification_effect` | PASS |
| `V9DATA-03` | `tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged[case-254d3518b58d10c8]`<br>`tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged[case-41d95aaae1c0a2fe]`<br>`tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged[case-44a7cb3d9218709c]`<br>`tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged[case-fcbf9e9a0326ed2f]`<br>`tests/test_phase475_parent_binding_reconciliation.py::test_changed_after_preview_is_skipped_and_new_data_is_preserved`<br>`tests/test_phase475_parent_binding_reconciliation.py::test_one_sided_apply_is_atomic_and_replay_is_zero_write` | PASS |
| `V9DATA-04` | `tests/test_phase475_rate_limit.py::test_repeating_429_requests_leave_counter_exactly_at_limit`<br>`tests/test_phase475_rate_limit.py::test_two_concurrent_distinct_requests_compete_for_one_final_slot`<br>`tests/test_phase475_rate_limit.py::test_provider_failure_retry_replays_one_count_and_distinct_operation_is_evaluated` | PASS |
| `V9DATA-05` | `tests/test_phase475_mistake_answer.py::test_wrong_answer_round_trips_exactly_after_normalization[case-33e3e0865f1a8444]`<br>`tests/test_phase475_mistake_answer.py::test_wrong_answer_round_trips_exactly_after_normalization[case-fc774eb4f32fba3d]`<br>`tests/test_phase475_mistake_answer.py::test_legacy_missing_answer_is_explicit_unknown_and_never_uses_standard_answer`<br>`tests/test_phase475_mistake_answer.py::test_route_rejects_unsupported_answer_before_attempt_write_and_redacts_value` | PASS |
| `V9DATA-06` | `tests/test_phase475_profile_version_cas.py::test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes`<br>`tests/test_phase475_profile_version_cas.py::test_same_sensitive_field_race_always_leaves_scrubbed_linkage_absent[case-8a9d03258664306c]`<br>`tests/test_phase475_profile_version_cas.py::test_same_sensitive_field_race_always_leaves_scrubbed_linkage_absent[case-e919c647738d67f5]`<br>`tests/test_phase475_profile_version_cas.py::test_profile_writer_registry_is_closed_against_direct_source_mutations` | PASS |
| `V9DATA-07` | `tests/test_phase475_delivery_begin.py::test_dependency_failure_remains_recoverable_then_healthy_retry_delivers_once`<br>`tests/test_phase475_delivery_begin.py::test_ordered_fence_failure_plus_strong_deleted_fence_cancels_without_provider`<br>`tests/test_phase475_delivery_begin.py::test_ordered_intent_condition_loss_is_retryable_and_never_mislabeled` | PASS |
| `V9DATA-08` | `tests/test_phase475_completed_deletion_replay.py::test_real_endpoint_replays_stored_terminal_receipt_with_zero_new_effects`<br>`tests/test_phase475_completed_deletion_replay.py::test_terminal_replay_preserves_fingerprint_and_verified_identity_conflicts[case-26fe64099a2c0fad]`<br>`tests/test_phase475_completed_deletion_replay.py::test_terminal_replay_preserves_fingerprint_and_verified_identity_conflicts[case-d6e55e6fd29db54c]` | PASS |

### Decisions

| ID | Exact observed nodes | Result |
| --- | --- | --- |
| `D-01` | `tests/test_phase475_question_replay.py::test_ai_failure_returns_queryable_durable_pending_question` | PASS |
| `D-02` | `tests/test_phase475_question_replay.py::test_lost_response_retry_returns_original_without_repeating_effects` | PASS |
| `D-03` | `tests/test_phase475_question_reconciliation.py::test_terminal_reversal_is_exact_once_and_attachment_storage_are_unchanged` | PASS |
| `D-04` | `tests/test_phase475_question_replay.py::test_changed_payload_returns_structured_new_submission_action` | PASS |
| `D-05` | `tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser` | PASS |
| `D-06` | `tests/test_phase475_teacher_takeover_effect.py::test_losing_claim_never_reaches_notification_effect` | PASS |
| `D-07` | `tests/test_phase475_teacher_takeover_effect.py::test_route_keeps_winner_session_when_effect_fails_then_replays` | PASS |
| `D-08` | `tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser` | PASS |
| `D-09` | `tests/test_phase475_parent_binding_transaction.py::test_conflicting_parent_is_preserved_and_authorization_remains_denied` | PASS |
| `D-10` | `tests/test_phase475_parent_binding_reconciliation.py::test_different_parent_conflict_is_report_only_and_remains_unauthorized` | PASS |
| `D-11` | `tests/test_phase475_parent_binding_reconciliation.py::test_changed_after_preview_is_skipped_and_new_data_is_preserved` | PASS |
| `D-12` | `tests/test_phase475_profile_version_cas.py::test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes` | PASS |
| `D-13` | `tests/test_phase475_rate_limit.py::test_provider_failure_retry_replays_one_count_and_distinct_operation_is_evaluated` | PASS |
| `D-14` | `tests/test_phase475_mistake_answer.py::test_legacy_missing_answer_is_explicit_unknown_and_never_uses_standard_answer` | PASS |
| `D-15` | `tests/test_phase475_delivery_begin.py::test_dependency_failure_remains_recoverable_then_healthy_retry_delivers_once` | PASS |
| `D-16` | `tests/test_phase475_completed_deletion_replay.py::test_real_endpoint_replays_stored_terminal_receipt_with_zero_new_effects` | PASS |

### Audit findings

| ID | Exact observed nodes | Result |
| --- | --- | --- |
| `DATA-001` | `tests/test_phase475_question_admission.py::test_concurrent_identical_keys_commit_one_complete_admission`<br>`tests/test_phase475_question_admission.py::test_commit_then_timeout_reconciles_to_resume`<br>`tests/test_phase475_question_reconciliation.py::test_each_terminal_transaction_boundary_fails_without_partial_compensation`<br>`tests/test_phase475_question_reconciliation.py::test_terminal_reversal_is_exact_once_and_attachment_storage_are_unchanged` | PASS |
| `BUG-002` | `tests/test_phase475_teacher_takeover.py::test_two_barrier_claimants_produce_one_owner_session_and_private_loser`<br>`tests/test_phase475_teacher_takeover_effect.py::test_begin_dependency_failure_then_retry_creates_one_notification`<br>`tests/test_phase475_teacher_takeover_effect.py::test_losing_claim_never_reaches_notification_effect` | PASS |
| `DATA-003` | `tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged[case-254d3518b58d10c8]`<br>`tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged[case-41d95aaae1c0a2fe]`<br>`tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged[case-44a7cb3d9218709c]`<br>`tests/test_phase475_parent_binding_transaction.py::test_failure_at_every_operation_leaves_all_relationship_projections_unchanged[case-fcbf9e9a0326ed2f]`<br>`tests/test_phase475_parent_binding_reconciliation.py::test_changed_after_preview_is_skipped_and_new_data_is_preserved`<br>`tests/test_phase475_parent_binding_reconciliation.py::test_one_sided_apply_is_atomic_and_replay_is_zero_write` | PASS |
| `BUG-006` | `tests/test_phase475_rate_limit.py::test_repeating_429_requests_leave_counter_exactly_at_limit`<br>`tests/test_phase475_rate_limit.py::test_two_concurrent_distinct_requests_compete_for_one_final_slot`<br>`tests/test_phase475_rate_limit.py::test_provider_failure_retry_replays_one_count_and_distinct_operation_is_evaluated` | PASS |
| `BUG-004` | `tests/test_phase475_mistake_answer.py::test_wrong_answer_round_trips_exactly_after_normalization[case-33e3e0865f1a8444]`<br>`tests/test_phase475_mistake_answer.py::test_wrong_answer_round_trips_exactly_after_normalization[case-fc774eb4f32fba3d]`<br>`tests/test_phase475_mistake_answer.py::test_legacy_missing_answer_is_explicit_unknown_and_never_uses_standard_answer`<br>`tests/test_phase475_mistake_answer.py::test_route_rejects_unsupported_answer_before_attempt_write_and_redacts_value` | PASS |

### Phase 473 follow-ups

| ID | Exact observed nodes | Result |
| --- | --- | --- |
| `profile-version-cas` | `tests/test_phase475_profile_version_cas.py::test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes`<br>`tests/test_phase475_profile_version_cas.py::test_same_sensitive_field_race_always_leaves_scrubbed_linkage_absent[case-8a9d03258664306c]`<br>`tests/test_phase475_profile_version_cas.py::test_same_sensitive_field_race_always_leaves_scrubbed_linkage_absent[case-e919c647738d67f5]`<br>`tests/test_phase475_profile_version_cas.py::test_profile_writer_registry_is_closed_against_direct_source_mutations` | PASS |
| `delivery-begin-dependency-classification` | `tests/test_phase475_delivery_begin.py::test_dependency_failure_remains_recoverable_then_healthy_retry_delivers_once`<br>`tests/test_phase475_delivery_begin.py::test_ordered_fence_failure_plus_strong_deleted_fence_cancels_without_provider`<br>`tests/test_phase475_delivery_begin.py::test_ordered_intent_condition_loss_is_retryable_and_never_mislabeled` | PASS |
| `completed-deletion-replay` | `tests/test_phase475_completed_deletion_replay.py::test_real_endpoint_replays_stored_terminal_receipt_with_zero_new_effects`<br>`tests/test_phase475_completed_deletion_replay.py::test_terminal_replay_preserves_fingerprint_and_verified_identity_conflicts[case-26fe64099a2c0fad]`<br>`tests/test_phase475_completed_deletion_replay.py::test_terminal_replay_preserves_fingerprint_and_verified_identity_conflicts[case-d6e55e6fd29db54c]` | PASS |

## Static analysis truth

Ruff passed all 21 Phase 475 runtime files plus the verifier and its test. Mypy analyzed the same runtime inventory: 0 diagnostics touch Phase 475 changed lines; 178 diagnostics remain on pre-candidate lines and are disclosed rather than suppressed or called zero.

## External obligations

| Obligation | Status | Owner phase |
| --- | --- | --- |
| `LIVE-AWS-DYNAMODB` | **NOT RUN** | 479 |
| `LIVE-PROVIDER-EFFECTS` | **NOT RUN** | 480 |
| `DEPLOYMENT-AND-PRODUCTION-SMOKE` | **NOT RUN** | 480 |

## Privacy and source binding

Raw receipt match count: 0; published match count: 0. Exact argv, UTC bounds, exit codes, safe opaque node manifests, artifact hashes, runtime-file inventory, and immutable Git-blob source snapshot are recorded in the checked JSON. No raw answer, teacher identity, storage coordinate, provider diagnostic, or identity hash is published.
