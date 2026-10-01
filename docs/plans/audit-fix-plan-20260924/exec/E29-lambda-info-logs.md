# E29 让 Lambda 里的 INFO 日志真的写出来

Status: released
Blocked by: 
Decision: [票据 15](../issues/15-terminal-failed-reservation.md) 第 5 条（可观测性）
GitHub: #18

## Delivers

E26 的 sweep 汇总行、E16 的删除周期完成行、API 与各 job 的既有 INFO 日志在 CloudWatch 可见；票据 E26 里的两条 Logs Insights 查询有结果。

## Change

仓库无任何日志级别配置，Lambda Python 运行时（Text 格式）根 logger 默认 WARNING。二选一：(a) 后端在四个 handler 入口（`main.py`、`jobs/weekly_reports.py`、`jobs/account_deletion.py`、`jobs/conversation_generation.py`、`jobs/dispatch_reconciler.py`）处 `logging.getLogger("stoa").setLevel(logging.INFO)`；(b) infra 把五个函数的 `LoggingConfig` 改为 JSON 格式并设 `ApplicationLogLevel=INFO`（会发布新版本并移别名）。推荐 (a)：只动后端、一次部署、不改日志格式。顺带确认 `emit_private_event` 默认 INFO 的事件哪些依赖这条（它们此前同样不可见）。

## Acceptance

测试：用 `caplog` 断言 handler 导入后 `stoa` logger 有效级别为 INFO；线上：部署后下一轮 sweep 的 `conversation_generation_sweep_summary` 出现在 worker 日志组，API 日志组出现 `[INFO]` 行。

## Poison

去掉 setLevel → 级别断言那条红。

## Commit

后端单独一个提交。

## Implementation (2026-09-25)

本地提交 5714aebf，**未推送**。按 (a)，但不在五个 handler 各写一行：`src/stoa/__init__.py`（原为空）里 `logging.getLogger("stoa").setLevel(logging.INFO)`，每个部署的 handler 都先导入这个包，一处覆盖全部。只抬 `stoa`，SDK 的 logger 不动。
测试 `tests/test_lambda_info_logs.py`：五个部署 handler 各在新进程里导入（根 logger 按运行时设为 WARNING），断言本模块 INFO 行输出、`botocore` 的 INFO 行不输出。去掉 setLevel → 5 条全红。全量 3918 passed。
随之可见的 INFO：`logger.info` 共 5 处（sweep 汇总、删除周期、dispatch_reconciler、report_service）与默认 INFO 的私有事件 `ai_request_started`、`ai_response_received`（每次 AI 调用 2–3 行，封闭类别、无内容）。量小。
线上验收（部署后下一轮 sweep 出汇总行、API 日志组出 `[INFO]`）本机无 AWS 凭据，需在控制台或有凭据处核对。

## Released (2026-09-26)

5714aebf，run 36195635146 success。线上验收（worker 日志组出现 `conversation_generation_sweep_summary`、API 日志组出现 `[INFO]`）待有凭据处核对。

## Verification（地图会话，2026-09-26）

5714aebf 已上线（run 36195635146，api v128、worker v13、deletion v39 同一 CodeSha256，22:20Z）。实现比票据更集中：`src/stoa/__init__.py` 把 `stoa` logger 设为 INFO，五个 handler 都先导入该包；SDK 的 logger 不动。测试在新进程里按运行时方式把根 logger 设为 WARNING 后导入各 handler，断言本模块 INFO 行输出、`botocore` INFO 不输出；5 条通过，投毒改回 WARNING → 5 failed；ruff 过。

**线上验收（SSO 只读，2026-09-26）**：worker 日志组自 22:20Z 起每轮 sweep 都有 `conversation_generation_sweep_summary`（`candidates=0 … stale_leases=0 reconciled=0`）；账号删除日志组出现 `account_deletion_scan_cycle_completed version=330`；API 日志组 147 次调用 0 条 `[INFO]`，符合预期（API 侧 INFO 只有模型调用事件，期间无人发消息）；三条告警 OK，无错误。票据 E26 的两条 Logs Insights 查询现在都有结果。
