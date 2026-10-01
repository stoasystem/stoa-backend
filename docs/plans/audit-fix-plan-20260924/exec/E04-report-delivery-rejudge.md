# E4 周报投递前重判当前关系并解析当前邮箱

Status: released
Blocked by: 
Decision: [票据 04](../issues/04-report-delivery-rejudge.md)
GitHub: #3

## Delivers

周报生成后、发信前，关系已撤销的家长收不到孩子的报告；收件地址来自家长当前 profile。

## Change

抽共享函数（建议放 `parent_link_service` 或 `report_recovery_service`）返回三态：`no_relationship` / `recipient_missing` / `(email)`；`report_service.store_and_send_weekly_report` 在 S3 写入之后、`send_fenced_weekly_report_email` 之前调用它，不发信时 `update_report_status(..., "email_failed", email_status="failed", email_error_class=<原因>)`；`report_recovery_service._current_recipient` 改用同一函数并区分原因。收件地址不再读 payload 的 `parent_email`。

## Acceptance

payload 判后撤销 → 无 SES 调用、`email_failed/relationship_revoked`；payload 生成后家长改邮箱 → 发到新邮箱；家长当前邮箱缺失 → 不发送、`recipient_missing`；有效新 link → 正常发出且 `email_status=sent`；旧绑定撤销、账号删除中两条既有用例保持。

## Poison

去掉生成路径的重判 → 第一条红；把地址改回 payload → 第二条红。

## Commit

单独一个提交。CONTEXT.md 的「当前关系」词条已由地图会话补上，不在此提交内。

## Verification

2026-09-24 地图会话核查，提交 `3a005cc7`。生成路径 6 条（当前家长、新 link、payload 后撤销、payload 后销户、地址变更、地址缺失）与重发路径 3 条通过。投毒：去掉关系重判 → 5 failed；改回 payload 地址 → 1 failed。行为变化已在提交信息写明：重发不再要求报告存有 `parent_email`，当前家长无地址时重发返回 422 `recipient_missing`。报告记录里仍归档 `parent_email`（数据静态存在，不再用于投递）。

全量离线回归（排除依赖相邻 infra 根目录的两个 release-gate 文件）3541 passed / 0 failed；`test_formal_release_gate.py` 的一条失败在这五个提交之前的 a015a444 上同样失败，属既有 infra 根目录问题。ruff 对改动文件全部通过；mypy 报错都在未改动的文件里。与远端 origin/main 新增的 4 个提交（b7b1b4f8…ef0827c9）在临时 worktree 里合并无冲突，重叠文件相关 308 条测试通过。五个提交**尚未推送**，未部署。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
