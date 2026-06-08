# Summary: Phase 96 Content Moderation Contract And Data Model

**Status:** Complete
**Completed:** 2026-06-08
**Requirement:** MOD-01

## Outcome

Phase 96 defined the v3.2 moderation MVP contract before implementation. The contract covers reportable surfaces, moderation case fields, lifecycle statuses, user-facing report creation, admin list/detail/action APIs, data access assumptions, and functional verification priorities.

## Key Decisions

- Moderation supports question content, AI answer, and teacher reply report surfaces.
- Case lifecycle is `open`, `in_review`, `actioned`, `dismissed`, and `closed`.
- MVP storage should reuse the existing DynamoDB single-table pattern and use bounded admin scans unless Phase 97 proves an index is required.
- v3.2 stays product-focused and avoids compliance-grade legal workflow scope.

## Verification

- `96-MODERATION-CONTRACT.md` defines the required case shape and workflow.
- `STOA_DOCS_FEATURE_GAP_AUDIT.md` marks moderation as active v3.2.
- `.planning/REQUIREMENTS.md` maps MOD-01 to Phase 96.
- `.planning/ROADMAP.md` maps v3.2 to Phases 96-99.
