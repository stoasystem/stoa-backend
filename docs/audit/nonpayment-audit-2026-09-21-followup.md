# 非支付审计后续检查与 Issue 发布 — 2026-09-21

已发布 **16 条 Issue（5 P1、11 P2）**：15 项代码缺陷和 1 项依赖例外门禁问题。相较[首轮报告](nonpayment-audit-2026-09-21.md)，本轮新增 4 项代码缺陷（NP-12—NP-15），补强 NP-02 的重发路径证据，并将首轮已发现的依赖例外过期单列为 NP-16。

审计与发布前核实的远端版本均为 `f47fe62202f363354883a0ba3308fa50217054d8`。支付业务继续排除。本轮重点检查了密码验证码、邀请恢复、账号生命周期写入、家长关系、周报恢复和异步消息入口；另检查了通知、WebSocket、上传清理及数值类型调用点，没有将未经复现的猜测列为确认问题。

## 已发布问题

| 审计编号 | 级别 | 问题 | GitHub |
|---|---|---|---|
| NP-01 | P1 | 撤销关系后家长账号汇总仍暴露学生资料 | [#2](https://github.com/stoasystem/stoa-backend/issues/2) |
| NP-02 | P1 | 周报生成及重发未核验当前家长授权 | [#3](https://github.com/stoasystem/stoa-backend/issues/3) |
| NP-03 | P1 | 删除分支漏掉新家长关系并错误报告完成 | [#4](https://github.com/stoasystem/stoa-backend/issues/4) |
| NP-04 | P1 | 登出后旧 JWT 仍可访问后端 | [#5](https://github.com/stoasystem/stoa-backend/issues/5) |
| NP-05 | P2 | PDF 上传校验在隔离之前调用存在 DoS 缺陷的解析器 | [#6](https://github.com/stoasystem/stoa-backend/issues/6) |
| NP-06 | P2 | 删除任务跨轮丢失扫描进度 | [#7](https://github.com/stoasystem/stoa-backend/issues/7) |
| NP-07 | P2 | 新家长关系未进入周报发现和生成流程 | [#8](https://github.com/stoasystem/stoa-backend/issues/8) |
| NP-08 | P2 | DynamoDB Decimal 导致教师课程授权失败 | [#9](https://github.com/stoasystem/stoa-backend/issues/9) |
| NP-09 | P2 | 教师求助队列忽略 Scan 后续页 | [#10](https://github.com/stoasystem/stoa-backend/issues/10) |
| NP-10 | P2 | 学生对话列表忽略共享索引后续页 | [#11](https://github.com/stoasystem/stoa-backend/issues/11) |
| NP-11 | P2 | 未知 JWT kid 逐请求触发 JWKS 抓取 | [#12](https://github.com/stoasystem/stoa-backend/issues/12) |
| NP-12 | P2 | 验证码消费未绑定所验证的挑战记录 | [#13](https://github.com/stoasystem/stoa-backend/issues/13) |
| NP-13 | P2 | 教师升级 Lambda 错读原生 SQS 消息字段 | [#14](https://github.com/stoasystem/stoa-backend/issues/14) |
| NP-14 | P1 | 家长关系写入绕过双方账号删除 fence | [#15](https://github.com/stoasystem/stoa-backend/issues/15) |
| NP-15 | P2 | 邀请重发写入失败后无法使用原句柄恢复 | [#16](https://github.com/stoasystem/stoa-backend/issues/16) |
| NP-16 | P2 | 依赖例外过期导致当前时间门禁拒绝 | [#17](https://github.com/stoasystem/stoa-backend/issues/17) |

Issue 均使用英文，包含固定提交的源码链接、触发条件、观察结果、验证边界和验收方向。发布前通过连接器搜索及 GitHub REST 的全部状态列表查重：当时没有已有 Issue，唯一历史条目是已关闭 PR #1。

## 本轮新增代码缺陷

### NP-12 / #13：旧验证码可能消费新验证码

`password_change_code_service.verify_and_consume` 先读取挑战，再比较摘要，但最终更新只检查 `consumed_at` 不存在。Moto 可控交错中，验证 A 读取后存入 B，再让 A 提交：A 获准，B 被标记已消费。另一个用例在读取后将 attempts 增至 5，提交仍被接受。

这违反挑战替换和尝试次数边界；密码修改路由仍需要登录身份和当前密码，因此没有将它描述为独立账号接管。最小修复方向是复用条件写，绑定确切挑战身份及其有效状态。

### NP-13 / #14：SQS 原生事件没有进入教师派发

消费者读取 `Body`，Lambda handler 却直接传入原生 `Records[*]`，其字段名是 `body`。同一内容使用 boto3 ReceiveMessage 格式可成功；使用 AWS Lambda 格式则返回 `legacy_debt=1, processed=0`，没有派发调用。

AWS 的[原生事件格式与成功批次确认语义](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)支持该触发条件。当前生产的事件源绑定未检查，因此结论限定为该 handler 直接接收原生 SQS 事件时的缺陷。

### NP-14 / #15：删除受理后仍能新建家长关系

对家长、学生分别使用真实 `begin_account_deletion`，先确认 fence 为 `deletion_pending`，然后调用真实 `assign_link`。两个用例都成功写入 active 的双向关系。此时 profile 尚未被后续删除分支清理，仍为 active；服务只读 profile，关系事务又没有双方 fence 条件。

这与 NP-03 分别对应“写入准入”和“既有数据清理”，需分别验证。建议将双方 active fence 条件与双向写入置于同一个现有 DynamoDB 事务。

### NP-15 / #16：重发邀请失败后原句柄不可恢复

真实邀请创建后，重发先撤销旧邀请，再写新邀请。在新邀请写入边界注入一次临时失败，恢复存储后重试同一旧邀请 ID，得到 409 `invitation_not_reissuable`；旧邀请为 revoked，没有返回新的令牌或管理句柄。

应采用原子替换或可恢复的重发命令。不能简单允许所有 revoked 邀请重新发放，否则会破坏旧邀请失效和单一有效令牌的约束。

## 补强与门禁问题

- **NP-02 / #3：** 重发路径用例在 Moto 中保存 revoked 的旧家长关系，并保持学生 fence active；真实恢复服务仍将旧邮箱及合成私密 HTML 交给本地 provider recorder。未发送真实邮件。这将首轮授权缺陷扩展到了实际重发调用边界。
- **NP-16 / #17：** 对当前仓库账本调用 `validate_exception_ledger(..., now=datetime.now(timezone.utc))`，得到 `dependency exception is expired`。例外到期为 2026-08-18 09:00 UTC。未将 RS256-only 路径下的 ECDSA 公告误报为已证实可利用漏洞；问题是过期例外和当前门禁不能通过。

## 验证结果与保留证据

本轮新增规格执行结果为 **7 failed、0 errors，74.22 秒**。七项均失败于预期安全/行为断言，无收集、fixture 或外部连接错误。失败表示成功复现现有缺陷，尚未修复。

首轮基线继续保留原始结论：2979 passed、32 failed、5 skipped；32 项为跨仓库 release gate 根目录解析问题。本轮没有修改业务代码，因此未重复整套基线。首轮 12 个回归用例和本轮 7 个合计 19 个反例规格；PDF 使用独立受限子进程探针。

本轮证据目录：`.scratch/nonpayment-audit-20260921-round2/`：

- `test_round2_regressions.py`、`regressions.log`、`regressions.xml`：测试输入、完整失败输出与结构化结果。
- `issues/NP-*.md`、`issues/NP-*.json`、`issue-payloads.json`：审阅后发布的精确内容。
- `publication-receipts.jsonl`：每次创建/确认的返回编号和正文 SHA-256。
- `publication-verified.json`：按每个返回编号独立 GET，核对 16 条 Issue 的标题、正文及 open 状态。
- `manifest.json`：本轮报告与证据摘要。

复现本轮规格（预期退出码 1）：

```bash
env -u AWS_PROFILE AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_SESSION_TOKEN=testing AWS_EC2_METADATA_DISABLED=true \
AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null \
.venv/bin/python -m pytest -q --tb=short --disable-socket --allow-unix-socket \
  .scratch/nonpayment-audit-20260921-round2/test_round2_regressions.py
```

## 发布记录与范围

GitHub 连接器的创建请求返回 403（集成无写入权限），没有创建条目；随后使用本机已授权的 `gh` 创建 #2—#17。创建响应核对通过；首次集合回读遗漏一个新条目，随后改用每条已返回编号的直接 GET，全部核对成功，未重复创建。独立确认时间为 2026-09-21 21:47:10 UTC。

首轮报告和证据保持原样，本轮新增报告独立保存。业务代码没有修改，没有提交、推送、部署、调用生产 AWS 或发送真实邮件。此次外部写入仅为用户要求的 GitHub Issues。后续应先处理家长授权与生命周期（#2/#3/#4/#8/#15），再处理登出撤销（#5）及其余功能、资源和门禁问题。

