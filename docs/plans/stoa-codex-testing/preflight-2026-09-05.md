# STOA 首轮基线只读预检

日期：2026-09-05。结论：真实核心流程 BLOCKED；本次仅检查本地源码、配置和 Git 状态，未发送云端请求、运行真实流程或测量性能。

## 当前输入

| 仓库 | 本次读取 HEAD | 工作区状态 |
|---|---|---|
| backend | fe19facca111d23ea24b41ca0964ef593b159841 | 未跟踪 .scratch/、CONTEXT.md、docs/testing/ |
| frontend | 49fb7bcd83302b66d65492d95bf84e6591cc57ea | 干净 |
| infra | e8aa182687b5ef5821f4005ccb5925ffde93d2f0 | 未跟踪 .DS_Store |
| docs | ecde75bc25c8dcf4ca07b99bb2a1c160f22b5c4d | 未跟踪 .DS_Store |

以上为读取时快照；没有改动已有代码、配置或未跟踪文件。当前提交与历史讨论草案列出的起点相同，但这不证明已部署版本相同。

## 发现的问题与缺少的输入

1. **独立环境身份未确认。** 本轮已读的规划文档未给出完整、经核对的独立环境资源映射（Web/API、User Pool、各角色 client、存储、版本、合成账号凭据引用）。没有据此判断云端资源不存在；需要实际配置位置作为下一步输入。
2. **HTTP 冒烟不能仅靠 base URL 隔离。** `scripts/smoke_live_flows.py` 的默认 URL 指向线上，region、合成账号邮箱及教师/管理员 Cognito client 固定于源码；`every_account_can_sign_in()` 会调用 `backfill_account_registration.py --verify`。后者使用 `DYNAMODB_TABLE_NAME` / `AWS_REGION`，缺省为 `stoa-main` / `eu-central-2`，并执行表扫描。现有调用不先证明目标资源全部属于同一独立环境；未运行该入口。
3. **默认浏览器配置是 Demo。** frontend `playwright.config.ts` 的普通 webServer 启用 Demo API / Mock Checkout，并指向 `127.0.0.1:65535`；chromium 未排除支付用例。真实远端分支绑定 Stripe sandbox preflight，而支付已排除。当前配置不能直接作为所需非支付真实流程的通过证据。
4. **真人老师闭环覆盖不足。** `smoke_live_flows.py` 的真人老师路径检查派单、排队和学生查询状态，没有执行老师回复与结单。额度耗尽记为 skip，最终只检查 failed 决定退出码，可能 skip 后仍退出 0；报告必须遵循已批准的未验证规则。
5. **5 美元预算上界未证实。** 所读入口未提供可确认的整轮费用上界；实际模型、token 上限及资源计费映射尚未核对。不宣称一定超预算，也不按无法验证的成本假设运行付费流程。

这些是预检与覆盖缺口，不是通过运行产品测试发现的断言失败。独立环境配置即使补齐，仍须核对上述入口限制；在仅测试、不修改的权限下，无法直接执行的项目保持 BLOCKED。

## 下一步

取得已存在的独立测试环境配置文件位置及合成账号凭据引用位置（不在对话中提供密钥明文），检查能否使用既有入口直接满足隔离、范围及预算约束。若已有另一套非支付真实测试入口，应一并指出位置。未取得基线前，不解决性能门槛票据。

## 用户补充：获准使用的测试账号

用户明确授权直接使用以下测试账号；角色与关系为用户提供，尚未通过登录或服务端读取核验。

| 账号 | 角色 | 用户说明 |
|---|---|---|
| <admin test account> | admin | 管理后台 |
| <student test account> | student | 学生演示 |
| <parent test account> | parent | 已绑定上述学生 |
| <teacher test account> | teacher | 已开放派单 |
| <agent test account> | student | 用户运行测试使用 |

这解决了账号使用授权；未提供登录密码或凭据引用，也未确定账号所在环境。角色名不是密码，不尝试据此猜测登录凭据。

本轮检查三个执行仓库中的 `.env*` 文件，仅发现 backend/frontend 的 `.env.example`；当前进程未发现 STOA_*、PLAYWRIGHT_*、AWS_PROFILE、AWS_REGION 或 DYNAMODB_TABLE_NAME 配置键。此检查不代表系统其他位置没有凭据。仍需登录网址与凭据存放位置；此前批准的独立环境/线上有限冒烟边界继续适用。

## 后续更新

用户随后提供 app.stoaedu.ch 和共享测试密码，凭据已按授权保存于 macOS 登录钥匙串（service: app.stoaedu.ch.codex-smoke，account: stoa-test-accounts）。公开发布描述确认该站点属于 production；已执行[线上合成账号有限冒烟](runs/20260905-production-smoke/report.md)。登录凭据缺口已解除，独立环境与完整基线缺口仍在；保留上述预检作为历史记录。
