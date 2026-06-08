# Phase 90 Context: OCR Correction And Daily Question Quota Hardening

## Purpose

Bring question intake closer to the `stoa_docs` MVP by supporting corrected OCR text and robust daily quota enforcement.

## Existing State

- Question submission accepted optional `image_s3_key`.
- OCR text was appended to submitted content when Rekognition returned text.
- The final submitted text and OCR source state were not separately recorded.
- Daily quota counted today's questions by scanning the latest 200 question rows, which can miss older same-day records beyond the page limit.
- `QuestionResponse` exposed `image_s3_key`.

## Constraints

- Keep OCR failure non-fatal.
- Do not expose private image object keys in API responses.
- Keep student ownership checks unchanged.
- Preserve enough OCR source metadata for debugging without returning raw private storage identifiers.

