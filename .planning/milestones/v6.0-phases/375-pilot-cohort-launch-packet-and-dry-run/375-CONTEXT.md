# Phase 375 Context

## Phase Boundary

Phase 375 assembles the first cohort operating packet and dry-runs the pilot path before any real cohort is enabled.

## Decisions

- The launch packet must include cohort scope, account aliases, communication plan, consent state, support staffing, teacher owner, launch room, dashboards, rollback authority, and pause criteria.
- Dry run coverage must include login, onboarding, entitlement, usage, first learning action, notification/support touchpoints, mobile path, and admin visibility.
- Missing packet areas or a missing dry run block start.

## Existing Code Insights

- Existing launch-room and cohort helpers already model rollback, support, dashboard, and start-gate behavior.
- v6 adds a current launch-packet readiness layer that can feed the final decision gate.
