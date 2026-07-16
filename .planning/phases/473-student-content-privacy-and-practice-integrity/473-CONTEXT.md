# Phase 473: Student Content Privacy And Practice Integrity - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase establishes safe student upload, attachment-retention, ownership, reuse, validation, and practice-answer contracts. It prevents one user from referencing another user's content, prevents raw storage details or OCR material from leaking, preserves successfully attached conversation history within explicit quotas, and separates answer-free student preview responses from post-submission and privileged answer-bearing responses.

An upload intent is single-consumption and short-lived; a successfully saved attachment is a durable, owner-scoped resource that may be reused through its opaque attachment ID. Broader question quota/ledger transactions remain Phase 475, billing purchase/recovery remains Phase 476, and final mobile journey implementation remains Phase 478.

</domain>

<decisions>
## Implementation Decisions

### Upload file boundaries
- **D-01:** Photo-question/OCR uploads accept only JPEG and PNG. HEIC must be converted to JPEG by the client before upload.
- **D-02:** Images are limited to 10 MB each and a longest edge of 4096 pixels. The client should downscale before upload, and the server must independently enforce both limits.
- **D-03:** Conversation attachments support JPEG, PNG, PDF, DOCX, PPTX, XLSX, TXT, and MD. Legacy DOC, PPT, and XLS are not supported in the first release.
- **D-04:** Non-image conversation documents are limited to 50 MB each; images retain the 10 MB limit.
- **D-05:** Obvious unsupported types are rejected before upload. After upload, the server validates extension, declared MIME type, detected/magic-byte type, size, and image dimensions. A mismatch or invalid file makes the upload unusable and requires a new file selection.

### Upload lifecycle, history, and quotas
- **D-06:** An unbound upload intent expires after 30 minutes.
- **D-07:** An upload intent becomes consumed only when question/conversation creation and attachment association succeed together. A replay of the same idempotent request returns the original result; the transient intent cannot be attached to a different resource.
- **D-08:** A transient system failure releases/resumes the attempt for retry within the original validity period. Type, size, integrity, or content-validation failure permanently invalidates that upload intent.
- **D-09:** Expired, invalid, or abandoned uploads become unusable immediately and are deleted asynchronously. Cleanup failure must never restore usability.
- **D-10:** Successfully bound conversations and attachments persist until the student deletes the conversation or closes the account. The 30-minute transient-upload expiry does not apply after successful binding.
- **D-11:** Attachment storage quotas are 5 GB for the free tier and 15 GB for the paid tier. At the limit, new uploads are blocked while viewing, downloading, and deleting existing attachments remain available. The system never deletes old attachments automatically to make room.
- **D-12:** A student may reuse an existing saved attachment through its opaque attachment ID. The server rechecks ownership and active state, creates a new logical association to the same immutable stored object, and does not charge storage quota again.

### Ownership and safe upload errors
- **D-13:** The verified Actor is authoritative. Client-supplied student IDs, object keys, bucket names, or storage paths never establish ownership.
- **D-14:** A missing attachment and an attachment owned by someone else have the same external behavior: a redacted not-found response and a UI instruction to select/upload the file again. The response must not reveal whether the foreign attachment exists.
- **D-15:** An owner-visible expired transient upload uses structured API code `upload_expired`; the UI says the upload expired and asks the student to select the file again.
- **D-16:** Oversize, unsupported type, content/type mismatch or corruption, and temporary service failure use distinct stable API codes/actions. UI copy remains short, friendly, and actionable.
- **D-17:** API responses, logs, evidence, and UI errors must not expose raw object keys, storage paths, internal provider names, raw OCR text, or another user's content.

