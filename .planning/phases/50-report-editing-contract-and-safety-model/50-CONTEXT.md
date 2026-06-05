# Phase 50 Context

**Phase:** 50 - Report Editing Contract And Safety Model
**Milestone:** v2.0 Controlled Report Editing MVP
**Created:** 2026-06-05

## Context

v2.0 adds a controlled report editing MVP. The MVP is intentionally metadata-first:

- create an edit draft
- read an edit draft
- apply a draft
- write append-only audit

Raw HTML/JSON artifact rewriting is deferred. The frontend never receives S3 keys, presigned URLs, raw HTML, or raw JSON.

