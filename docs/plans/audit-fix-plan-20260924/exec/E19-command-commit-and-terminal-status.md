# E19 对话命令拆为提交与生成两段，`/generation` 暴露终态

Status: released
Blocked by: 
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

学生看到的行为不变（答案仍在请求内生成并以 SSE 回放），但命令已有 `message_committed` 中间态、请求上下文随命令持久化、`GET /conversations/{id}/generation` 返回绑定 command/attempt 的终态字段。前端 E13 据此可以先行开发。

## Change

`routers/conversations.py`：`_execute_message_command` 拆为 `commit_message_command`（写学生消息、预留、命令到 `message_committed`，持久化已解析的 locale、subject、grade、附件提取结果）与 `generate_for_command(command)`（现有生成、落库、终态改写逻辑，含 E2 的失败契约）；请求内仍顺序调用两者。`/generation` 返回 `status`（`message_committed`/`ai_running`/`completed`/`failed`）、`attempt`、`assistantMessageId` 或 `failureCategory`、`steps`、`updatedAt`。失败路径显式把命令改写为 `failed` 并带类别（不再靠 lease 到期）。旧形状命令可读。

## Acceptance

成功：`/generation` 终态 `completed`，助手消息一条，SSE 回放不变；截断、超时、provider 错误 → `failed` 加类别，预留按 E2/E10 规则处理；命令行含 locale/subject/grade/附件结果且 `generate_for_command` 不再读请求头；旧形状命令查询不报错；同一幂等键重试复用原命令；既有 conversations 套件全绿。并入 stoa-docs 卡 071 C-07 的后端两组：组 A 学生 `preferred_locale` 为 de/en/fr/it 时传给 `ai_service` 的 `language` 逐一对上（来自命令而非请求头；投毒把 language 写死成 de → 至少 3 条红）；组 B `**{hint_label}:**` 随 locale 变（de=Hinweis / en=Hint / fr=Indice / it=Indizio；投毒写死 Hinweis → 至少 3 条红）。

## Poison

让 `generate_for_command` 读请求头 → 上下文那条红；去掉失败改写 → `failed` 那条红。

## Commit

单独一个提交，只动后端，随时可 revert；不引用 worker。

## Released (2026-09-25)

提交 3fd92dc7，07:54Z 推送（30a2d7bd..3fd92dc7），"Deploy Backend to Production" run 36110096659 success，CI 3852 passed；stoa-api production v118、worker v3（CodeSha256 `/pj0Vrg4…`）。上线后 15 分钟无调用、无错误日志；尚无真实流量读数。

与票据的偏离（待用户认可）：附件提取文本不落命令行（最多 20 万字符可超 DynamoDB 400 KB 条目上限），生成时从不可变、sha 校验过的附件记录重新提取；只有未付费失败可同键重试（最多 3 次），模型已作答的失败 `retryable=false`——E13 需按 `retryable` 分支；响应多 `retryable`、`commandId` 两字段；未知幂等键复用 409 `message_command_not_found`。

留给 E20：worker 需一个从命令行重建 `CommittedMessage` 的加载函数；答案已接受后记账失败、或付费失败的额度归还失败，命令仍停在 `ai_running` 靠 lease 恢复；「结果未知」尚未与「尚未调用」区分。

2026-09-25 对接：卡 071 的后端部分并入本票据（卡只留前端）；卡 043 D-15 的第一层确定性检测应放在 `commit_message_command`（请求侧），Guardrail id 挂在 `generate_for_command`（worker 侧），043 依赖本票据先上。

## Verification（地图会话，2026-09-25）

提交 3fd92dc7，已上线（v118）。与票据对照：命令拆为 `commit_message_command` / `generate_for_command`，`generation_context`（language、subject、grade、weak topics）随命令持久化，生成不读请求头；`/generation?idempotencyKey=` 返回 status/attempt/assistantMessageId 或 failureCategory 加 retryable；失败路径显式写 `failed`；旧形状命令可读可续。新测试 17 条通过；投毒：把 `fail_message_command` 改成空操作 → 7 failed。`CONVERSATION_ACTIVE_COMMAND_STATES` 新增 `failed` 的唯一消费方是销户分支，它对任何状态的命令都直接抹掉私有字段（`cancel_stale_message_command` 无状态条件），不会卡住删除。

**与票据的三处偏离，待用户认可**（实施方已在 Released 段列出）：附件提取文本不落命令行（400 KB 上限），生成时从 sha 校验过的附件记录重提；只有未付费失败可同键重试（模型已作答的失败 `retryable=false`）；响应多 `retryable`、`commandId`。三条我都认为成立：第一条是硬限制，第二条与票据 11/E14「已知结果不重调」一致，第三条是 E13 需要的。

2026-09-25 用户认可三处偏离：附件文本不落命令行而是重提；只有未付费失败可同键重试；响应多 `retryable`、`commandId`。票据据此为准。
