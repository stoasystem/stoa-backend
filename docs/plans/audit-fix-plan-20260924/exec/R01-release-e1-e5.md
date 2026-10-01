# R01 本地后端提交发布与 GitHub 收尾（E1–E10、E14、E16、E17）

Status: released
Blocked by: E01–E10、E14、E16、E17 已 verified-unpushed
Decision: [票据 01/02/03/04/05](../issues/01-grade-as-depth-prompt.md)
GitHub: #3 #6 #7 #19 #20 #21（#18 等 E11）
Type: task
Mode: HITL

## Delivers

本地全部后端提交在生产运行，对应 GitHub issue 状态与事实一致。

## Change

按顺序，每步都有读数：
1. 本地 main 合入 `origin/main`（演练无冲突；重叠文件 `routers/conversations.py`、`tests/test_parent_link_paid_downstream.py`），再跑全量离线套件（排除两个依赖相邻 infra 根目录的 release-gate 文件），记录 passed/failed。
2. `git push origin main`；`gh run list --limit 3` 盯 "Deploy Backend to Production" 到 success；`curl` served release 或函数版本确认新 SHA 已上线。
3. 冒烟（只算冒烟，不推断拒答率）：用测试学生账号，数学 Grade 6 问 "Was ist eine Ableitung? Erkläre es mit einem einfachen Beispiel."，物理 Grade 5 问 "Was ist Quantenphysik? Erkläre es mit einem einfachen Beispiel."；记录是否给出解释、`suggest_teacher` 值、回答语言是否与请求语言一致（语言错配作为线上观察记录，不单独立票）。
4. GitHub 收尾，**每条动作前向用户确认一次**：#19、#20、#21 评论修复提交与验证边界后关闭；#3 评论生成路径已在 3a005cc7 补齐（投递前重判、三态收件判定）后关闭。#7 在 E16、E17 上线后关闭，主要引用已提交的 `tests/test_account_deletion_sweep_cursor.py`，`.scratch` 里的适配见证只作补充说明。评论写明只有本地离线验证与一次冒烟。
5. 回填：地图 Notes 记发布 SHA 与冒烟读数；E01–E07 状态改为 `released`。

## Acceptance

deploy run success；线上版本 SHA 等于推送的 HEAD；两道冒烟题各有一条记录；四条 issue 状态为 CLOSED 且评论可见。

## Poison

不适用（发布任务）。

## Commit

无新代码提交。对外动作（push、评论、关 issue）逐条确认。

## Push order (2026-09-24 核查后修正)

报告里「infra 先推」的说法**不成立**：后端部署工作流把 stoa-infra 的 main 检出到相邻目录并跑全量 pytest，`test_每个声明出来的lambda都会被后端部署更新` 会读到 worker 声明。infra 若先推，后端任何推送都会在 CI 卡在这条红测试上，直到部署列表加名。正确顺序：

1. **先推后端 main**（到 750dbff8，即 E1–E8、E10、E14、E16、E17）：infra main 此时没有 worker，CI 绿；这些提交不引用 worker。盯 deploy run 到 success。
2. **再推 infra 9858946**：infra 的 deploy-production 在 push 到 main 时自动 `cdk deploy`；worker 创建后空转，sweep DISABLED。
3. **立即推 E18**（部署列表加一行）：让后端 CI 重新变绿。2 与 3 之间是后端 CI 被挡的窗口，越短越好。
4. E11、E13 按票据 08 的顺序之后再上。

#7 的关闭在第 1 步上线后进行，引用 `tests/test_account_deletion_sweep_cursor.py`；#21 的评论同时提及 E2 与 E14。

## Step 1 record (2026-09-24)

实施方合并 `origin/main` 的 4 个提交为 `653821db`（双亲 0e419007、ef0827c9），本地 main 领先 15、落后 0，工作区干净。四个双方都改过的文件（`routers/conversations.py`、`routers/questions.py`、`tests/fakes/dynamodb.py`、`tests/test_parent_link_paid_downstream.py`）无冲突。地图会话复核：在本机（相邻 infra 为含 worker 的 9858946）全量 3829 passed / 1 failed，唯一失败为有意留红的部署列表检查；CI 检出的 infra 是 origin/main（无 worker），该条在 CI 会通过，与实施方报的 3830 passed 一致。`git ls-files '*.py' | ruff check` 全过。E9（0e419007）在 R01 原清单之外但已提交，已补核通过（见 E9 Verification）。待推送集合：E1–E10、E14、E16、E17 加合并提交，均不引用 worker，可在 infra 之前推送。

#6 在第 1 步上线后可关闭（E8 加 E9），评论引用 `tests/test_pdf_validation_isolation.py` 与探针读数。

## Step 2 record (2026-09-24)

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。 待推送集合已全部上线。剩余第 3 步（冒烟）、第 4 步（GitHub 收尾）、第 5 步（回填）。

## Step 4 drafts: GitHub closure comments（每条发出前需用户确认）

**#19**（close）
> Fixed in 04fd9737, deployed 2026-09-24 (stoa-api production alias v115). The system prompt now keeps the subject boundary and uses the grade only for depth, examples and prerequisites; the "too complex → teacher" rule became "explain first, suggest a teacher only if the student stays stuck or shows distress". Tests `tests/test_ai_service_prompt.py` capture the outbound prompt for the two audited questions with in-grade and off-subject controls. Verified offline; the prompt test does not measure live refusal rates, one manual smoke per question is planned.

