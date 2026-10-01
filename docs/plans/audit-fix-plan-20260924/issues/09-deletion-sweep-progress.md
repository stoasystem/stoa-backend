# 定时删除扫描应如何在多次调用之间保留进度（#7）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: [#7](https://github.com/stoasystem/stoa-backend/issues/7)

## Question

`jobs/account_deletion.py::run_pending_deletions` 每次从 `cursor=None` 起扫，100 页上限，预算耗尽只把 `unfinished` 计入 retryable，不返回也不持久化游标。2,600 条无关行后的删除命令三轮都到不了。

要决定：
1. 机制：(a) 把游标持久化到一行控制记录，下轮从上次位置续扫，扫到底再归零；(b) 给待处理命令建可查询的稀疏索引或独立分区键，Query 代替 Scan；(c) 请求侧失败时直接把 command_id 投到队列，定时任务只兜底。各自的一致性与成本。
2. 完整一轮的定义：多久必须把整表扫完一遍；扫描期间新写入的命令如何保证被发现。
3. 覆盖：超出单次预算的命令最终被发现、零匹配页、重试、完整重扫一轮；现有 `test_phase473_account_deletion.py` 的用例保持。

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

持久化游标：控制行 `PK=JOB#account_deletion / SK=SCAN_CURSOR`，字段 `cursor`、`version`（单调递增）、`cycle_started_at`。条件写绑定 `version`，表尾归零同样递增，迟到写入因 version 落后被拒；本批命令逐项 claim 并尝试（或持久移交）之后才推进游标。「完整周期」指多次调度累计扫到表尾，不是单次运行；强一致 Scan 也不是表快照，周期内新写入的命令由下一周期或请求侧 `continue_deletion_command` 覆盖。不建 GSI（仓库写明 GSI 不建立删除完整性），不加队列。
触发源事实（远端 stoa-infra c0d79df9，`api_stack.py:404-428`）：EventBridge Scheduler `rate(5 minutes)`、input `limit=25`、重试 maxAge 3600 秒 / 3 次、DLQ；本地 infra 副本停在 2026-09-19，无此声明。单次运行最多 100 页 × 25 行 = 2,500 行评估量，一天最多约 720,000 行；实测周期等实施时按表大小算。

2026-09-24 实施（E7）记录周期估算：每轮 ≤2,500 行评估量、5 分钟一轮，理想吞吐下完整周期 ≈ ⌈表行数 ÷ 2,500⌉ × 5 分钟（例：10 万行 ≈ 200 分钟，100 万行 ≈ 33 小时）。这是理想吞吐估算，不是完成上限：匹配到的命令会缩小后续分页的 `Limit`，命令失败会让游标原地保持到下一轮重试，调度重试与分页字节上限也会拉长周期。本仓库无表行数读数；实测周期看表尾复位 CAS 成功后的结构化日志 `account_deletion_scan_cycle_completed`（周期版本、完成时间、耗时），不另存持久字段。
验收：2,600 条无关行后的命令第二轮被发现；零匹配页；扫完归零后下一轮从头；归零后迟到写入被拒；扫描后中断、重启恢复从存的游标继续；并发两轮条件写只有一个成功；`test_phase473_account_deletion.py` 全绿。实施票据 [E7](../exec/E07-deletion-cursor.md)。
