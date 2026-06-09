# Subscription Operations Contract: v3.3 MVP

## Plan Tiers

| Tier | AI Daily Limit | Teacher Support | Weekly Report |
|------|----------------|-----------------|---------------|
| Free | 5 | none | none |
| Standard | 30 | text support | enabled |
| Premium | unlimited | priority support | enhanced/enabled |

## Parent Request Lifecycle

Statuses:

- `requested`
- `in_review`
- `approved`
- `applied`
- `rejected`
- `cancelled`

Request types:

- `upgrade`
- `downgrade`
- `cancel`

Minimum fields:

- `request_id`
- `parent_id`
- `student_id` optional for child-specific subscriptions
- `current_tier`
- `requested_tier`
- `request_type`
- `status`
- `source`: `parent_portal`, `admin_created`, `manual_import`
- `parent_note`
- `admin_note`
- `created_at`
- `updated_at`
- `effective_at`
- `applied_at`
- `applied_by`
- `history`

## API Shape

Parent:

- `GET /parents/me/subscription`
- `POST /parents/me/subscription/requests`
- `GET /parents/me/subscription/requests`

Admin:

- `GET /admin/subscriptions/requests`
- `GET /admin/subscriptions/requests/{request_id}`
- `PATCH /admin/subscriptions/requests/{request_id}`
- `POST /admin/subscriptions/requests/{request_id}/apply`

## Data Access Plan

Preferred DynamoDB shape:

- Request row: `PK=SUBSCRIPTION_REQUEST#<request_id>`, `SK=SUMMARY`
- Parent mirror/query fields for pilot list access: `parent_id`, `status`, `requested_tier`, `created_at`
- History rows: `PK=SUBSCRIPTION_REQUEST#<request_id>`, `SK=EVENT#<timestamp>#<event_id>`

Phase 101 should reuse the existing single-table design and bounded admin scans for pilot volume unless an existing GSI can support a cleaner status/date list.

## Functional Verification Priorities

- Parent can view current plan and benefits.
- Parent can submit upgrade/downgrade/cancel intent.
- Admin can list, filter, open, approve/reject/cancel, and apply a request.
- Applying a request updates `subscription_tier` consistently with existing quota behavior.
- Stripe/TWINT remains future scope and no payment is attempted.
