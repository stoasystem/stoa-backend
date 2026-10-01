# E26 给「标 terminal」与超窗过期 lease 计数

Status: released
Blocked by: 
Decision: [票据 15](../issues/15-terminal-failed-reservation.md) 第 5 条
GitHub: #18

## Delivers

线上能读到两类预留卡住的发生频率：命令被标 `terminal_failed` 的次数，以及 sweep 每轮看到的、lease 已过期且超出年龄窗口的 `ai_running` 命令数。

## Change

`routers/conversations.py`：`mark_message_command_terminal` 成功（disposition TERMINAL）时发私有事件 `conversation_ai_attempts_exhausted`（WARNING，correlation_id 为 command_id），并在 `private_telemetry` 登记。`jobs/conversation_generation.py`：`SweepSummary` 新增 `stale_leases`（`too_old` 中 `ai_running` 的那部分），每轮结束记一行 `conversation_generation_sweep_summary` 带全部计数。只动后端，不加告警。

## Acceptance

第三次尝试 lease 到期后被 sweep 接手 → 命令 `terminal_failed` 且发一次事件；重复投递不再发。过期 lease 在窗口外 → `stale_leases == 1`、`too_old` 同时计入；窗口内或未过期不计。汇总日志一行、含各计数。

## Poison

去掉事件 → 事件那条红；`stale_leases` 改为统计全部 `too_old` → 「超窗未提交命令不计」那条红。

## Commit

后端单独一个提交，先于 E27 上线。

## Released (2026-09-25)

7372f58e，run 36188572800 success。事件 `conversation_ai_attempts_exhausted` 只由真正把命令改成 `terminal_failed` 的那次条件写发出（结果带 `previous_status="ai_running"`），学生同键重试再走到同一终态不再发。sweep 每轮 INFO 一行 `conversation_generation_sweep_summary`，含 `stale_leases`。新用例 2 条；投毒：去掉事件 → 1 红；`stale_leases` 改为统计全部 `too_old` → 1 红。全量 3902 passed。

读数（Logs Insights，worker 日志组）：
- `filter @message like /event_category=conversation_ai_attempts_exhausted/ | stats count() by bin(1d)`
- `filter @message like /conversation_generation_sweep_summary/ | parse @message "stale_leases=* missing" as stale | stats max(stale) by bin(1h)`

## Verification（地图会话，2026-09-25）

7372f58e 已上线。事件 `conversation_ai_attempts_exhausted` 只由把命令改成 `terminal_failed` 的那次条件写发出（`previous_status="ai_running"`），WARNING 级；`stale_leases` 单列超窗过期 lease。新用例 2 条通过；投毒去掉事件 → 1 failed。

**线上缺口**：sweep 的汇总行 `conversation_generation_sweep_summary` 用 `logger.info` 写，仓库里没有任何日志级别配置，Lambda Python 运行时（Text 格式）根 logger 默认只放行 WARNING 及以上。核对：E26 上线后 worker 至少 10 次调用，日志组里除 START/END/REPORT 外零行应用日志；API 日志组近 6 小时也没有一条 `[INFO]`。也就是说票据里给的两条 Logs Insights 查询中，`stale_leases` 那条永远查不到东西；`attempts_exhausted` 是 WARNING，能查到。E16 的 `account_deletion_scan_cycle_completed` 同样是 INFO，同样不可见。修法见 E29。
