---
status: resolved
trigger: "文件上传失败"
created: 2026-07-09
updated: 2026-07-09
---

# Debug Session: file-upload-failed

## Symptoms

- expected: On onboarding step 3, selecting a valid PDF, PNG, or JPEG under 10 MB for "Upload diploma or teaching certificate" uploads successfully and allows the user to continue.
- actual: The page shows a red alert: "File upload failed."
- errors: Frontend message only: "File upload failed." Backend/network details not provided.
- timeline: Not provided.
- reproduction: On teacher onboarding/account type step 3 of 4, fill teaching subjects, years of experience, education background, and short introduction, then use the "Upload diploma or teaching certificate" upload button.
- screenshot: /var/folders/13/jgb8c061583ggg622pgv9l0c0000gp/T/codex-clipboard-ac5a2472-32af-4f8f-9fb0-7bec4a4fb526.png

## Current Focus

- hypothesis: Backend presign validation rejects PDF certificates even though the onboarding UI allows PDF, PNG, or JPEG.
- test: Add/execute route tests for PDF presign, image presign, and extension/content-type mismatch.
- expecting: PDF requests with filename .pdf and content_type application/pdf return a presigned URL; image uploads still work; mismatched pairs return 422.
- next_action: resolved
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-07-09
  observation: Screenshot upload copy says "PDF, PNG, or JPEG. Maximum 10 MB." and frontend shows "File upload failed."
- timestamp: 2026-07-09
  observation: src/stoa/routers/files.py only allowed image extensions and rejected any content_type that did not start with image/*.
- timestamp: 2026-07-09
  observation: Added tests in tests/test_files.py; .venv/bin/python -m pytest tests/test_files.py passed.
- timestamp: 2026-07-09
  observation: .venv/bin/python -m pytest tests/test_questions.py passed, confirming existing image-question flow was not regressed.

## Eliminated

- hypothesis: Upload route is not registered.
  reason: src/stoa/main.py includes files.router at /files.

## Resolution

- root_cause: The backend /files/presign request schema was out of sync with the onboarding UI. The UI permitted PDF certificates, but PresignRequest only accepted image extensions and image/* content types.
- fix: Allow .pdf with application/pdf, keep image support, and require extension/content-type pairs to match.
- verification: .venv/bin/python -m pytest tests/test_files.py; .venv/bin/python -m pytest tests/test_questions.py; .venv/bin/python -m ruff check src/stoa/routers/files.py tests/test_files.py
- files_changed: src/stoa/routers/files.py, tests/test_files.py
