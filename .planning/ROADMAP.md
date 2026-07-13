# Roadmap: v8.4 Strategic Scale Reliability And Next-Version Decision

**Status:** Completed
**Created:** 2026-07-09
**Prior milestone:** v8.3 Learning Outcomes Scale And AI Curriculum Improvement

## Goal

Make a strategic scale decision after live rollout, growth, revenue, learning, support, and operations evidence. v8.4 decides scale growth, hold, rollback, remediation, market expansion, enterprise readiness, or v9 focus.

## Function Purpose

- Prevent growth from outpacing support, learning quality, revenue reliability, mobile/provider reliability, or incident response.
- Convert live evidence into a strategic roadmap decision.
- Decide whether to scale, hold, remediate, or open a new strategic track.

## Implementation Strategy

- Review customer success, revenue, retention, learning outcomes, support load, teacher load, mobile reliability, provider health, acquisition quality, incidents, releases, and data quality.
- Identify bottlenecks, strategic opportunities, and stop criteria.
- Keep market/language expansion, enterprise sales, paid marketing scale, and AI autonomy separately approved.
- Close with scale, hold, rollback, remediation, or v9 recommendation.

## Phases

- [x] **Phase 467: Strategic Product Business Operations Review** - Review customer success, revenue, retention, learning, support, teacher, mobile, provider, acquisition, incidents, and roadmap feedback.
- [x] **Phase 468: Reliability Data Quality And Release Scale Review** - Review reliability, data quality, dashboards, alerts, migrations, rollback, release cadence, and operational ownership.
- [x] **Phase 469: Market Expansion Enterprise And Localization Options** - Evaluate market/language expansion, enterprise readiness, school partnerships, localization, and support implications.
- [x] **Phase 470: AI Autonomy Growth And Governance Options** - Evaluate AI autonomy, paid marketing scale, growth loops, compliance, privacy, and governance options.
- [x] **Phase 471: Strategic Scale Decision Gate** - Decide scale growth, hold, rollback, remediation, market expansion, enterprise readiness, or v9 focus.

## Phase Details

### Phase 467: Strategic Product Business Operations Review

**Goal**: Review customer success, revenue, retention, learning, support, teacher, mobile, provider, acquisition, incidents, and roadmap feedback.
**Depends on**: v8.3 Learning Outcomes Scale And AI Curriculum Improvement.
**Requirements**: V8STRAT-01
**Success Criteria**:

1. Customer success, revenue, retention, learning outcomes, support load, teacher workload, mobile reliability, provider health, acquisition quality, incidents, and roadmap feedback are reviewed.
2. Findings are grouped into customer value, revenue/growth, learning quality, operations, reliability, and strategic opportunities.
3. Each risk/opportunity has owner, impact, evidence, mitigation, and decision status.
4. Evidence distinguishes real users from internal/test traffic.

### Phase 468: Reliability Data Quality And Release Scale Review

**Goal**: Review reliability, data quality, dashboards, alerts, migrations, rollback, release cadence, and operational ownership.
**Depends on**: Phase 467.
**Requirements**: V8STRAT-02
**Success Criteria**:

1. Reliability, data quality, dashboards, alerts, migrations, rollback, release cadence, incident response, and operational ownership are reviewed.
2. Release evidence links code SHA, deploy/build IDs, request IDs where applicable, timestamp, and owner.
3. Data drift, support overload, provider degradation, and release regressions have owner/action rows.
4. Scale blockers are separated from strategic opportunities.

### Phase 469: Market Expansion Enterprise And Localization Options

**Goal**: Evaluate market/language expansion, enterprise readiness, school partnerships, localization, and support implications.
**Depends on**: Phase 468.
**Requirements**: V8STRAT-03
**Success Criteria**:

1. Market/language expansion, enterprise readiness, school partnerships, localization, support staffing, pricing, billing, and compliance implications are evaluated.
2. Unsupported markets/languages remain blocked unless approved.
3. Enterprise/school options have scope, owner, evidence, support impact, and go/no-go criteria.
4. Localization does not hide incomplete product behavior.

### Phase 470: AI Autonomy Growth And Governance Options

**Goal**: Evaluate AI autonomy, paid marketing scale, growth loops, compliance, privacy, and governance options.
**Depends on**: Phase 469.
**Requirements**: V8STRAT-04
**Success Criteria**:

1. AI autonomy, paid marketing scale, growth loops, compliance, privacy, audit, and governance options are evaluated.
2. AI autonomy remains blocked without quality, safety, teacher oversight, and owner approval evidence.
3. Paid marketing scale remains blocked without support, revenue, retention, learning quality, and incident readiness.
4. Governance options are tied to live risks rather than speculative compliance work.

### Phase 471: Strategic Scale Decision Gate

**Goal**: Decide scale growth, hold, rollback, remediation, market expansion, enterprise readiness, or v9 focus.
**Depends on**: Phase 470.
**Requirements**: VERIFY-93
**Success Criteria**:

1. Decision is scale growth, hold, rollback, remediation, market expansion, enterprise readiness, or v9 focus.
2. Decision uses product, revenue, learning, support, teacher, mobile, provider, incident, reliability, acquisition, and strategic evidence.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. Any v9 recommendation is based on live risks and opportunities.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V8STRAT-01 | Phase 467 | Completed |
| V8STRAT-02 | Phase 468 | Completed |
| V8STRAT-03 | Phase 469 | Completed |
| V8STRAT-04 | Phase 470 | Completed |
| VERIFY-93 | Phase 471 | Completed |
