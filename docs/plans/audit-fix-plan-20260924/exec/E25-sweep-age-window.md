# E25 sweep 年龄窗口以最近一次尝试计

Status: released
Blocked by: 
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

第三次尝试的 lease 到期不再因 20 分钟（自 `created_at`）窗口而被记为 too_old。

## Change

`jobs/conversation_generation.py::_recent`：对 `ai_running` 命令以 `claimedAt`（最近一次尝试）计，对 `message_committed` 以 `message_committed_at` 计，窗口保持 20 分钟；`created_at` 仅作回退。测试：第三次尝试在第 19 分钟领取、lease 于第 24 分钟到期 → 第 25 分钟的 sweep 仍接手。

## Acceptance / Poison

新用例通过；改回按 `created_at` → 红。既有 worker 测试全绿。

## Commit

后端单独一个提交。

## Implementation (2026-09-25)

本地提交 c93dce94，**未推送**。`_recent`：`ai_running` 按 `claimedAt`、其余按 `message_committed_at`（重发时 reopen 会重写它），`created_at` 仅回退。新用例两条（第 19 分钟领取的第二次尝试、40 分钟前提问但 2 分钟前重发）；改回按 `created_at` → 2 条红。既有 5 条用例把 `message_committed_at` 写死为 2026-09-24，E25 之后会被算作 too_old，改为「2 分钟前」（worker 测试 3 条、cutover 测试 2 条）。偏离：票据写的「第三次尝试的 lease 到期」按字面（attempt=3 过期）sweep 接手后标 `terminal_failed`（无 failure_category），不是 needs_reconciliation；测试用的是 attempt=2 过期、sweep 领第三次。

## Verification（地图会话，2026-09-25）

提交 c93dce94，未推送。`_recent`：`ai_running` 以 `claimedAt` 计，`message_committed` 以 `message_committed_at` 计，`created_at` 只作回退；窗口仍 20 分钟。新测试 2 条（第三次尝试晚领取仍被接手；重发的命令按重发时间计）通过。投毒：改回只按 `created_at` → 2 failed。

## Released (2026-09-25)

随 9956aa9b 推送，run 36186080005 success。
