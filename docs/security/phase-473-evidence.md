# Phase 473 student content privacy and practice integrity evidence

Evidence window: 2026-07-16T11:54:27Z–2026-07-16T11:56:38Z UTC  
Tested source SHA: `671612b017bc392f587a8c6dd8d3e9bb09ddffc6`  
Environment: local offline test process in `/Users/zhdeng/stoa-backend`  
Safety statement: **no production mutation, AWS call, provider call, network access, live S3 upload/delete, external schedule invocation, identity change, billing effect, or student-data mutation was performed.** Provider, table, object, content, and actor effects used deterministic local fakes only.

## Source-bound artifacts

| Artifact | SHA-256 | Result |
| --- | --- | --- |
| `docs/security/route-authorization-inventory.json` | `2d072ad391724100647b1d7a9862660730a0b358268cf37b65481fba727253b3` | 222 registered operations; two generations were byte-identical, matched the checked file, and `--check` passed |
| `tests/test_files.py` | `2e81ef2f716e618e604eb5a50da78330907caadfa832aef486a95efcb494a432` | opaque presign/finalize and concealed missing/foreign route contracts |
| `tests/test_attachment_security.py` | `0b5bdaf362d4b48dc61081538f28fa2961fb0cc29a895084d17199878bd86158` | validation, lifecycle, quota, reuse, OCR, retention, cleanup, and redaction controls |
| `tests/test_questions.py` | `a482dda3240e9e123c0bcbceb95309691d8adf638a41baf0983edc5ab672538e` | owner-resolved OCR, atomic association, idempotency, and safe response controls |
| `tests/test_conversations.py` | `90e1c278178bfb46f08111ab00545d0d524536212792fb49dd0eed3b89ee7d92` | regular/stream/history attachment parity and safe summary controls |
| `tests/test_practice.py` | `416c2f183c01e3070479aa595e32b0e403d59fe4ce925d9e12740967a2cce0ad` | write-before-result, owner result, and safe hint controls |
| `tests/test_practice_privacy.py` | `08abcdfa6ed50bcbc55cd406679aabb641c61e92f5f773db483c1e0478732b47` | recursive preview, result, privileged answer, schema, and scope controls |
| `tests/test_curriculum_rollout.py` | `c1d6d818534172bc58dac4c418e6aedddd60008127dcb8ebf62d51fa0a1380b3` | answer-free lesson/exercise and ignored answer-toggle controls |
| `tests/test_route_authorization_inventory.py` | `2fd3ddc98ef9e8b9bc2eab883c75b780da03ca5eefd7aaf67a735a604d7bcaa1` | executable runtime/OpenAPI/checked inventory equivalence |
| `tests/test_student_authorization_matrix.py` | `1fcb2450294a01b57689773023a53b279904843e2a67aec8c66ab9e65c289c38` | assigned/wrong/stale teacher, admin, student, and parent answer matrix |

The tested source commit contains the bounded cleanup implementation and all test digests above. Evidence-document and tracking changes are intentionally outside that tested production source SHA.

## Exact commands and observed results

