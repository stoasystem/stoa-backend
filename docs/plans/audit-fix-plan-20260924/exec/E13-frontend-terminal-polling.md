# E13 前端轮询命令终态并复用幂等键重试

Status: released
Blocked by: E19（终态字段已上线）
Decision: [票据 08](../issues/08-runtime-budget-architecture.md)
GitHub: #18

## Delivers

学生发送后看到进度，请求结束不再等同步 SSE；失败与重试来自命令终态；刷新页面能恢复到同一条命令；重试不产生第二条命令。

## Change

stoa-frontend `src/hooks/chat/useStreamingChat.ts`：发送后保存后端返回的命令标识与幂等键；轮询 `/generation` 直到 `completed`/`failed`，渲染 `assistantMessageId` 对应消息或 `failureCategory`；重试沿用原幂等键；页面恢复时按持久化的命令标识继续轮询；轮询设置上限与退避；过渡期同时接受旧的 SSE 终态与新的命令状态。

## Acceptance

Vitest（含并入的 stoa-docs 卡 103 A-24）：轮询拿到的 `steps` 渐进渲染且文本长度单调增加；终态前 `StreamingCursor` 可见、终态后消失；缺终态或 `failed` 时有可见失败态；投毒「全部收完才渲染」→ 单调那条红，「终态后不隐藏光标」→ 光标那条红。原有：成功终态渲染一条助手消息；`failed` 渲染可重试失败；重试请求体幂等键与首次相同；刷新后恢复轮询；轮询在终态后停止；旧 SSE 路径对照仍通过。

## Poison

让重试生成新幂等键 → 幂等那条红。

## Commit

stoa-frontend 单独一个提交，被 E19 阻塞，须在 E21 切换之前上线（过渡期同时接受 SSE 终态与命令状态），回退时最先退。基于 origin/main 开分支：本地 stoa-frontend 检出停在 `test-script-node-webstorage` 分支，不是 main。

2026-09-25 对接：stoa-docs 卡 103 A-24（伪流式逐步渲染单测）并入本票据，因为 E21 之后 SSE 分块不再存在，钉住的对象改为轮询到的 `steps`。与卡 112 D-08 同页：两个轮询的周期与停止条件在同一处声明。

## Implementation (2026-09-25)

stoa-frontend 分支 `e13-generation-terminal-polling`（worktree `../stoa-frontend-e13`，基于 origin/main 8208d9b），提交 3aae4b2，**未推送、未合入 main**。门禁全绿：lint、typecheck、API 契约、翻译棘轮 175 不变、Vitest 253、release 34。投毒：重试换新键 → 同键两条转红；去掉 attempt 归属守卫 → 迟到请求那条转红。

决定：
- 重试沿用原键仅当命令 `retryable`、从未存储（409 not found）或等待超时；`retryable:false`（已付费不可用）换新键——依赖 E19 的 retryable 口径，待用户认可。
- 轮询与发送请求并行（1,1,1,2,2,3 秒后每 5 秒，最长 240 秒）；请求结束前的 not found 视为尚未存储。
- 本地气泡使用后端 UUIDv5 派生的 student/assistant id，页面按 id 去重（失败的学生气泡优先本地副本以保留重试）。
- 待答消息存 sessionStorage，刷新后继续同一命令。
- 未读 `commandId` / `assistantMessageId`（完成后按原逻辑刷新会话）；`failureCategory` 未展示（沿用通用失败文案）。
- 停止只停止本地等待，服务器上的命令继续；答案落库后以同 id 替换 stopped 气泡。

上线：须在 E21 之前 push 到 stoa-frontend main（push 即部署）。

## Verification（地图会话，2026-09-25）

前端分支 `e13-generation-terminal-polling` 提交 3aae4b2，基于 origin/main 8208d9b，未合并。与票据（含并入的卡 103）对照：发送后同时读命令；stream 给出 `message_done` 即答案；202 或流提前结束交给命令；发送请求失败（如 504）不算失败，命令说了才算；命令未存在则可安全重发；重试按 `retryable` 分支复用原键或新键；待答消息存 sessionStorage 供刷新恢复；本地气泡用后端同款 UUIDv5 派生 id 去重；轮询在终态或时限停止。Vitest 253 passed（我本机需 `NODE_OPTIONS=--localstorage-file=…`，因 Node 26 的实验性 localStorage 全局遮住 jsdom；CI 是 Node 22，不受影响）；typecheck、lint 通过；api-contract 160 调用对 213 路由全部匹配。

**留意**：等待上限 240 秒小于 E20 的 300 秒 lease。240 秒后前端会"再次提供同键重试"，此时后端 lease 仍被持有，同键重发得到 409 `MESSAGE_IN_PROGRESS`，前端按"请求失败不算失败"继续轮询，直到 300 秒 lease 到期。行为正确但多一次无效往返；合并前建议把上限提到 ≥ 330 秒（lease 加余量），或在 E20 推送前决定。

## Released (2026-09-25)

等待上限 240 → 360 秒（e347fc7，lease 300 秒加一次读取）；11:39Z 快进推送 stoa-frontend main（8208d9b..e347fc7，含 3aae4b2），"Deploy Frontend to Production" run 36130597284 success，app.stoaedu.ch 200。

## Card 103 acceptance (2026-09-25)

ad40c74：真实 hook + 真实气泡的渲染测试（步骤渐进、文本长度单调增加、终态/无终态/停止/完成后光标消失、助手气泡上的失败与停止态）。由此发现并修复：失败与停止时 updater 懒读已被清空的 ref，助手气泡从未被标记，光标永不消失。投毒两条（全收完才渲染、updater 内懒读 ref）各转红。12:13Z 快进推送 stoa-frontend main（e347fc7..ad40c74），run 36137475229 success。

2026-09-25 地图会话补核：e347fc7 把等待上限提到 360 秒（lease 300 加一次读取），ad40c74 落实并入的卡 103 测试并顺带修了失败/停止时助手气泡光标不消失的旧缺陷；两次都已快进部署。
