# AI 生成搬出 29 秒请求生命周期有哪些可行落点（#18 研究）

Labels: wayfinder:research
Type: research
Mode: AFK
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: [#18](https://github.com/stoasystem/stoa-backend/issues/18)

## Question

只找事实，不做决定。产出供票据 08 决策。

1. 平台上限：API Gateway HTTP API 集成超时上限是多少、能否申请提高；Lambda 函数超时上限；Lambda 响应流式传输（response streaming）目前只能通过 Function URL 还是也能经 API Gateway；CloudFront 前置 Function URL 的常见做法。引用 AWS 官方文档。
2. infra 现状（远端 stoasystem/stoa-infra main，`stacks/api_stack.py`）：API Lambda 超时与内存；是否已有 SQS 触发的 worker Lambda、Function URL、EventBridge 定时任务；现有 Lambda 打包方式（`scripts/build_lambda_dist.py`）能否再装一个函数。
3. 后端现状：`routers/conversations.py` 的 message command（`ai_running` 状态、120 秒 lease、`_conversation_allowance_command_fields`、progress 轮询端点）已经做到哪一步；`jobs/teacher_escalation.py` 与 `jobs/account_deletion.py` 两个异步命令继续模式各自怎么声明、怎么被触发；`get_ai_answer` 的 Config（connect 5 秒、read 85 秒、单次尝试）与 allowance wrapper 无 Config 的差异。
4. 前端契约（`.scratch/ai-audit-20260924/remote/useStreamingChat.ts`，远端 830e1b7）：同步请求打开期间轮询什么端点、拿到什么字段、请求失败时是否换幂等键。
5. 模型：`settings.bedrock_model_id` 与 `bedrock_max_tokens` 的当前值；是否用 streaming API。不要编造延迟数字，没有实测就写"未测"。

产出：`docs/research/ai-runtime-budget-2026-09-24.md`，每条事实带来源链接或文件路径行号，末尾列出 08 可选的架构方向（不排序、不推荐）。

## Comments

2026-09-24：研究子代理已领取，在独立 worktree 的 `research/ai-runtime-budget` 分支上工作，产出 `docs/research/ai-runtime-budget-2026-09-24.md`。

## Answer

2026-09-24 由研究子代理解决。全文在分支 `research/ai-runtime-budget`（提交 6b2e3718）的 `docs/research/ai-runtime-budget-2026-09-24.md`，未推送；读取方式 `git show research/ai-runtime-budget:docs/research/ai-runtime-budget-2026-09-24.md`。每条事实带 AWS 文档链接或 `path:line`。

要点：
1. infra 用的是 API Gateway HTTP API v2，集成超时上限 30 秒且**不可提高**；只有 REST API v1 能申请超过 29 秒。
2. Lambda 最长 900 秒。响应流式传输只支持 Function URL、`InvokeWithResponseStream` 与 REST API v1；HTTP API v2 与 ALB 不支持。Python 托管运行时不原生支持流式，需 Lambda Web Adapter 或自定义运行时；Function URL 没有 JWT 授权器。
3. infra 现状：`stoa-api` 1024 MB / 29 秒，无 Function URL，无 SQS 事件源映射，无 EventBridge Rule；三个 EventBridge Scheduler 任务共用同一个 zip：周报 `cron(0 6 ? * MON *)` Europe/Zurich（函数超时 15 分钟）、派单对账 `rate(5 minutes)`（超时 5 分钟）、账号删除 `rate(5 minutes)`、input `limit=25`（超时 10 分钟）。`stoa-teacher-escalation.fifo` 队列存在但**没有消费者 Lambda**。
4. 再加一个函数不需要改打包：同一 zip 含全部模块；要加的是 infra 里一个 `lambda_.Function`、`deploy-production.yml` 的函数名循环、可选的 `EXPECTED_HANDLERS`。
5. 后端：`stream_message` 同步跑完整条命令后，把成品答案切成 100 字符的 SSE 块回放；90 秒 deadline 在 lease 与附件提取之后才起算；lease 120 秒；3 次 attempt 后 `terminal_failed`；异常路径不改命令状态，`ai_running` 靠 lease 到期解锁。
6. allowance wrapper 建 boto3 client 时没有 `Config`（直调路径是 connect 5 秒、read ≤85 秒、单次尝试）；count_tokens 与预留不检查 deadline；流式 deadline 第一次检查在拿到首个事件之后。
7. 前端每 1 秒轮询 `GET /conversations/{id}/generation`，只读 `steps` 与 `updatedAt`；请求失败即标记失败并停止轮询；**重试生成新的 idempotencyKey**，后端视为新命令。没有端点暴露命令终态。
8. 模型 `eu.anthropic.claude-sonnet-4-6`，`max_tokens` 2048；对 Bedrock 用流式 API，对客户端不是。所有延迟数字未测。
9. 三个可选方向（A 留在请求内压预算；B 生成搬到独立 worker、请求返回命令状态、前端轮询终态；C Function URL 流式）各自涉及的仓库与平台约束见全文第 6 节。

2026-09-24 修正：原摘要把函数超时写成了调度频率，已按研究正文 §2.3 改正。
