# Phase 473: Student Content Privacy And Practice Integrity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 473-Student Content Privacy And Practice Integrity
**Areas discussed:** 上传文件边界, 上传生命周期与历史保存, 上传错误可见性与附件复用, 练习答案揭示时机

---

## 上传文件边界

| Question | Options considered | Selected |
|----------|--------------------|----------|
| Photo/OCR image formats | JPEG/PNG; add HEIC; add PDF; other | JPEG/PNG; client converts HEIC |
| Image size | 10 MB; 5 MB; 20 MB; other | 10 MB |
| Image dimensions | Client downscales to 4096 px; server resizes; bytes only; other | Client downscales and server enforces 4096 px |
| Type mismatch | Precheck plus post-upload validation; precheck only; validate at submission; server conversion | Precheck plus authoritative post-upload validation |

**User's choice:** Selected the recommended bounded image path for photo questions, then clarified that conversation attachments must also support common documents.
**Notes:** The original JPEG/PNG decision applies to photo-question/OCR input, not to all durable conversation attachments.

---

## 上传生命周期与历史保存

| Question | Options considered | Selected |
|----------|--------------------|----------|
| Transient upload expiry | 30 minutes; 15 minutes; 24 hours; other | 30 minutes |
| Consumption point | Atomic resource creation/association; submit click; validation completion; other | Atomic successful creation and association |
| Failure retry | Retry transient failures but invalidate bad files; always invalidate; always retry; other | Retry transient failures within expiry; bad files become terminal |
| Cleanup | Disable immediately then async delete; synchronous delete; retain; other | Disable immediately then async delete |
| History retention | Until conversation/account deletion; one school year; shorter attachment retention; other | Until conversation deletion or account closure |
| Quota behavior | Block new uploads but preserve access/delete; auto-delete oldest; permit overage; other | Block new uploads; never auto-delete |
| Conversation formats | Images/PDF/DOCX/TXT/MD; add PPTX/XLSX; arbitrary files; other | Add PPTX and XLSX |
| Per-file size | Tiered 10/25/5 MB; all 10 MB; images 10 MB and documents 50 MB; other | Images 10 MB; documents 50 MB |

**User's choice:** Durable conversation history and attachments, with explicit free/paid quotas.
**Notes:** User set free storage to 5 GB and paid storage to 15 GB. Successful binding moves the file out of the transient 30-minute lifecycle.

---

## 上传错误可见性与附件复用

| Question | Options considered | Selected |
|----------|--------------------|----------|
| Missing versus foreign attachment | Same redacted not-found; distinguish forbidden; generic support message; other | Same redacted not-found |
| Owner's expired upload | Structured `upload_expired`; hide as missing; auto-extend; other | `upload_expired` plus reselect action |
| Previously uploaded own file | Re-upload; duplicate bytes; reuse only in original context; owner-authorized reuse | Reuse same immutable bytes through a new association |
| Invalid/service errors | Distinct API codes and friendly UI messages; one generic error; two broad classes; other | Distinct structured codes and actionable UI copy |

**User's choice:** A student should directly reuse their own saved attachment instead of uploading it again.
**Notes:** This corrected the initially proposed “already used, upload again” behavior. Transient upload intents remain single-consumption, while durable saved attachments are reusable and do not consume quota twice.

---

## 练习答案揭示时机

| Question | Options considered | Selected |
|----------|--------------------|----------|
| Earliest standard-answer reveal | First recorded attempt; final retry; lesson completion; teacher release | First successfully recorded attempt |
| Pre-submit help | Non-answer directional hint; no hint; full derivation without final answer; other | Non-answer, non-derivable hint |
| Answer delivery contract | Attempt result only; all endpoints after submit; client-side hiding; other | Attempt result only; previews always answer-free |
| Privileged access | Explicit curriculum capability; all teacher/admin; admin only; any user | User corrected to automatic role-based read access |
| Privileged scope | Assigned teacher plus global admin; all teacher/admin global; author-only teacher plus global admin; other | Assigned course/class teacher; global admin |

**User's choice:** `teacher` and `admin` roles automatically receive answer read access within their decided scope.
**Notes:** This superseded the initially selected explicit-capability proposal. A teacher's automatic answer read access is restricted to assigned courses/classes and does not imply curriculum-edit permission; admin answer read access is global.

---

## the agent's Discretion

- Exact internal error code names other than `upload_expired`.
- Cleanup scheduling, retry/backoff, accounting mechanics, safe parser selection, internal schema names, and exact friendly copy.

## Deferred Ideas

- Broader transaction/ledger convergence remains Phase 475.
- Paid entitlement purchase and recovery remain Phase 476.
- Complete mobile implementation remains Phase 478.
