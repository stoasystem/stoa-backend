# Teacher Reply Contract

**Phase:** 92
**Status:** Planned

## Allowed Reply Shape

Teacher replies should support:

- Plain text.
- Markdown-like emphasis and lists if sanitized.
- Formula spans or blocks using an allowlisted LaTeX/math payload.
- Optional structured attachments only if backend-mediated and authorized.

## Forbidden Reply Content

- Raw unsafe HTML.
- Scripts, event handlers, iframe/embed/object tags.
- Presigned URLs.
- Private image keys.
- Report artifact keys.
- Auth tokens, cookies, passwords, AWS secrets, or raw private storage identifiers.

## Storage Model

Store both:

- `teacher_response_text`: safe plain-text fallback.
- `teacher_response_rich`: normalized sanitized rich reply payload.
- `teacher_response_format`: versioned format identifier.
- `teacher_first_replied_at`: timestamp for SLA metrics.

## Rendering Rule

Frontend must render only sanitized/allowlisted nodes. Any unsupported block should degrade to safe text instead of rendering raw HTML.
