# 审计 issue 修复决策地图

Labels: wayfinder:map
Status: closed（2026-09-26 收口；后继地图为 GitHub [#23 阶段二：上线后收口 + 任务卡批次 0/1](https://github.com/stoasystem/stoa-backend/issues/23)）

## Destination

为 2026-09-21 非支付审计与 2026-09-24 AI 行为审计留下的 7 条未修 GitHub issue（#3 余量、#6、#7、#18、#19、#20、#21）以及 stoa-docs 卡 022 记下的支付判据缺口（B-2），逐条定出修复规范：改哪一层、验收怎么判、投毒怎么验、哪些改动落在 infra 与前端仓。完成时每条都有一张已决议的票据，实施会话可以按票据逐条动手，不再需要产品或架构拍板。

## Notes

- 2026-09-24 用户决定：只做规划，不在本地图内执行修复（Q1 选 a）；#18 的 infra 与前端改动纳入决策范围；已关闭的 12 条 issue 以本地复测为准，不另建票据；地图与票据用本地 Markdown、中文；#19 的产品口径按 issue 正文写死，不设学科例外。
- 仓库事实：push 即部署、没有预发环境，回退靠单提交 revert。每条修复规范都要能落成"一张卡一个提交"。
- 现状核对（后端 `main` = 5a6ba852，复测报告见 [prior-issues/REPORT.md](../ai-audit-20260924/prior-issues/REPORT.md)）：#2 #4 #5 #8 #9 #11–#17 已关闭且离线复测不再复现；#10 已于 2026-09-24 关闭（修复 d63e952a）；#3 部分修复（重发路径已判当前关系，生成路径投递前仍只有学生围栏，见 stoa-docs 卡 022 B-1）；#6 #7 仍复现；#18–#21 未动。
- 已知产品口径：同学科超纲问题先用可理解的解释或类比回答，再视情况建议老师介入；"不给最终答案、只讲步骤"不变（#19）。
- 术语见 [CONTEXT.md](../../CONTEXT.md)。代码里这轮修复落成的唯一判据叫 `current_relationship`（当前关系），同时覆盖旧绑定行和新 link 行；CONTEXT.md 目前只有"家长绑定"。对齐工作放在票据 04。
- 使用技能：Wayfinder；HITL 票据用 grilling 与 domain-modeling；prototype 票据用 prototype；research 票据由子代理调用 research 技能，产出落在 `research/<name>` 分支。
- 票据文件在 `issues/`。`Status: open` 未领取、`claimed` 已领取、`resolved` 已完成；`Blocked by:` 列本地编号，全部 resolved 后才进入 frontier；按编号取第一个未领取项。编号即建议的处理顺序：先用户正在感受到的 AI 症状（#19 #21 #20），再家长隐私判据（#3 余量、B-2），再 #18 架构，再 #7 #6。理由：今天生产 0 条家长关系行，#3 的暴露暂时是理论上的；AI 症状是用户报告的现实。
- 对外动作（建 GitHub issue、关 issue、评论）一律先问再做；票据 06 专门承接 B-2 的建 issue。
- 2026-09-24：E1–E5 已实施（04fd9737、972cefe2、71a7adf4、3a005cc7、6760f124），地图会话按 Acceptance 与 Poison 核查通过，详见各票据 Verification；**尚未推送**，推送前需先合入远端 4 个新提交（演练无冲突）。
- 2026-09-24：E6 已完成（GitHub #22），E7 已实施（a72c7be3、05727d3a）并核查通过，详见票据 Verification；仍未推送。适配后的 #7 审计见证在 [evidence/](evidence/)。
- 2026-09-24：E8、E10、E14、E16、E17（后端）与 E12（infra 9858946）已实施并核查通过，详见各票据 Verification；全部未推送。两处待用户认可：E8 账本的批准措辞、E10 保留预留（偏离票据 08）。推送顺序已在 R01 修正为后端先、infra 次、E18 立即跟上。
- 2026-09-24：R01 第 1 步完成（合并提交 653821db，本机复核 3829 passed 加 1 条有意留红），E9（0e419007）补核通过；本地 main 领先 15、待推送。第 2 步 push 即部署，等用户执行或授权。
- 2026-09-24 18:55Z：E1–E10、E14、E16、E17 已上线（653821db，api v115、deletion v26）。R01 剩冒烟、GitHub 收尾（六条评论草稿在 R01）、回填。
- 第二阶段（#18 落地与收尾）票据：R02 推 infra 与 E18；E11 拆为 E19（命令拆两段、终态字段）→ E20（worker handler、三态）→ E13（前端）→ E22（infra 切换）→ E21（路由切异步）；D01 在 stoa-docs 记任务卡。仍待用户认可：E10 保留预留（票据 08 评论）、E8 账本措辞。
- 2026-09-25：与 stoa-docs 卡 028–113 对接完成，见下方专节；新增 E23，E13/E19/E22/D01 按对接结果修订。
- 2026-09-25：E18、E19 已上线（api v118、worker v3）；E20 本地已核查（verified-unpushed）；E13 在前端分支已核查（verified-unmerged）。E19 三处偏离、E10 保留预留、E8 措辞仍待用户认可。R01 第 3–5 步（冒烟、关 issue、回填）未做。
- 2026-09-25 晚：E20、E22（infra 813c538，sweep 已启用）、E13 及两个前端跟进、86cbf0af（sweep 20 分钟年龄上限）均已上线并核查；六条 issue 已关；E21、E23（后端）与 D01（stoa-docs 卡 114）已核查、未推送。审计延迟契约 harness 已被 E19/E20 的内部重构淘汰（它 monkeypatch 的表替身写不了调用标记，E20 按设计拒绝调模型），以仓库内 `tests/test_async_generation_cutover.py` 与 worker 测试为准。
- 2026-09-25 19:4xZ：用户认可全部待拍板项（票据 14 选项 2、E19 三处偏离、E10 保留预留、E8 措辞）；E21+E23 已推送（8433b39e）、D01 已推送（stoa-docs 9829b1e）、#22 已关。新增 E24（结果未知预留结算加告警）、E25（sweep 年龄窗口按最近尝试计）。
- 2026-09-25 晚：E24（后端 87e4cf54 加 infra 2cec071）、E25（c93dce94）已核查、未推送；E24 的一条投毒声明不成立（性质由账本状态机兜住），建议推送前加两条断言。推送顺序：后端先、infra 后（infra 部署会重新发布后端 main）。
- 2026-09-25 晚：E24（后端 87e4cf54、infra 2cec071）、E25（c93dce94）连同补断言 9956aa9b 已上线（后端 run 36186080005、infra run 36186922615）。E24 核查发现 `terminal_failed` 的预留仍无出路，新立决策票据 15。
- 2026-09-25 晚：票据 15 按推荐决议。E26（计数，7372f58e，run 36188572800）已上线；E27（结算，47a603c2，run 36189913895）已上线，首轮起结算历史积压。票据 16 已决议（算缺陷、只修今后）→ E28 已推送（1f2c9097）。E29（INFO 日志）已核查、未推送。R01 冒烟仍暂缓。
- 2026-09-25 深夜：E24–E27 已上线（api v126），E28 已核查未推送；发现 Lambda 默认不写 INFO 日志，E26 的汇总行与 E16 的周期完成行在线上不可见 → 新增 E29。
- 2026-09-26：E28（1f2c9097）、E29（5714aebf）已上线。R01 冒烟完成（生产、用户登录）：两题均在本学科内给出解释、德语对德语；账号年级为空，年级边界未测；对话路由不保留 `suggest_teacher`，该值不可观测。E29 的线上日志验收待有 AWS 凭据处核对。
- 2026-09-26：#18 按用户确认的草稿评论后关闭（CLOSED/COMPLETED，回读一致）。地图剩余：E29 线上日志验收（需 AWS 凭据）；卡 022 C-1/C-4 与线上验收另立卡。
- 2026-09-26：E28（1f2c9097）、E29（5714aebf）已上线并核查；INFO 日志已在线上可见，E26 的读数查询生效。本地图的实施票据全部 released，只剩 #18 等真实流量读数后关闭。
- 2026-09-26：#18 已关闭（用户账号 22:32Z 关闭并评论，地图会话 22:41Z 追加生产读数）；卡 114 已更新到当前事实（stoa-docs a7728a6）。审计的 8 条 issue 加 #22 全部关闭。
- 实施票据在 [exec/](exec/)，E01–E29、R01、R02、D01 已生成。阻塞边：E18 ← infra 9858946 已部署（R02）；E19 无；E20 ← E19, E18；E13 ← E19；E22 ← E20 已部署；E21 ← E20, E13, E22；D01 ← R01 第 4 步；对外动作（push、评论、关 issue）逐条确认。本地图已收口。Not yet specified 里的线上验收、卡 022 C-1/C-4、sweep 稀疏索引、infra 重发、归档均已转入 GitHub 地图 #23（票据 #27、#34、#46、#33、#45）；`suggest_teacher` 与 E14 边界留在 #23 的雾里。
- 2026-09-25：R02 完成（infra 9858946 run 36065554586；E18 30a2d7bd run 36109520881），E19 已上线（3fd92dc7，run 36110096659，stoa-api v118）。注意：infra 部署会自行构建后端 main 并重发到所有函数，别名随之移动（详见 R02）。E20 与 E13 现已解除阻塞。
- 2026-09-24 提交 a015a444 把本仓库的 issue tracker 配成 GitHub（`docs/agents/issue-tracker.md`）。本地图按用户 Q3 决定继续用本地 Markdown；此后的新效力默认走 GitHub。
- 2026-09-25：E20 上线（1318ffd7，run 36129836249）；E13 合入 stoa-frontend main 并上线（3aae4b2 + e347fc7 等待上限 240→360 秒，run 36130597284）。R01 第 4 步完成：#3 #6 #7 #19 #20 #21 按用户逐条认可的草稿评论后关闭，回读一致；第 3 步冒烟用户选择暂缓。E13 追加卡 103 验收的渲染测试时发现并修复：失败与停止时助手气泡未被标记（updater 懒读已清空的 ref），光标永不消失（ad40c74，已上线 run 36137475229）。

## Decisions so far

<!-- 一行一条已 resolved 票据：标题链接 + 一句摘要 -->
- [年级应如何从准入限制改写为讲解深度（#19）](issues/01-grade-as-depth-prompt.md)：提示词按草稿改，年级只定深度与前置引导；两道超纲题捕获测试；上线冒烟不推断拒答率。→ E1
- [被截断的结构化输出应落成失败还是受支持的部分答案（#21）](issues/02-truncated-output-terminal-state.md)：走可恢复失败；`max_tokens` 判定移到解析前、残缺 JSON 不回退成原文；抛错前保留用量证据并释放预留。→ E2
- [Accept-Language 的权重与 q=0 应如何进入语言协商（#20）](issues/03-accept-language-q-values.md)：按 q 稳定降序取首个受支持语言，畸形项跳过，q≤0 剔除，无可用则 None。→ E3
- [周报生成路径的投递前应如何重判当前关系（#3 余量）](issues/04-report-delivery-rejudge.md)：SES 前一刻用共享三态解析重判，区分关系失效与邮箱缺失，地址取当前 profile，状态复用 `email_failed`。→ E4
- [支付解冻前，权益子女判据应如何改到当前关系（卡 022 B-2）](issues/05-entitlement-current-children-gate.md)：改用 `current_children`，负例针对旧绑定反向撤销；C-4 另立卡；英文 issue 稿已备。→ E5、票据 06
- [定时删除扫描应如何在多次调用之间保留进度（#7）](issues/09-deletion-sweep-progress.md)：持久化带 version 的游标控制行，多轮累计扫到表尾为一周期；远端调度 5 分钟一轮、limit 25。→ E7
- [把 B-2 建成 GitHub issue](issues/06-file-entitlement-issue.md)：用户确认后按票据 05 英文稿建成 [#22](https://github.com/stoasystem/stoa-backend/issues/22)，回读一致；E5 提交引用 #22。
- [PDF 结构预校验应升级依赖还是搬进受限解析进程（#6）](issues/10-pdf-prevalidation-isolation.md)：先升 pypdf 6.19.0 并重签例外，再把结构校验搬进受限子进程，超时不放行。→ E8、E9
- [AI 生成搬出 29 秒请求生命周期有哪些可行落点（#18 研究）](issues/07-runtime-budget-research.md)：HTTP API v2 的 30 秒不可提高，Python 运行时不原生流式，前端已在轮询但拿不到终态且重试换幂等键；三个方向 A/B/C 的仓库触及面已列出，供票据 08 决策。全文在分支 `research/ai-runtime-budget`。
- [AI 回答应在请求内完成还是搬到独立生命周期（#18）](issues/08-runtime-budget-architecture.md)：方向 B，提交与完成分开、worker 条件领取、lease 到期三态区分、异步上下文随命令持久化、幂等键复用；先单独上一提交让调用受实际剩余运行时约束；三仓 infra → 后端 → 前端上线、反向回退。→ E10–E13
- [结果未知的对话命令，其额度预留如何收敛（E20 余量）](issues/14-needs-reconciliation-reservation.md)：超过 10 分钟按「成本未知」结算（restore 预留、成本按上限记）并告警；E10 未重试的预留同路。→ E24
- [第三次尝试本身中断的命令，其额度预留如何收敛（E24 余量）](issues/15-terminal-failed-reservation.md)：两类（`terminal_failed`、超窗过期 `ai_running`）都收，走 E24 路径按上限结算，超窗的一并标 terminal；先上计数。→ E26、E27；丢答案另立票据 16
- [第三次尝试已存下的答案在标 terminal 时被丢弃（票据 15 余量）](issues/16-attempt-three-kept-answer.md)：算缺陷，只修今后不回填；带已存答案的最后一次尝试可再领取只补完、不调模型，以提问后一天为界。→ E28
- [question 路由上带用量证据的 AI 失败应如何处置（E2 余量）](issues/11-question-route-paid-failure.md)：带 `usage` 的失败视为已知结果，观测成本、terminal 加补偿，不标 unknown、不靠重放再调模型。→ E14
- [失败命令按住删除扫描游标应有怎样的上限（E7 余量）](issues/12-deletion-sweep-hold-limit.md)：最多按住 3 轮，`held_runs` 与游标同一条件写，越过时记名、命令状态原样保留；顺带修完成时间。→ E16
- [缺游标方法的注入 repository 应拒绝还是静默退回（E7 余量）](issues/13-deletion-sweep-no-silent-fallback.md)：scan/claim 之前缺接口即失败，只保留真实 repository 的扫描签名，迁移 phase473 那条注入替身的用例。→ E17

## Not yet specified

- AI 求助判断已有、未接线（2026-09-26 用户决定先不做）：模型每次回答都输出 `suggest_teacher`，E1 的提示词也规定了何时标 true，但前后端没有任何地方读它，对话路由拼回答时直接丢弃。学生仍可随时通过每条回答下固定的「Soll eine Lehrperson helfen?」卡片自行求助。理由：目前常无老师在线，主动提示会让学生落空。等老师在线时间稳定后，再立决策票据定显示方式与老师不在线时的说法（需后端存取该字段、前端据此显示）。
- E14 的记账失败边界：结算时若观测成本或归还预留失败，effect 停在 `invoking`、成本证据丢失，重放不再调模型，等既有 intent 过期的 exact-once 补偿收敛。沿用既有模式；若要补成本证据的持久化，另立票据。
- E9 之后每次 PDF 上传校验多一次隔离进程 spawn（本机约 0.27 秒）。可接受；若上传延迟成为问题，再考虑复用长驻 worker。
- E20 之后 `needs_reconciliation` 的命令预留永久 reserved，尚无对账：已立决策票据 [14](issues/14-needs-reconciliation-reservation.md)，已决议并由 E24 上线。
- E20 的 sweep 每 5 分钟过滤扫描整表（上限 50 页）；表增大后需要面向等待命令的稀疏索引，可并入 stoa-docs 卡 047 的 GSI 批次。
- infra 流水线每次部署都重新发布后端 main 到全部函数（R02 发现），E21/E22 的上线与回退按此排序，已写进两张票据。
- 已关闭的 12 条 issue 与本地图各修复的线上验收：需要真实环境读数，本轮不规划；等修复上线后另立效力。
- AI 终态模型已在票据 08 决议第 4 条与 E11 合并；实施时若发现 E2 与 E11 的失败类别不能共用一套，再回到这里立票据。
- 卡 022 C-1（两份等价关系判据实现）与 C-4（`_profile_claims_binding` 只读 profile 的 `parent_id` 加 `parent_binding_status`，不读反向行）已决定不随 B-2 收口，各自另立卡；何时立看修复上线后的余量。

## 与 stoa-docs 卡 028–113 的对接（2026-09-25）

远端 `stoa-docs/任务卡.md`（654b97a）新增 86 张卡，由另一位开发者 2026-09-24 的四条并行调研产出，**没有一处引用审计 issue 或本地图**；卡 022 未变。逐张比对后，有交集的 14 张按下面处置。「并入」= 卡里的对应部分由本地图的票据承接，卡只保留其余部分；「依赖」= 顺序约束；「补注」= 卡里要加一句对接说明（由 D01 一并写进 stoa-docs）。

| 卡 | 交集 | 处置 |
|---|---|---|
| 043 D-15 危机内容检测 | 改提示词、改 `conversations.py` 消息入口；E1 已把「emotional distress → suggest_teacher」改成先解释再建议 | **依赖 E19**：第一层确定性检测放在 `commit_message_command`（请求侧，worker 无关），Guardrail id 挂在 `generate_for_command`（worker 侧）。E1 的 suggest_teacher 语义不动 |
| 046 A-06 `/admin/users` 3207 次往返 | 同一个 29 秒天花板，不同路由 | 不交叉。E10 的 `runtime_budget_service` 可供它读剩余时间，补注即可 |
| 047 D-19 / 049 D-10 GSI 与教师侧读路径 | 决议 09 明确删除扫描不建 GSI | 不冲突：实体不同。049 引用的 `_list_escalated_questions` 分页预算正是 #10 的修法 |
| 070 C-05 降级分支零执行 / 075 C-04 事务替身收敛 | 票据 13 只关了 job 层的探测；`account_deletion_repo` 仍有 20 个表级钩子，含 sweep 用的 `scan_pending_deletion_commands`（:1536）与 `claim_deletion_command`（:1690），以及卡 022 C-9 的 `delete_owned_row`（:1057） | **E23** 先摘 sweep 的两个表级钩子（票据 13 的余量）；其余钩子归 070/075。本地图 Out of scope 里的 C-9 即卡 070/075 |
| 071 C-07 语言闸 + 后端 locale 传递 | 组 A（学生 locale → `ai_service` 的 `language`）、组 B（hint 标签）与 E3 同一测试文件；E19 之后 language 来自持久化命令而非请求 | **后端部分并入 E19**（E19 验收已含「不再读请求头」，加上 hint 标签那条）；卡 071 只保留前端 |
| 073 C-13 用户报过的 bug 回归 | 清单来自 9 月 16 日黑盒，不含 #18/#19/#20 三个 AI 症状 | 不交叉；三个症状的回归已在 E1、E3、E19–E21 的测试里。补注 |
| 074 C-03 替身 vs moto 合约 | E7 在 FakeTable 里修过一处保真 bug（`if_not_exists(a,:v)+:one` 被当函数调用） | 作为 074 的一条已知偏差样例，补注 |
| 078 C-10 AI 回复离线评测 | E1 的边界：提示词测试量不到拒答率；R01 冒烟只有两道题 | **依赖补充**：题目集加「超纲同学科题」一组（数学 G6 导数、物理 G5 量子及同类），输出「拒答率」读数，替代 R01 里的人工冒烟成为长期量具 |
| 095/096/098 教师升级与 SQS 路径 | 098 删未部署的 `jobs/teacher_escalation.py` 与 SQS 队列（研究票据 07 §2.2 的发现）；也改 `api_stack.py` | 不冲突：方向 B 用异步 Invoke 不用 SQS。**顺序**：098 的 infra 改动与 E12/E22 都动 `api_stack.py`，排在 E22 之后或同一人串行做。#14 已修的 handler 随 098 删除，无损 |
| 103 A-24 伪流式前端单测 | 钉「SSE 分块逐步渲染」，而 E21 之后请求不再同步返回 SSE，步骤来自 `/generation` 轮询 | **并入 E13**：改为钉「轮询到的 `steps` 单调增长、终态前光标可见、终态后消失、缺终态有失败态」；103 里「P2-4 真流式归产品方向」改指票据 08 方向 B |
| 107 D-09 WebSocket / 109 D-20 回收轮询 | 107 写「不解决伪流式（那是 Function URL 的事）」 | 补注：方向 B 已定，不走 Function URL；E13 的 `/generation` 轮询列入 109 将来回收的清单 |
| 110 A-08 `upload_cleanup` 未部署 | 新增一个 Lambda → 后端 `test_每个声明出来的lambda都会被后端部署更新` 会红 | **依赖规则**：同 E12/E18 的顺序（infra 先、后端部署列表行立即跟上、`EXPECTED_HANDLERS` 同步）。补注 |
| 111 A-09 告警与 DLQ | E12 新增第 5 个 DLQ `stoa-conversation-generation-dlq` 与第 5 个 Lambda，均无告警；111 写的是「四个 DLQ」 | **E22 承接 worker 自己的错误告警与 DLQ 告警**（按 111 的形状）；111 的计数改为 5，「每个告警都有 action」那条通用闸仍归 111 |
| 112 D-08 学生等待体验 | 同一 ChatPage，112 给 `useConversationQuery` 加 10 秒轮询，E13 给 `useStreamingChat` 加终态轮询 | 补注：两个轮询周期与停止条件要在同一处声明，避免同页两套节拍；先做的一方留接口 |
| 拍板 Q4 `eu.` 跨区推理 | E12 在 infra 第三次写死 `BEDROCK_MODEL_ID` | **E22 顺带**把模型 id 收成 infra 一个常量，Q4 无论选 (a)/(b)/(c) 都只改一处 |

没有任何一张卡与方向 B 冲突；D 组没有「真流式」卡，只有 103、107 两处附注假设 Function URL，已在上表处理。新卡编号规则：新卡加在最前、取最大号 +1，D01 的卡号为 **114**。

## Out of scope

- 在本地图内写业务修复、提交、部署或线上操作；地图交付的是规范。
- 支付业务本身的解冻与测试；B-2 只决定解冻前必须先改什么。
- 卡 022 其余 C 级项（C-5 至 C-12）：不在 GitHub issue 里，另立卡评估。C-9 的 `delete_owned_row` 测试逃生口已由 stoa-docs 卡 070/075 承接；sweep 自己的两个表级钩子除外，见 E23。
- 对话路由内同步 IO 阻塞 ASGI worker、前端重试换幂等键、轮询文本重复追加：AI 审计观察到但未复现，不列为本次修复对象；若票据 08 的研究证实，再由 08 提出。
