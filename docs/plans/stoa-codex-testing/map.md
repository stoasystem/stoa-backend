# STOA 自动化测试：功能、安全与稳定性决策地图

Labels: wayfinder:map
Status: open

## Destination

为 STOA 当前产品确定一套可交给 Codex 与既有测试工具实施的自动化测试规范，覆盖功能、安全和稳定性。完成时，环境、实际功能范围、执行权限、放行条件、运行频率及成本、四仓库集成方式均已有明确决策，并能据此生成实施顺序和验收清单。

## Notes

- 本轮遵循用户原始请求“制定流程”及后续“使用 Wayfinder 完成规划”，规划不包含实现测试框架、运行线上写入、部署或启用定时任务。
- 当前为逐票据决策阶段。按 Wayfinder 维护地图与依赖，不把 agent 建议冒充 HITL 决策，每轮只解决一张非研究票据。
- 使用技能：Wayfinder；HITL 决策使用 grilling 和 domain-modeling。需要 Codex 能力事实时使用 OpenAI Docs。术语见 [STOA 学习与真人支持](../../CONTEXT.md)。
- 使用本地 Markdown tracker；本仓库未发现显式 tracker 配置。遵循 Wayfinder 默认及其同目录技能集合提供的 `issue-tracker-local.md`。未来需要持久团队 tracker 时可运行 `/setup-matt-pocock-skills`，本轮不配置 GitHub 或创建远端 issue。
- 子票据独立存于 `issues/`；`Status: open` 表示未领取，`claimed` 表示已领取，`resolved` 表示完成。`Blocked by:` 使用本地编号，全部前置票据 resolved 后才进入 frontier；按文件编号选取第一个未领取项。
- claim 在任何票据决策工作前写入；解答追加至票据 `## Answer`，然后 resolved，再在本地图追加标题链接和一句摘要。标题是对用户的引用名称。
- 当前证据资产：[STOA 自动化测试讨论草案](../../docs/testing/STOA_CODEX_AUTOMATED_TEST_PLAN.md)。它记录四仓库 SHA、已核查缺口、功能/安全/稳定性建议，不是已定案规范。决策详情仅在票据，不在草案与地图重复维护。
- 已核对前端静态契约检查：147 个识别到的服务调用匹配 196 个后端路径。该证据不能替代字段校验、真实链路或云端部署核实。
- 简单成熟方案优先：复用 pytest/Vitest/Playwright、现有 HTTP 冒烟、CDK 与 release/dependency 入口；新增能力需有被现有工具无法覆盖的具体需求。
- 图中准备解决的是决策，不是把实现任务冒充决策票据。所有数字目标、预算和排期都在相关票据决议前保持建议状态。
- 已批准首轮决议的执行步骤见[首轮测试执行规范](../../docs/testing/STOA_CODEX_FIRST_RUN.md)。首轮尚未执行；地图保持 open，后续性能决定仍需要基线证据。

## Decisions so far

- [真实测试应使用哪些环境和数据边界](issues/01-environment-boundary.md)：独立测试环境承担完整合成测试；线上只允许受控合成账号的有限核心冒烟，不能替代完整验收。
- [哪些当前产品能力必须纳入首版真实验收](issues/02-product-acceptance-scope.md)：首版覆盖核心学习、真人老师、家长、权限和删除；支付暂不测试，原生与 Demo 能力排除。
- [Codex 在测试失败后可以自动执行到哪一步](issues/03-agent-authority.md)：仅运行测试并记录问题；不修改代码、测试、配置或门禁，不生成修复 patch。
- [什么证据足以判定功能和安全测试通过](issues/04-release-verdict.md)：必需用例实际通过且环境版本可核对才整体通过；失败、未验证和不稳定分别保留，范围外项目不计通过。
- [当前产品需要承诺怎样的响应和恢复能力](issues/05-stability-targets.md)：先测基线，首轮逐流程三次、整轮最多 60 分钟；严重数据或权限问题立即停止，性能门槛待基线后确定。
- [自动运行频率、成本和通知应如何取舍](issues/06-cadence-cost-notification.md)：首轮手动触发、当前任务汇报；AWS 与模型新增费用合计最多 5 美元，Codex 使用现有额度，费用不可控项记为阻塞。
- [如何把既有测试接入四仓库并交付可实施规范](issues/07-cross-repo-rollout.md)：backend 汇总报告，各仓库运行已有适用检查；按预检、本地检查、独立环境核心流程和报告的顺序执行，需修改项记为阻塞。

## Not yet specified

- 首轮环境选择及性能目标确定后，才能判断是否需要额外资源隔离或专用负载工具；若确有新选择，再将其形成准确问题。
- 实际确认保留功能后可能出现更细的 AI 评估或原生移动端验收边界；先不推定未启用能力的测试承诺。

## Out of scope

- 本轮编写业务修复、自动合并、发布、远端 issue/评论、部署及定时任务启用；此地图交付规划依据。
- 使用真实用户数据、真实扣款、对共享环境无限压测或整表清理。
- 新建通用测试管理平台、多智能体编排框架、重新设计 STOA 产品或替换已有测试栈。
- 把历史报告、mock 通过、Git 同步或仅路径匹配作为当前线上产品通过证明。
