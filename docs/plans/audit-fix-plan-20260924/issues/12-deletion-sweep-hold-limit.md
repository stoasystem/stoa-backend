# 失败命令按住删除扫描游标应有怎样的上限（E7 余量）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by:
GitHub: [#7](https://github.com/stoasystem/stoa-backend/issues/7)

## Question

05727d3a 让 claim 或 continue 失败的命令把游标按住，下一轮重试同一片。这解决了短暂故障，但一条持续失败的命令会让整表扫描停在它那一片，后面的命令无限期不被发现。按住要不要上限，上限之后怎么办？

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

**上限 N = 3 轮**，计数字段 `held_runs` 与 `cursor`、`version` 同在一条控制行里条件写：
1. 保持游标的那一轮也递增 `version`，`held_runs += 1`；同一 version 上的并发失败只计一次（条件写落败的那一轮不计）。推进或归零时 `held_runs` 清零。
2. 定义：第 3 次已记录的失败轮结束后，**下一轮**仍先尝试本批命令，若再失败即推进游标越过这一片，并以 `account_deletion_scan_skipped` 警告记下被越过命令的 `command_id`。扫描异常、无效分页、硬中断不套用这条跳过规则：它们不写游标、不计 `held_runs`。
3. 被越过的命令保留原有 `pending/running` 状态、lease 与分支检查点，不做任何改写；恢复靠持久命令、请求侧 continuation 与后续周期扫描。警告只用于定位。
4. 开头就被按住时也保留首次 `cycle_started_at`。N=3 不等于保证 15 分钟内恢复；被越过的命令可能要等完整周期。

实施票据 [E16](../exec/E16-deletion-hold-limit.md)，其中顺带修 05727d3a 的完成日志时间：`completed_at` 与 `duration_seconds` 目前用函数入口的 `now`，应在表尾归零的条件写成功后重新取时间。
