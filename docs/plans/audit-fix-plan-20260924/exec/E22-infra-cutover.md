# E22 infra 给 API 环境变量、启用 sweep、补 IAM

Status: released
Blocked by: E20 已部署
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

API 知道 worker 的名字，sweep 每 5 分钟运行，worker 的 IAM 覆盖后端实际调用的 Bedrock 方法。

## Change

stoa-infra `stacks/api_stack.py`：API 环境变量 `CONVERSATION_GENERATION_FUNCTION_NAME` = worker production alias ARN（这会发布新 API 版本并移别名，接受）；`ConversationGenerationSchedule.state` → `ENABLED`；按 E20 实际使用的方法补 `bedrock:InvokeModel`；按 stoa-docs 卡 111 A-09 的形状给 worker 加错误告警与 `stoa-conversation-generation-dlq` 的 `ApproximateNumberOfMessagesVisible >= 1` 告警，动作接 `stoa-alerts`；把三处写死的 `eu.anthropic.claude-sonnet-4-6` 收成 `api_stack.py` 一个常量（拍板 Q4 无论选哪条都只改一处）；拓扑测试同步。

## Acceptance

`cdk synth` 通过；拓扑测试断言变量存在、schedule ENABLED、IAM 动作集合；部署后 sweep 首轮日志无 handler 缺失错误（E20 已上线）。

## Poison

不适用（基础设施）。

## Commit

stoa-infra 单独一个提交，在 E20 部署之后、E21 之前推送；回退：先改回 DISABLED 与去掉变量。

2026-09-25 对接：卡 098 D-13 也改 `api_stack.py`（删 teacher_queue），排在本票据之后或由同一人串行做；卡 111 的 DLQ 计数由 4 改 5。

2026-09-25 补记（来自 R02 的发现）：infra 流水线每次 `cdk deploy` 都会检出后端 main 重新构建并发布到全部函数。因此 E22 部署时后端 main 上是什么就发布什么：E21 若已在 main，切换会随 infra 部署一起发生；E21 若不在，E22 只是加变量与启用 sweep。回退同理：改回 infra 变量也会重新发布后端 main。上线时按这个理解排序：E22 先（此时 main 无 E21），E21 后。

## Implementation (2026-09-25)

stoa-infra 本地提交 813c538，**未推送**。API 变量（worker production alias）、sweep ENABLED、worker Bedrock 动作集合固定为流式 + CountTokens（worker 恒流式，不补 InvokeModel）、worker 错误告警与 DLQ 告警（≥1，接 stoa-alerts）、模型 id 收成常量 `BEDROCK_MODEL_ID`。`cdk synth` 通过（后端 dist 于 1318ffd7 重建）；infra tests 37 passed；后端读 infra 的发布测试 221 passed。`cdk diff` 未跑（SSO 令牌过期）。

审查发现：启用 sweep 会处理 E19 上线以来所有卡住的命令，不论多久（答复并扣额）。已在后端加年龄上限（86cbf0af，本地未推送）：sweep 只处理 20 分钟内提出的命令，更早的计为 `too_old` 原样保留，学生同键重试仍可在请求内续上。**推送顺序：后端 86cbf0af 先上线，再推 infra 813c538**（此时后端 main 无 E21）。
告警从 StoaApiStack 导入 worker 与 DLQ 名称（跨栈导出），日后改名/删除须先删告警。

## Released (2026-09-25)

15:21Z 推送后端 86cbf0af（sweep 20 分钟年龄上限），run 36153616729 success，CI 3874 passed。15:29Z 推送 infra 813c538，run 36154534049 success：构建自后端 86cbf0af（provenance 校验通过）；StoaApiStack 更新（API 函数含新变量、ConversationGenerationSchedule 更新为 ENABLED、五个函数与别名重发）；StoaMonitoringStack 新建 ConversationGenerationErrorAlarm、ConversationGenerationDlqAlarm。
**只读核对（2026-09-25 15:38Z，SSO 重新登录后）**：schedule `stoa-conversation-generation` ENABLED、rate(5 minutes)、目标 worker production alias；五个函数 production 别名同一 CodeSha256 `nDb0pRDk…`（stoa-api v121、weekly-report v121、dispatch-reconciler v71、account-deletion v32、conversation-generation v6）；API v121 的 `CONVERSATION_GENERATION_FUNCTION_NAME` = worker production alias ARN；两条告警 OK、动作 `stoa-alerts`；DLQ 0 条。首轮 sweep 15:34:35Z：handler 正常导入、293 ms、无 warning/错误。表内等待中的命令（message_committed / ai_running）为 0（扫描 6802 条），年龄上限此次未拦下任何命令。

## Verification（地图会话，2026-09-25）

infra 813c538 已部署。与修订后票据对照：API 环境变量 = worker production alias ARN；schedule ENABLED、rate(5 minutes)；Bedrock 权限钉为 InvokeModelWithResponseStream 加 CountTokens（worker 恒流式，不授 InvokeModel，与 E20 一致）；按卡 111 形状加 worker 错误告警与 DLQ 告警，动作 `stoa-alerts`（该 topic 仍零订阅，卡 111 未做）；模型 id 收成 `BEDROCK_MODEL_ID` 常量。线上只读核对（2026-09-25，SSO）：API v121 变量正确、worker alias v6、schedule ENABLED、E22 部署后 sweep 每 5 分钟运行约 90 毫秒无错误、DLQ 0。前置提交 86cbf0af（sweep 只处理 20 分钟内的命令）已上线，避免启用当天补答所有历史卡住的问题；边界：20 分钟与「3 次尝试 × 300 秒 lease 加 5 分钟周期」贴着，第三次尝试的 lease 到期可能落在窗口外而被记为 too_old，只剩学生同键重试一条路，记入地图。
