# Plans and maps

Working records kept in the repository by stoasystem/stoa-backend#45, copied from
the untracked `.scratch/` where they were written.

- `audit-fix-plan-20260924/`: the map that took the 2026-09-21 and 2026-09-24
  audits to production, with every ticket's execution record and its poisoning
  readings (`exec/`).
- `stoa-codex-testing/`: the earlier testing plan and its 2026-09-05 production
  smoke run.

Only the Markdown was taken. The raw harness output (logs, pytest XML, JSON, probe
scripts) stays local and untracked; the parts that repository tests replaced were
removed. The production test accounts' addresses are replaced by role placeholders
such as `<student test account>`. The findings themselves are public as issues
#2-#22; the audit reports are in `docs/audit/`.
