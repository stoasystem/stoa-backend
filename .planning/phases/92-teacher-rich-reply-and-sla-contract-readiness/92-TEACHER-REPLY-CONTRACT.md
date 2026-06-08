# Teacher Reply Contract

**Phase:** 92
**Status:** Complete

## Current Surface

The backend question route currently stores a plain `teacher_response` string through
`POST /teachers/questions/{question_id}/reply`. The active teacher-facing frontend
workflow is the tutor request workspace under `/tutor`, while `/teacher/queue` and
`/teacher/session` are placeholders. Phase 93 should harden the backend contract first;
Phase 94 should surface it in the current tutor workspace and avoid a parallel isolated
teacher UI unless routing is consolidated.

## Allowed Reply Shape

Teacher replies should support:

- Plain text.
- Rich blocks using a versioned JSON payload.
- Paragraph, heading, ordered list, unordered list, quote, and code-text blocks.
- Formula spans or blocks using an allowlisted LaTeX/math string payload.
- Optional structured attachments only if backend-mediated and authorized.

MVP payload:

```json
{
  "version": 1,
  "blocks": [
    {"type": "paragraph", "text": "Move 4 to the right side."},
    {"type": "formula", "latex": "2x + 4 = 10"}
  ]
}
```

Validation limits:

- `version` must be `1`.
- `blocks` length must be between 1 and 20.
- Text block content must be 1 to 2,000 characters after trimming.
- Formula payloads must be 1 to 500 characters after trimming.
- Total plain-text fallback must not exceed 4,000 characters.
- Unsupported block types are refused by the backend, not rendered raw by the frontend.

## Forbidden Reply Content

- Raw unsafe HTML.
- Scripts, event handlers, iframe/embed/object tags.
- Presigned URLs.
- Private image keys.
- Report artifact keys.
- Auth tokens, cookies, passwords, AWS secrets, or raw private storage identifiers.

## Storage Model

Store both:

- `teacher_response`: backward-compatible safe plain-text fallback.
- `teacher_response_text`: safe plain-text fallback.
- `teacher_response_rich`: normalized sanitized rich reply payload.
- `teacher_response_format`: versioned format identifier such as `stoa_teacher_reply_v1`.
- `teacher_first_replied_at`: timestamp for SLA metrics.

The normalized rich payload must be generated server-side from allowed fields only. The
backend must strip private markers from text and formula fields before storage and return
validation errors for raw HTML/script/embed attempts.

## Rendering Rule

Frontend must render only sanitized/allowlisted nodes. Any unsupported block should degrade to safe text instead of rendering raw HTML.

## Refusal Behavior

- Invalid payload shape: HTTP 422.
- Raw unsafe HTML, scripts, embedded objects, presigned URLs, private storage keys, tokens, cookies, passwords, or AWS secret patterns: HTTP 422.
- Reply by a teacher that has not taken over the question: HTTP 403.
- Reply to a missing question: HTTP 404.
- Reply to a question in a terminal invalid state should be refused with HTTP 409.