| UTC | Exact command | Result |
| --- | --- | --- |
| 2026-07-16T11:54:27Z | `.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py tests/test_questions.py tests/test_conversations.py tests/test_practice.py tests/test_practice_privacy.py tests/test_curriculum_rollout.py tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` | PASS — 230 passed in 2.37s; no skip or xfail |
| 2026-07-16T11:54:39Z | `.venv/bin/python scripts/generate_route_authorization_inventory.py --output /tmp/phase473-route-inventory-1.json; .venv/bin/python scripts/generate_route_authorization_inventory.py --output /tmp/phase473-route-inventory-2.json; cmp /tmp/phase473-route-inventory-1.json /tmp/phase473-route-inventory-2.json; cmp /tmp/phase473-route-inventory-1.json docs/security/route-authorization-inventory.json; .venv/bin/python scripts/generate_route_authorization_inventory.py --check; shasum -a 256 docs/security/route-authorization-inventory.json` | PASS — both generated files and the checked file were byte-identical; digest recorded above |
| 2026-07-16T11:55:04Z | `.venv/bin/python -m pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_public_identity_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | PASS — 635 passed in 8.21s |
| 2026-07-16T11:56:05Z | `.venv/bin/python -m pytest -p no:terminal --junitxml=/tmp/phase473-full.xml` | OBSERVED GREEN — complete JUnit XML reports 1232 tests, 0 failures, 0 errors, 0 skipped, aggregate test time 32.517s |
| after evidence creation | `rg -n -f /tmp/phase473-private-canaries.txt docs/security/phase-473-evidence.md` | PASS when the command returns no matches; the private denylist values remain only in local test fixtures and the temporary file |

## Requirements and audit findings

| Item | Local closure evidence | Positive and zero-effect controls |
| --- | --- | --- |
| V9PRIV-01 / SEC-003 | Opaque owner upload or saved-attachment references replace caller-selected storage coordinates; fresh question reservation precedes OCR and the final question/attachment/consumption/byte charge is conditional and atomic | own validated image succeeds; missing, foreign, expired, invalid, non-image, reused, raced, and mismatched-idempotency inputs stop before counter/OCR/question effects |
| V9PRIV-02 / SEC-005 | Exact POST bounds plus authoritative HEAD/bounded-byte validation cover supported formats, size, MIME, magic, image, archive, encryption, and UTF-8 controls; terminal and expired unconsumed uploads enter bounded conditional cleanup | supported boundary fixtures pass; malformed/oversize/mismatch fixtures become unusable; provider failures expose only stable codes; cleanup retries never restore validated state |
| V9PRIV-03 / BUG-001 | Typed preview allowlists cover overview, path, lesson, catalog, exercise, and mistake preview; answer-bearing result construction requires a durable owner attempt | correct and incorrect attempts persist before reveal; failed writes reveal nothing; assigned teacher/global admin positives pass while anonymous, student, parent, unassigned, stale, disabled, and wrong-scope teacher controls are concealed |

## D-01 through D-22 decision matrix

| Decisions | Passing evidence in the combined command |
| --- | --- |
| D-01–D-05 | Supported JPEG/PNG and conversation document fixtures plus unsupported, MIME/magic mismatch, size, dimension, unsafe archive, encrypted, binary-text, and corruption controls in `test_attachment_security.py`; exact constrained route contracts in `test_files.py` |
| D-06–D-08 | 1800-second intent contract, owner/expiry/version transitions, authoritative finalize, permanent content invalidation, and transient question reservation release retaining original expiry |
| D-09 | bounded conditional cleanup covers expired, invalid, abandoned, retry, reordered, invalid-cursor, active, consuming, consumed, and durable-reference states; only eligible unconsumed bytes are deleted by fake S3 |
| D-10 | reference-counted conversation history and account purge retain durable bytes until the last explicit resource reference is released |
| D-11 | authoritative free/paid storage limits, preflight plus transactional quota condition, and no automatic history deletion |
| D-12 | saved attachment reuse creates a new association/reference without a storage update or duplicate object |
| D-13–D-14 | verified Actor owns every intent/resource; client owner/storage fields fail schema validation; missing and foreign resources have identical safe outcomes before provider effects |
| D-15–D-16 | `upload_expired` and the exhaustive stable attachment error/action registry cover size, unsupported type, mismatch/corruption, quota, and temporary service recovery |
| D-17 | public schemas, error bodies, question/history responses, captured logs, and this evidence exclude raw storage coordinates, extracted/OCR content, provider payloads, tokens, and raw actor identifiers |
| D-18–D-20 | every correct/incorrect answer is immutable before result construction; preview families are recursively answer-free; only owner attempt-result and explicit privileged schemas contain answer material |
| D-21 | exact current assignment coordinates authorize a teacher; admin receives only the narrow curriculum-answer read; neither path grants curriculum mutation |
| D-22 | anonymous, student, parent, unassigned, stale, disabled, unrelated, and wrong-scope teachers cannot access the privileged answer contract |

## Generated route and OpenAPI contract

The 222-row inventory is generated from the registered FastAPI dependency graph. Runtime, OpenAPI `x-stoa-authorization`, and checked JSON are asserted equivalent. It includes executable metadata for nested `uploadId`/`attachmentId` commands and path-bound `attempt_id`/`challenge_id` result and privileged-answer resources. Mutation tests fail closed for missing or incompatible authorization metadata.

## Privacy canaries

Local fixtures seed distinct storage-coordinate, file/document content, OCR content, submitted-answer, provider-diagnostic, token, and raw-student identifier values. The combined tests assert that these values may reach only the intended private fake/provider boundary and never public bodies, logs, generated inventory, or answer-free schemas. A separate temporary-file denylist scan verifies this evidence document without copying the private values into it.

## Full-suite delta and ownership boundaries

The supplied pre-plan baseline was 1229 passing tests. This plan adds three cleanup tests; the source-bound full-suite JUnit observation is 1232 tests with zero failures, errors, or skips. Historical Phase 474 evidence recorded 23 strict production-Settings fixture failures, but those failures are not present in this checkout and were not weakened, edited, reassigned, or represented as Phase 473 work.

- Phase 475 retains broader question quota/ledger/question convergence, attempt analytics consistency, assignment-write consistency, parent binding repair, and concurrency remediation.
- Phase 476 retains checkout/provider/local billing idempotency and paid-entitlement recovery.
- Phase 478 retains web/mobile upload, history, practice-result, retry, and offline journey implementation.
- Phase 479 retains authoritative IaC, S3 lifecycle/schedule ownership, and deployed cleanup scheduling.
- Phase 480 retains production log-redaction captures, pagination/load evidence, alarms, staged deployment, and rollback.

## External evidence gate

| Manual item | Status | Result / limitation |
| --- | --- | --- |
| Real presigned S3 POST boundary uploads | NOT RUN — no separately approved non-production bucket or credentials | local fake policy and authoritative finalize tests pass; no live bucket-policy or provider behavior is inferred |
| Scheduled cleanup Lambda/EventBridge/IaC invocation | NOT RUN — authoritative IaC and schedule evidence are Phase 479 owned and unavailable here | local handler/service tests pass with fake S3/table only; no deployed schedule is claimed |
| Production log-redaction/provider capture | NOT RUN — production access/mutation not approved and Phase 480 owned | local captured-log and response redaction tests pass only |

These NOT RUN rows are release limitations, not passing external evidence.
