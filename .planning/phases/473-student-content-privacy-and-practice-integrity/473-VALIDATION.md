---
phase: 473
slug: student-content-privacy-and-practice-integrity
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-16
---

# Phase 473 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with FastAPI TestClient, moto/fakes and monkeypatch |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest -q tests/test_attachment_security.py tests/test_practice_privacy.py` |
| **Full phase command** | `.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py tests/test_questions.py tests/test_conversations.py tests/test_practice.py tests/test_practice_privacy.py tests/test_curriculum_rollout.py tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` |
| **Estimated runtime** | ~45–90 seconds |

---

## Sampling Rate

- **After every task commit:** Run the task's focused pytest command.
- **After every plan wave:** Run all Phase 473 test modules touched through that wave.
- **Before `$gsd-verify-work`:** Run the full phase command plus the Phase 472 authorization regression subset.
- **Max feedback latency:** 120 seconds for focused commands.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 473-01-01 | 01 | 1 | V9PRIV-01/02 | T-UPLOAD-ID | Opaque owner-scoped contracts and redacted errors | contract | `.venv/bin/python -m pytest -q tests/test_attachment_security.py -k 'contract or error or redaction'` | ❌ W0 | ⬜ pending |
| 473-01-02 | 01 | 1 | V9PRIV-03 | T-ANSWER-PREVIEW | Preview/result schemas are structurally separate | contract | `.venv/bin/python -m pytest -q tests/test_practice_privacy.py -k 'schema or preview or result'` | ❌ W0 | ⬜ pending |
| 473-02-01 | 02 | 2 | V9PRIV-02 | T-UPLOAD-TYPE | Bytes/type/size/dimension/container checks fail closed | unit | `.venv/bin/python -m pytest -q tests/test_attachment_security.py -k 'validate or mime or magic or size or dimension or archive'` | ❌ W0 | ⬜ pending |
| 473-02-02 | 02 | 2 | V9PRIV-01/02 | T-UPLOAD-RACE | Intent ownership, expiry, quota and consumption are conditional | repository | `.venv/bin/python -m pytest -q tests/test_attachment_security.py -k 'intent or quota or consume or transaction'` | ❌ W0 | ⬜ pending |
| 473-02-03 | 02 | 2 | V9PRIV-02 | T-UPLOAD-PROVIDER | Presign/finalize errors are stable and provider-redacted | route | `.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py -k 'presign or finalize or unavailable or expired'` | ✅/❌ W0 | ⬜ pending |
| 473-03-01 | 03 | 3 | V9PRIV-01/02 | T-ATTACHMENT-REUSE | Conversation history binds owner attachments and reuses bytes once | integration | `.venv/bin/python -m pytest -q tests/test_conversations.py tests/test_attachment_security.py -k 'attachment or reuse or quota or history'` | ✅/❌ W0 | ⬜ pending |
| 473-04-01 | 04 | 3 | V9PRIV-01 | T-OCR-FOREIGN | Only validated owner attachment reaches OCR | integration | `.venv/bin/python -m pytest -q tests/test_questions.py tests/test_attachment_security.py -k 'ocr or attachment or foreign or idempot'` | ✅/❌ W0 | ⬜ pending |
| 473-05-01 | 05 | 2 | V9PRIV-03 | T-ANSWER-PREVIEW | All student preview families omit answer-derived fields | snapshot | `.venv/bin/python -m pytest -q tests/test_practice.py tests/test_practice_privacy.py -k 'overview or path or lesson or catalog or preview'` | ✅/❌ W0 | ⬜ pending |
| 473-05-02 | 05 | 2 | V9PRIV-03 | T-ANSWER-WRITE | Answer appears only after durable attempt write | repository/route | `.venv/bin/python -m pytest -q tests/test_practice_privacy.py -k 'attempt or result or write or failure'` | ❌ W0 | ⬜ pending |
| 473-06-01 | 06 | 3 | V9PRIV-03 | T-ANSWER-SCOPE | Assigned teacher and admin scopes are exact | authorization matrix | `.venv/bin/python -m pytest -q tests/test_practice_privacy.py tests/test_student_authorization_matrix.py -k 'answer or teacher or admin or assignment'` | ✅/❌ W0 | ⬜ pending |
| 473-07-01 | 07 | 4 | V9PRIV-01/02 | T-UPLOAD-CLEANUP | Expired/invalid objects stay unusable and cleanup is idempotent | job | `.venv/bin/python -m pytest -q tests/test_attachment_security.py -k 'cleanup or expired or invalid'` | ❌ W0 | ⬜ pending |
| 473-07-02 | 07 | 4 | V9PRIV-01/02/03 | ALL | Combined route/OpenAPI/privacy gate passes | integration | `.venv/bin/python -m pytest -q tests/test_files.py tests/test_attachment_security.py tests/test_questions.py tests/test_conversations.py tests/test_practice.py tests/test_practice_privacy.py tests/test_curriculum_rollout.py tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` | ✅/❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_attachment_security.py` — upload formats, ownership, state machine, quota, transaction, redaction and cleanup fixtures.
- [ ] `tests/test_practice_privacy.py` — recursive preview leak checks, attempt-result ordering and privileged answer scope fixtures.
- [ ] Extend existing fake S3/table/Actor helpers without ambient AWS or network access.
- [ ] Add valid JPEG/PNG/PDF/OOXML/text fixtures plus malformed, oversized, mismatch, traversal and decompression-bomb controls.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| S3 presigned POST rejects an over-limit real upload | V9PRIV-02 | Requires an approved non-production bucket and credentials | Create 10 MiB/50 MiB boundary uploads and one byte-over upload; record redacted status only. If approval/config is absent, mark NOT RUN. |
| Cleanup handler deletes expired objects on schedule | V9PRIV-02 | Schedule/IaC is outside this repository and owned by Phase 479 | Invoke handler locally with fake S3 for automated proof; record external schedule as NOT RUN until authoritative IaC is imported. |

---

## Validation Sign-Off

- [x] All planned tasks have focused automated commands or explicit Wave 0 dependencies.
- [x] Sampling continuity has no three consecutive tasks without automated verification.
- [x] Wave 0 covers all new fixture modules.
- [x] No watch-mode flags are used.
- [x] Focused feedback latency target is under 120 seconds.
- [x] `nyquist_compliant: true` is set.

**Approval:** pending execution