### Practice-answer reveal contracts
- **D-18:** A student may see the standard answer only after the first answer has been successfully recorded. A click, request receipt, timeout, or failed write does not unlock the answer.
- **D-19:** Before a recorded submission, the student may receive directional hints only when they neither contain the answer nor allow the answer to be directly derived. Full explanations are post-submission content.
- **D-20:** Standard answers and full explanations are returned only by an attempt-result contract tied to that student's recorded attempt. Student preview, question, lesson, course overview, and course path contracts always remain answer-free; the client must never receive answers early and merely hide them in the UI.
- **D-21:** A `teacher` automatically has read access to answers and explanations only for courses or classes they are assigned to. An `admin` automatically has read access to all answers and explanations. This read access does not grant a teacher curriculum-edit permission.
- **D-22:** Unauthenticated users, `student`, `parent`, and unassigned `teacher` actors cannot access pre-submission answer-bearing contracts.

### the agent's Discretion
- Choose exact structured error-code names other than the locked `upload_expired`, while preserving the decided distinctions and client actions.
- Choose cleanup scheduling, retry backoff, storage accounting implementation, and safe document-validation/parsing libraries.
- Choose internal schema/table names and opaque identifier formats, provided raw storage locations never become resource identifiers.
- Define the exact wording of friendly UI messages without changing their required action or revealing hidden state.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and requirements
- `.planning/ROADMAP.md` — Phase 473 goal, dependencies, likely slices, success criteria, evidence, and exit gate.
- `.planning/REQUIREMENTS.md` — V9PRIV-01 through V9PRIV-03 upload ownership, validation, and answer-integrity requirements.
- `.planning/PROJECT.md` — Product context and milestone-wide constraints.

### Authorization foundation
- `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-CONTEXT.md` — Verified Actor authority, one-role account model, canonical `teacher` terminology, resource authorization, and safe error behavior inherited by this phase.

### Audit evidence
- `docs/audit/full-project-audit.md` — SEC-003, SEC-005, and BUG-001 analysis and remediation expectations.
- `docs/audit/findings.json` — Machine-readable audit finding inventory and severity/evidence metadata.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/routers/files.py` — Existing user-scoped S3 presign flow is the integration point for upload intents, constrained policies, quota checks, and post-upload validation.
- `src/stoa/services/ocr_service.py` — Existing OCR integration can remain behind an owner-validated attachment service; callers must no longer pass arbitrary bucket/key pairs directly.
- Phase 472 actor/resource authorization components — Reuse the verified Actor and centralized authorization policy rather than creating upload-specific identity shortcuts.

### Established Patterns
- API failures use stable structured codes/actions and redacted safe messages; client UI translates them into simple actionable copy.
- Resource existence is concealed when the actor is not entitled to know it exists.
- Accounts have one canonical role: `student`, `parent`, `teacher`, or `admin`; active vocabulary is `teacher`, never `tutor`.

### Integration Points
- `src/stoa/routers/questions.py` currently accepts an arbitrary image S3 key; replace this with owner-scoped transient upload or saved-attachment identifiers and atomic association.
- `src/stoa/routers/practice.py` currently builds answer-bearing responses; split preview and attempt-result schemas and migrate every student-facing curriculum route to the answer-free contract.
- Conversation/question serializers must preserve attachment identity and safe metadata while omitting object keys and raw OCR text.

</code_context>

<specifics>
## Specific Ideas

- Treat “temporary upload” and “saved attachment” as different lifecycle states: the former expires and is single-consumption; the latter supports durable history and owner-authorized reuse.
- Reuse points to the same immutable stored bytes through a new logical association, so the student does not upload or pay quota for the same file twice.
- Friendly UI examples include “上传已过期，请重新选择文件上传”, “文件过大”, “不支持此格式”, “文件可能已损坏，请重新选择”, and “上传服务暂时不可用，请稍后重试”.

</specifics>

<deferred>
## Deferred Ideas

- Phase 475 owns broader question quota/ledger transactional convergence and reconciliation; Phase 473 still owns atomic attachment association and upload-intent consumption.
- Phase 476 owns paid-plan purchase, webhook idempotency, and entitlement recovery; Phase 473 consumes the authoritative effective tier to enforce 5 GB versus 15 GB.
- Phase 478 owns the complete mobile attachment picker, conversion, progress, quota, history, reuse, and practice-result journeys against these contracts.

</deferred>

---

*Phase: 473-Student Content Privacy And Practice Integrity*
*Context gathered: 2026-07-16*
