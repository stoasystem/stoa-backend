# Phase 473 final privacy and practice-integrity evidence

`testedSourceSha`: `060f07f187441bc9cb31ac9c1286ea6165d5bfa0`

Evidence window: 2026-07-16T18:10:01Z–2026-07-16T18:11:43Z UTC. Environment: local offline test process in `/Users/zhdeng/stoa-backend`. The tested source was a clean committed tree containing Plans 473-08 through 473-10 and the checked authorization inventory. HEAD and cleanliness were checked before and after every blocking gate.

No production mutation, AWS/network/provider call, live object upload/delete, deployed scheduler invocation, identity/billing effect, or student-data mutation was performed. Provider, table, object, content, actor, concurrency, and failure effects were deterministic local fakes only.

## Immutable source and artifact gate

The authorization inventory was generated twice before the candidate lock, byte-compared, compared with the checked JSON, and checked with the generator. The checked artifact was already current, so commit `060f07f` locked the complete implementation plus checked inventory as the immutable test candidate. No implementation, test, generator, or inventory file changed after that commit.

| Artifact | SHA-256 | Bytes / result |
| --- | --- | --- |
| `docs/security/route-authorization-inventory.json` | `9a3be6b628af5b08cc2ea918a7f775221d1c3f272b603fffd61f982008413b03` | 106,534 bytes; both generations and checked JSON identical; `--check` PASS |
| `scripts/generate_route_authorization_inventory.py` | `b4e2201940b44f1f48f0633f46e91c98dc8df60916a8c0871277e4e5c4abb0ff` | deterministic generation/check entry point |
| `tests/test_files.py` | `10aa4b0bf86b91339273a21aa13dffd7a127b2b40b7d62b3c5efd5568cc309ee` | opaque gateway and safe route failures |
| `tests/test_attachment_security.py` | `3d8555557f0783b5b950fa2f099c891f5e38af74684a7e8a75a3ffa4dd372906` | immutable bytes, transaction, cleanup, replay, telemetry controls |
| `tests/test_questions.py` | `031f3627c1a0c30fafd9c0c0bd4bd0ba26f4d7f08e907b2de1267a8877fb5a4a` | owner OCR, atomic association, stable errors |
| `tests/test_conversations.py` | `ced9ad56a526674759f2b229c220e5a101d5c5ca09643735255f902fefeb806b` | exact/concurrent replay and private telemetry |
| `tests/test_practice.py` | `416c2f183c01e3070479aa595e32b0e403d59fe4ce925d9e12740967a2cce0ad` | write-before-result and safe hints |
| `tests/test_practice_privacy.py` | `08abcdfa6ed50bcbc55cd406679aabb641c61e92f5f773db483c1e0478732b47` | previews, attempts, privileged answer scope |
| `tests/test_curriculum_rollout.py` | `c1d6d818534172bc58dac4c418e6aedddd60008127dcb8ebf62d51fa0a1380b3` | answer-free curriculum projections |
| `tests/test_route_authorization_inventory.py` | `2fd3ddc98ef9e8b9bc2eab883c75b780da03ca5eefd7aaf67a735a604d7bcaa1` | runtime/OpenAPI/checked equivalence |
| `tests/test_student_authorization_matrix.py` | `1fcb2450294a01b57689773023a53b279904843e2a67aec8c66ab9e65c289c38` | student/parent/teacher/admin authorization controls |
| Full-suite captured output | `0783200d9747f62b6253eaa1ff357c0f8e7618e49146d23a782896e214bd3655` | 1,303 passed |

## Exact blocking observations

