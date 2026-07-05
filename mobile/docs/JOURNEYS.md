# STOA Mobile Journey Contracts

## Student

- Dashboard reads `/students/me/profile`, `/practice/overview`, and `/notifications`.
- Practice reads `/practice/overview`, `/practice/curriculum/catalog`, `/practice/curriculum/progress`, and `/practice/curriculum/lessons/{lessonId}`.
- Question submission posts to `/questions` and remains online-only.
- Teacher escalation posts to `/questions/{questionId}/request-teacher` or `/practice/teacher-help` and remains online-only.
- Learning history reads `/students/{studentId}/questions`.

## Parent

- Dashboard reads `/parents/me/children`, `/parents/me/subscription`, `/parents/me/account-operations`, and `/notifications`.
- Child summary reads `/parents/me/children/{childId}/summary`, `/usage`, and `/learning-profile`.
- Child history reads `/parents/me/children/{childId}/history`.
- Child report reads `/parents/me/children/{childId}/report`.
- Billing reads `/parents/me/subscription` and `/parents/me/subscription/billing`.

## Screen States

Mobile screens must support loading, ready, empty, blocked, stale, and error states when the surface can be cached. Online-only mutation screens skip stale state because server authority is required.

## No Demo Data

Adapters must use real backend endpoints. Demo data, fixture user IDs, and client-side entitlement guesses are not allowed in authenticated journeys.
