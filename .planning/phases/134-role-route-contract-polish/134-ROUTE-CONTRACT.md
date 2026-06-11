# Phase 134 Adaptive Route Locale Contract

**Phase:** 134
**Requirement:** I18N-02
**Date:** 2026-06-11

## Selected Route Surface

Phase 134 applies locale metadata to the adaptive learning surface because it spans all target roles:

| Role | Route examples | Metadata behavior |
|------|----------------|-------------------|
| Student | `/adaptive/students/me/memory`, `/adaptive/students/me/assignments`, assignment transitions | Response includes `locale.effectiveLocale` and stable canonical learning/assignment fields. |
| Parent | `/adaptive/parents/me/children/{student_id}/progress` | Response includes locale metadata and keeps compact active/completed assignment slices. |
| Tutor | `/adaptive/students/{student_id}/memory/refresh`, `/adaptive/assignments` | Response includes locale metadata while preserving reviewed assignment status and answer-key visibility rules. |
| Admin | `/adaptive/assignments`, `/adaptive/students/{student_id}/memory` | Response includes locale metadata without changing admin authorization or canonical values. |

## Metadata Shape

```json
{
  "locale": {
    "effectiveLocale": "de",
    "contentLanguage": "de",
    "supportedLocales": ["de", "en"],
    "canonicalValuesStable": true
  }
}
```

## Canonical Values That Remain Locale-Neutral

- `studentId`
- `assignmentId`
- `status`
- `sourceType`
- `sourceId`
- `subject`
- `topicId` / `topicIds`
- `roleView`
- `freshness.status`
- `reviewRequired`
- `autonomousDecision`
- timestamps such as `createdAt`, `updatedAt`, `completedAt`

## Mobile-Friendly Contract Notes

- Assignment list responses retain `count` and `items` for compact rendering.
- Parent progress retains bounded `assignments` and `completedAssignments` slices capped to five active/completed records.
- Memory responses keep list/detail-ready fields and add metadata rather than duplicating localized content.
- Backend still performs no device or browser sniffing.

## Deferred Route Surfaces

The same metadata pattern can be extended later to billing, moderation, reports, notifications, and admin operations. Phase 134 intentionally starts with adaptive learning because it is role-crossing and directly tied to v4.0's product surface.