| UTC | Exact command | Result |
| --- | --- | --- |
| 18:10:01–18:10:06 | `.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py tests/test_questions.py tests/test_conversations.py tests/test_practice.py tests/test_practice_privacy.py tests/test_curriculum_rollout.py tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` | PASS — 301 passed in 4.22s |
| 18:10:15–18:10:24 | `.venv/bin/python -m pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_public_identity_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | PASS — 636 passed in 8.62s |
| 18:10:31–18:11:06 | `.venv/bin/python -m pytest -q` | PASS — 1,303 passed in 34.01s; zero failures |
| 18:11:40–18:11:43 | `.venv/bin/ruff check` over every Python file modified by Plans 08–10; `git diff --check`; generate inventory twice; compare both with checked JSON; generator `--check` | PASS — zero Ruff findings, clean diff, byte-stable inventory |
| after local gates | Fixed-string denylist built from 47 private fixture categories and applied to captured test output plus both generated and checked inventories | PASS — zero matches |

## Review finding closure matrix

| Finding | Result | Executable positive and adversarial evidence |
| --- | --- | --- |
| CR-001 | PASS locally | `test_fifty_mib_document_promotion_uses_bounded_spool_and_exact_version`, `test_same_key_newer_version_cannot_change_extraction_bytes`, version-bound OCR/extraction/cleanup tests prove the promoted tuple is immutable and replacement/newer versions cannot alter downstream bytes. |
| WR-001 | PASS locally | `test_gateway_intent_returns_only_opaque_contract`, `test_gateway_issuance_is_owner_bound_opaque_and_multipart_private`, legacy-route absence and generated-contract tests prove the gateway returns no URL, key, path, multipart ID, ETag, VersionId, or provider coordinate. |
| WR-002 | PASS locally | `test_ai_private_telemetry_excludes_input_output_and_provider_canaries`, title-failure, OCR-fed, extraction, malformed-output, answer/hint, exception, and replay caplog controls prove category/class/size/count/correlation-only telemetry. |
| WR-003 | PASS locally | `test_transaction_operation_index_classification_is_closed_and_redacted`, cancellation dependency matrices, quota-race and conversation cancellation tests prove quota-only visibility, concealed resource conflicts, retryable dependency mapping, and zero partial effects. |
| WR-004 | PASS locally | `test_issuance_dependency_failure_has_exact_safe_503` and `test_issuance_failure_is_service_unavailable_and_terminal` prove repository/provider issuance failures yield safe `upload_service_unavailable` and leave no consumable orphan. |
| WR-005 | PASS locally | required-key/fingerprint fixtures, `test_stage_a_completed_replay_bypasses_consumed_upload_resolution`, mismatch/new-foreign zero-effect controls, synchronized regular/SSE duplicate convergence, command/quota claim, and AI lease fencing prove one original result and one effect set. |

## Requirement proof

| Requirement | Result | Evidence |
| --- | --- | --- |
| V9PRIV-01 | PASS locally, retained | Verified student Actor owns opaque intents/attachments; missing/foreign/reused/wrong-type states stop before OCR, parsing, association, quota, question, message, or AI effects. Fresh question association remains atomic and OCR receives only the server-resolved immutable tuple. |
| V9PRIV-02 | PASS locally, restored | Exact gateway chunk/aggregate limits, supported type/size/container validation, bounded spool promotion, immutable version/checksum reads, stable error categories, non-consumable cleanup, and opaque public contracts pass positive, boundary, replacement, dependency, quota, and lifecycle negatives. |
| V9PRIV-03 | PASS locally, retained | Student overview/path/lesson/catalog/exercise/mistake projections are answer-free; both correct and incorrect attempts persist before reveal; result reads are owner-scoped; assigned `teacher` and narrow admin answer-read positives pass while anonymous/student/parent/unassigned/stale/wrong-scope teacher negatives remain concealed. |

## D-01 through D-22 executable decision matrix

| Decision | Result | Executable evidence |
| --- | --- | --- |
| D-01 | PASS | JPEG/PNG-only question image acceptance and non-image rejection before OCR. |
| D-02 | PASS | 10 MiB and 4096-pixel image bounds, oversize/dimension/sentinel negatives. |
| D-03 | PASS | JPEG/PNG/PDF/DOCX/PPTX/XLSX/TXT/MD conversation allowlist; legacy/unknown type negatives. |
| D-04 | PASS | 50 MiB document boundary succeeds through bounded spool; max-plus-one fails at sentinel. |
| D-05 | PASS | Extension, declared MIME, magic, image, PDF, OOXML, archive, encryption, and UTF-8 controls fail closed. |
| D-06 | PASS | Intent expiry remains 1,800 seconds and is conditionally enforced. |
| D-07 | PASS | Question identity binding plus versioned exact conversation fingerprint; lost/concurrent regular and SSE replay returns one original result with one effect set. |
| D-08 | PASS | Terminal content failures invalidate; dependency failures are safe/retryable without reviving invalid state. |
| D-09 | PASS | Bounded idempotent cleanup excludes active/consuming/consumed/durable rows and preserves non-consumable tombstones on failure. |
| D-10 | PASS | Durable conversation associations/reference counts persist until explicit release/purge. |
| D-11 | PASS | 5 GiB/15 GiB limits, transaction-authoritative quota race, no auto-deletion, and one chat quota operation per command. |
| D-12 | PASS | Saved attachment reuse increments one logical reference without duplicate bytes/storage charge. |
| D-13 | PASS | Actor is authoritative; public owner/bucket/key/path fields are absent or rejected. |
| D-14 | PASS | Missing and foreign opaque resources return equivalent concealed errors before provider/business effects. |
| D-15 | PASS | Owner-visible expired upload yields stable `upload_expired` reselect guidance. |
| D-16 | PASS | Oversize/type/mismatch/invalid/quota/dependency/checksum/idempotency/in-progress outcomes retain distinct stable codes and safe actions. |
| D-17 | PASS locally | Public bodies, SSE, generated inventory, stored safe results, and captured local logs exclude coordinates, provider/content payloads, OCR/student/model/other-user material, and exception text. |
| D-18 | PASS | Answer result construction requires successful immutable attempt persistence. |
| D-19 | PASS | Only approved directional answer-free hints are available before submission. |
| D-20 | PASS | Preview and result allowlists are structurally separate; all student preview families recursively omit answers/explanations/feedback. |
| D-21 | PASS | Current exact-scope assigned `teacher` and narrow admin answer reads pass; curriculum mutation remains denied. |
| D-22 | PASS | Anonymous, student, parent, and unassigned/stale/disabled/wrong-scope `teacher` controls are concealed. |

Canonical role vocabulary remains exactly `student|parent|teacher|admin`; one account has one role. Public failures remain stable structured `code`, safe `message`, and server correlation fields.

## External evidence boundaries

| External item | Status | Boundary |
| --- | --- | --- |
| Real S3 chunk, version, promotion, overwrite, and immutable read behavior | **NOT RUN** | No separately approved non-production bucket/credentials. Local deterministic fakes do not prove deployed provider policy. |
| Deployed cleanup scheduler/EventBridge/Lambda/IaC, retry, and alarm behavior | **NOT RUN** | Authoritative deployment/IaC evidence is unavailable and remains Phase 479-owned. |
| Production/deployed log-redaction capture | **NOT RUN** | Production access and provider execution were not approved; local caplog evidence only. |

These rows are limitations, not passes. This document and the accompanying validation/manifest intentionally contain no SHA for the commit that later contains them.