**#20**（close）
> Fixed in 71a7adf4, deployed 2026-09-24. `locale_from_accept_language` now ranks entries by q (1 when absent), drops q=0 and malformed weights, keeps header order on ties, and falls back to the profile preference when nothing is acceptable. Tests in `tests/test_locale_preferences.py`. Offline verification only.

**#21**（close）
> Fixed in 972cefe2 (conversation route) and 389e8a3b (question routes), deployed 2026-09-24. A `max_tokens` stop is refused before parsing as `incomplete_output`; a JSON fragment is never accepted as the answer; the failure carries the provider usage so the reservation is released (conversations) or the effect goes terminal with the cost recorded (questions), with no second model call on replay. Tests `tests/test_truncated_ai_output.py`, `tests/test_question_paid_ai_failure.py`. Offline verification only; `bedrock_max_tokens` unchanged at 2048.

**#3**（close）
> Completed in 3a005cc7, deployed 2026-09-24, on top of c1eee5f. The generation path now judges the relationship again immediately before SES and resolves the recipient from the parent's current profile through the same three-state function the resend path uses (`relationship_revoked` / `recipient_missing` / address). A revocation after the payload but before delivery no longer sends. Tests in `tests/test_parent_relationship_current.py` and `tests/test_report_service.py`. Offline verification only; stoa-docs card 022 B-1 is thereby addressed.

**#7**（close）
> Fixed in a72c7be3, 05727d3a, c0403c2e, aaf27cba, deployed 2026-09-24 (stoa-account-deletion production alias v26). The sweep stores its place in a versioned control row and resumes there; a failing command holds the place for at most three runs; a repository lacking the cursor methods is refused before any scan. Primary evidence: `tests/test_account_deletion_sweep_cursor.py` against the real repository and the shared table double. The original audit witness drove an unadapted double; adapted to the current signature it finds the command past 2,600 rows on the second sweep. Offline verification only; the schedule is `rate(5 minutes)`, `limit=25`.

**#6**（close）
> Fixed in 0404cf3c (pypdf 6.19.0, dependency exception re-signed against the new lock) and 0e419007 (structure check moved into the CPU/memory/wall-time-limited parser process; the API process reads only the magic bytes), deployed 2026-09-24. The audit's 4 MiB object-header input is rejected in 0.017 s on 6.19.0 and, when parsing is slow, by the worker's limits rather than the Lambda's. Tests `tests/test_pdf_validation_isolation.py`, `tests/test_dependency_policy.py`. Offline verification only; each PDF upload now pays one worker spawn (about 0.27 s locally).

## Step 4 record (2026-09-25)

用户逐条认可六条评论（AskUserQuestion 多选，六条全选）。按草稿原文发出并关闭：#19、#20、#21、#3、#7、#6，均 `CLOSED` / `COMPLETED`；逐条回读最后一条评论与认可文本逐字一致。

## Step 3 (2026-09-25)

冒烟未做：需要生产测试学生账号登录，用户选择「先跳过」。记为未完成；评论已写明只有离线验证，关闭不依赖冒烟。长期量具见地图对接表卡 078（超纲同学科题拒答率）。

## Step 5 record (2026-09-25)

回填：地图 Notes 记发布与关闭；E01–E07 状态已为 released/resolved。R01 除冒烟外完成。

## Step 3 record (2026-09-26)

生产 `app.stoaedu.ch`，内置浏览器，测试学生账号由用户登录（本会话不在生产站点输入凭据）。线上后端为 5714aebf（E29 之后），问答走 E21 的异步路径：`POST /messages/stream` 提交后前端轮询 `/generation` 至完成（第一题约 7 次）。

| 题 | 科目 | 是否给出解释 | `suggest_teacher` | 回答语言 / 请求语言 |
|---|---|---|---|---|
| Was ist eine Ableitung? Erkläre es mit einem einfachen Beispiel. | Mathematik | 是：定义、汽车速度类比、幂法则、f(x)=x² 求导与 x=3、x=0 两点解读，末尾提示 | 不可观测 | de / de |
| Was ist Quantenphysik? Erkläre es mit einem einfachen Beispiel. | Physik | 是：微观粒子、量子化、光子 E=h·f、楼梯类比，末尾提示 | 不可观测 | de / de |

说明：
- **年级未被测到**：该账号的 profile 年级为空（会话记录 `grade: ""`），票据要求的「数学 Grade 6 / 物理 Grade 5」没有按年级跑成；验证的是「超纲题在本学科内先解释、不拒答」，年级边界没有线上读数。
- **`suggest_teacher` 不可观测**：对话路由只用模型输出的 steps/answer/hints 拼回答，`suggest_teacher` 被丢弃，既不存也不返回；界面上的「Soll eine Lehrperson helfen?」是每条回答下固定的反馈块，与该字段无关。两题都没有转老师式的拒答。
- 请求语言取界面语言（`Accept-Language: de`，浏览器本身 en-US），回答均为德语，一致。
- 只算冒烟，不推断拒答率。长期量具仍是地图对接表卡 078。
