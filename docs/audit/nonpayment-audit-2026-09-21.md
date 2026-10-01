# 非支付代码审计 — 2026-09-21

本轮确认 **11 项问题：4 项 P1、7 项 P2**。12 个离线回归用例复现了其中 10 项；PDF 问题另有受限子进程探针和上游安全公告支持。审计没有修改产品代码。

## 版本、范围与证据边界

- 仓库：`stoasystem/stoa-backend`，分支 `main`。
- 初始版本 `04fca245`，远端领先 22 个提交；已 `fetch --prune` 并仅用 `merge --ff-only` 同步到 `f47fe62202f363354883a0ba3308fa50217054d8`。没有本地领先提交需要推送。
- 交付前再次执行 `git ls-remote origin refs/heads/main`，远端仍为上述版本，本地与 `origin/main` 的 ahead/behind 均为 0。
- 工作目录：`/Volumes/Codex-Workspace/live/home/zhdeng/stoa-backend`；旧路径 `/Users/zhdeng/stoa-backend` 是其符号链接。
- 范围：后端认证、权限、家长关系、账号删除、教师与学习流程、上传/解析、周报、通知及相关仓库层和任务。支付、订阅、结算业务排除；家长汇总中的学生资料授权属于本轮范围，其支付依赖在复现中被替换为空数据。
- 方法：调用链审查、现有禁网测试、真实 boto3 数值序列化/反序列化、Moto 本地 DynamoDB、合成 JWT/账号、公开依赖漏洞数据库查询。
- 没有调用生产 AWS、发送邮件、调用付费模型、执行部署或修改用户数据。结论针对该源代码版本，不代表线上部署版本或线上事故已被确认。

## 问题清单

P1 表示应优先处理的隐私/认证缺陷；P2 表示确定的功能、可靠性或资源消耗问题。没有发现可证实的 P0。

| ID | 级别 | 问题 | 主要证据 |
|---|---|---|---|
| NP-01 | P1 | 撤销家长关系后，账号汇总仍返回学生资料与使用数据 | HTTP 200，返回撤销关系的学生邮箱及合成活动标记 |
| NP-02 | P1 | 周报通过旧 `parent_id` 信任已撤销关系 | Moto 存储的 `revoked` 关系仍通过报告学生解析 |
| NP-03 | P1 | 账号删除分支漏掉新家长关系行 | 两轮扫描后 `complete/quiescent`，仍残留两条 active 关系 |
| NP-04 | P1 | 登出没有使旧访问令牌在后端失效 | 完整验签路径：200 → logout 204 → 同令牌 200 |
| NP-05 | P2 | 上传校验直接调用带已知 DoS 缺陷的 PDF 解析器 | `pypdf==6.14.2`；4 MiB 合成输入触发探针的 6 秒解析超时 |
| NP-06 | P2 | 删除任务耗尽扫描预算后丢失游标 | 连续三轮均从 0 开始，后部删除命令始终未执行 |
| NP-07 | P2 | 新建家长关系无法进入周报流程 | 实际 `assign_link` 成功，但周报发现为空、学生解析拒绝 |
| NP-08 | P2 | DynamoDB 数值类型导致教师课程授权失败 | 同一 assignment：int 允许，Decimal 被拒绝为资源不存在 |
| NP-09 | P2 | 教师求助队列只扫描首批 50 行 | 首批无匹配、存在下一页时，仍返回空队列 |
| NP-10 | P2 | 学生对话列表丢弃索引后续页 | 首个过滤后空页导致已有对话不显示 |
| NP-11 | P2 | 伪造 JWT 的未知 kid 可逐请求触发 JWKS 外连 | 新鲜缓存 + 10 个无有效签名的 JWT = 11 次密钥抓取 |

### NP-01 — 家长汇总绕过关系授权

位置：`src/stoa/services/account_operations_service.py:74-100`，入口 `src/stoa/routers/parents.py:1377-1388`。

入口只检查调用者是家长。汇总遍历所有旧绑定，并将带 `parent_id` 的学生 profile 当作补充来源；没有检查绑定状态、反向行、学生有效状态。`_child_operation_row` 随即加载学生 profile 和使用汇总。即使绑定明确为 `revoked`，姓名、邮箱等仍进入响应。仅保留 profile 的旧 `parent_id`、删除两端正式关系也能复现。

复现：`test_revoked_parent_cannot_read_child_via_account_operations` 与 `test_profile_parent_id_alone_does_not_authorize_operations`。两个真实 HTTP 请求均返回 200 和本应排除的学生资料；只有身份和外部依赖被替换，汇总实现未被替换。

建议：复用现有当前关系授权逻辑，先获得允许访问的学生集合，再读取资料和活动。管理员恢复界面若需要展示坏关系，应与家长可见投影分别授权。

### NP-02 — 周报仍认可已撤销的旧家长关系

位置：`src/stoa/services/report_service.py:636-661`、`src/stoa/jobs/weekly_reports.py:194-203`。

`_get_linked_student_profile` 只检查 profile 的 `parent_id`；明确标记 `parent_binding_status=revoked` 的学生仍被接受。定时发现也会把这种 profile 加回候选。正常账号删除 fence 只证明账号仍有效，不能证明家长仍获准接收该学生的报告。报告后续路径会将学生学习摘要发往该 parent 的邮箱。

复现：`test_revoked_parent_is_rejected_before_weekly_report_payload` 在 Moto 中写入真实 profile 后，没有得到预期拒绝。已审查后续生成/发送调用链；本轮没有发送邮件，也不声称生产已发生泄露。

建议：发现候选不等于授权。生成前和外部交付前分别校验当前有效家长关系，复用现有双向关系判断。

### NP-03 — 新家长关系未被账号删除分支处理

位置：`src/stoa/services/account_deletion_service.py:549-554`。

账号分支的 predicate 只接受 `PROFILE` 和旧 `parent_student_binding`，不接受当前关系系统写入的 `parent_student_link`。底层 `_targets_user` 已能找到新关系，但找到后又被分支过滤掉。两次扫描便被当作干净扫描，产生 `complete` 和 `quiescent=True`，同时保留 `PARENT#…/CHILD#…`、`STUDENT#…/PARENT#…` 两条带身份与关系信息的 active 行。

复现：`test_account_profile_deletion_cannot_finish_with_active_new_links` 使用真正的 `assign_link`、Moto 表和删除分支；profile 已删除的前提下，新关系两行仍在而分支报告完成。这是分支完成证明的反例，不是完整生产删除流程的验收。

建议：让新关系明确归属删除分支，处理两端记录并纳入完整性证明；补充真实分支/存储测试，不能只测试 `_targets_user` 能找到记录。关系写事务也应复用账号 fence，防止删除后并发写回。

### NP-04 — 登出后的 JWT 仍可访问后端

位置：`src/stoa/routers/auth.py:1013-1026`、`src/stoa/security/tokens.py:43-77`。

登出仅调用 Cognito `global_sign_out`。后端验证签名、有效期、客户端以及本地账号状态，不读取任何会话撤销状态；账号继续 active 时，原访问令牌继续通过。AWS 明确说明：被撤销的令牌仍可通过只验证签名和有效期的 JWT 库。[AWS token revocation 文档](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html)

复现：`test_logout_revokes_existing_token_at_protected_backend_route` 生成合成 RSA 签名 JWT，走真实 `get_actor`、验签和身份解析；已确认调用 provider 的登出接口。登出后同令牌仍得到 200。实际 Cognito 外连被替身替代，其撤销语义由官方文档核实。

建议：增加后端可验证的会话撤销事实，例如账号级撤销时间与 token 签发时间比较，或有界的会话/JTI 撤销存储；不能仅依赖前端删除令牌或 provider sign-out。

### NP-05 — PDF 入站校验发生在资源隔离之前

位置：`src/stoa/services/attachment_service.py:1648-1650`、`src/stoa/services/file_validation_service.py:162-176`、`requirements.txt:395`。

锁定的 `pypdf==6.14.2` 受 `CVE-2026-82398` 影响：`read_until_whitespace` 逐字节拼接造成超线性运行时间。上传完成时在 API 进程直接构造 `PdfReader` 并访问页树。后续文本提取虽有 `document_parser_worker`，这个前置步骤没有使用它，所以后面的 CPU/墙钟限制无法保护上传校验。

离线探针调用实际 `validate_uploaded_file`，使用有效 PDF 外壳和超长数字对象头；65,770 字节输入在解析阶段约 3.06 秒后拒绝，4,194,540 字节输入在解析阶段被额外施加的 6 秒 SIGALRM 终止。二者都低于 50 MiB 文件上限。总进程耗时包含较慢的模块加载，不能当作生产延迟；首次 6 秒全进程探针受启动耗时影响，未用于结论。

建议：升级到覆盖所列 PDF 公告的版本，并将入站 PDF 结构校验也纳入现有资源隔离边界；不需要再造一套解析器。[上游非空白输入公告，修复于 6.15.0](https://github.com/py-pdf/pypdf/security/advisories/GHSA-fc8x-2rww-xw9m)；[XForm 提取公告，修复于 6.16.1](https://github.com/py-pdf/pypdf/security/advisories/GHSA-763m-79hh-57f2)。后者的提取路径已有隔离缓解，未声称它能突破隔离。

### NP-06 — 删除发现每轮重新扫描同一前缀

位置：`src/stoa/jobs/account_deletion.py:32-39,78-79,109-111`。

每轮从 `cursor=None` 开始，最多 100 页。默认每页至多读取 25 行，且匹配命令越多，后续页读取量越小。耗尽预算时只增加 `retryable`，不持久化或返回游标。稳定表布局下，前约 2500 个评估项之后的命令可能一直不被发现，尤其影响路由后台回调丢失后的恢复。

复现：`test_deletion_sweeps_eventually_reach_commands_beyond_scan_budget` 放置 2600 条无关行，再放删除命令；三轮共 300 次 scan，起点均为 0，最远起点 2475，没有执行命令。[DynamoDB 的 Limit 在 FilterExpression 之前生效](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html)。

建议：保留跨轮游标，或复用可按待处理状态查询的发现机制，并明确重扫周期；只保留“还有工作”的计数不提供进展保证。

### NP-07 — 新家长关系无法生成周报

位置：`src/stoa/jobs/weekly_reports.py:157-169`、`src/stoa/services/report_service.py:657-661`。

当前 `assign_link` 写入 `parent_student_link`，不再把单一家长覆盖到学生 profile。但周报只扫描旧 `parent_student_binding` 和 profile.parent_id。新合法关系既不会被定时发现，手动触发生成也会在学生解析时被拒绝。

复现：`test_new_admin_assigned_link_is_discovered_for_weekly_reports` 与 `test_new_admin_assigned_link_can_resolve_student_for_report`。Moto 中实际创建关系，`active_children` 确认可访问；周报候选仍为空，解析报 `student is not linked to parent`。

建议：通过当前关系服务发现和校验学生，同时保留经严格校验的旧关系兼容。该修正与 NP-02 需要一起测试，防止为兼容而扩大权限。

### NP-08 — 教师课程授权仍拒绝 Decimal 版本号

位置：`src/stoa/db/repositories/question_repo.py:603-617`、`src/stoa/security/authorization.py:980-990`。

repository 把版本转换为局部变量用于校验，却返回未被转换的原始 item。授权层接着要求 `isinstance(version, int)`。因此数据库读出的正常 Decimal 版本会被拒绝，而测试手写的 int 版本通过。

复现：`test_teacher_curriculum_assignment_survives_dynamodb_number_roundtrip`。同一 assignment 经 boto3 `TypeSerializer` → `TypeDeserializer` 后，真实 repository 返回 Decimal；同一 policy 从允许变为 `resource_not_found`。

建议：复用已有 `stored_int`，在可信读边界或授权判断中统一处理整数 Decimal；继续拒绝 bool、非整数及无效值。补存储往返测试。

### NP-09 — 教师队列的 50 是扫描行数，不是匹配题目数

位置：`src/stoa/routers/teachers.py:208-217`。

`Scan(Limit=50, FilterExpression=status=escalated)` 只检查首批最多 50 行，却直接返回其 Items 并丢弃 LastEvaluatedKey。账号、活动、已完成问题都占扫描预算，因此即使存在等待老师的问题，也可能看到空队列；单表超过 50 行就可能触发。

复现：`test_teacher_queue_reaches_matching_question_after_empty_scan_page`。第一页无匹配但有游标，第二页有求助；实现只调用一次 scan 并返回空列表。

建议：复用已有分页扫描 helper，以匹配项数和显式扫描预算限制，耗尽预算时返回继续读取信息；无需先新增索引才能纠正语义。

### NP-10 — 对话列表丢弃共享索引的后续页

位置：`src/stoa/routers/conversations.py:169-177`。

查询共享 `GSI-StudentId` 后再过滤 conversation。其他带 student_id/created_at 的行也消耗一页容量；函数忽略 LastEvaluatedKey，所以老对话会被截断，过滤后的首个空页还会让全部对话暂时消失。

复现：`test_conversation_list_reaches_matching_row_after_filtered_gsi_page`。合法空页和游标之后还有 conversation，函数却只查询一次。这里是不同于教师队列的用户路径，需单独修复与验收。

建议：按现有 API 合约完整翻页，或增加有界 continuation API；不能把分页后的局部空结果解释为整个对话集合为空。

### NP-11 — 未知 kid 绕过新鲜 JWKS 缓存造成外连放大

位置：`src/stoa/security/jwks.py:78-98,101-111`。

缓存仅对已有 kid 生效。任何已允许 issuer 下的未知 kid 都触发抓取；single-flight 只合并同时发生的请求，没有 issuer 级刷新冷却或有界负缓存。攻击者无需有效签名，伪造 JWT 的头和 issuer 即能触发 HTTPS 请求。

复现：`test_unknown_jwt_kids_do_not_force_one_external_fetch_per_request`。先预热缓存，再发 10 个假签名、不同 kid 的 JWT，transport 总共被调用 11 次。未进行真实网络攻击；证明的是后端外连触发次数和缓存缺口。

建议：在现有 provider 内加 issuer 级最小刷新间隔/有界负缓存，保留已知密钥轮换和过期恢复的路径；与已存在的 rotation 测试共同验收。

## 测试与依赖审计

现有测试选择排除了文件名包含 billing、checkout、subscription、entitlement、allowance、stripe、payment、plan_identity、free_trial、usage_ledger 的文件。非支付流程会共用部分服务，因此这是业务范围排除，不声称运行时完全没有导入相关模块。

| 执行 | 结果 | 解释 |
|---|---|---|
| 首轮 133 个测试文件 | collection error | `test_infra_workflow_contract.py` 找不到相邻规范 infra 根目录 |
| 跳过该收集阻塞的首次执行 | 被用户中断，无最终结果 | 原始输出已保留，不计作通过 |
| 重新确认旧进程终止后运行 132 个文件 | **2979 passed, 32 failed, 5 skipped** | 143.76 秒；32 项都在 release/formal gate 的默认跨仓库根路径解析失败 |
| 新增离线回归规格 | **12 failed** | 每项在预期断言或明确的业务拒绝点失败，复现上述 10 项缺陷；不是已修复测试 |
| PDF 受限子进程探针 | 4 MiB 样本在解析阶段超时 | 探针施加的墙钟/CPU 上限保护本机；没有在服务环境测试 |
| PyPI 依赖公告查询 | 38 个非支付应用依赖，5 包，13 条去重公告 | 原始 pip-audit 报 20 条，包含重复记录，未重复计算 |

依赖版本在 requirements、uv.lock 和当前 venv 中交叉核对。`anyio 4.13.0` 有 2 条公告，`cryptography 49.0.0` 有 1 条，`ecdsa 0.19.2` 有 1 条，`pyasn1 0.6.3` 有 3 条，`pypdf 6.14.2` 有 6 条。NP-05 给出已确认可到达的 PDF 校验路径。其他公告的 IDNA、进程池、PKCS7 或 ASN.1 不可信输入前提，不能从包存在就推断可被利用。

`ecdsa` 的现有例外基于 RS256-only 边界，未将其作为新可利用漏洞；但是例外已于 **2026-08-18 09:00 UTC** 到期，当前日期校验会拒绝该账本。需要重新处理依赖门禁，不能沿用历史通过结论，也不应未经评估简单延长例外。

## 交付物与复现

证据目录：`/Volumes/Codex-Workspace/live/home/zhdeng/stoa-backend/.scratch/nonpayment-audit-20260921/`。

- `test-selection.json`：现有测试选择与排除清单。
- `baseline.log`、`baseline-without-infra-collection.log`：首次收集失败和中断证据。
- `baseline-resumed.log`、`baseline-resumed.xml`：完整基线执行与失败详情。
- `test_audit_regressions.py`、`regressions-expanded.log`：12 个预期应通过但当前失败的回归规格及结果。
- `pdf_validation_probe.py`、`pdf-validation-results-with-startup.json`：带启动阶段区分的 PDF 探针。
- `dependency-pins.txt`、`dependency-audit.json`、`dependency-audit.log`：公开数据库查询输入/原始结果。
- `dependency-exception-validation.json`：当前时间下对既有依赖例外的拒绝结果。
- `manifest.json`：报告与本轮证据的 SHA-256、审计版本和现有测试失败分组。

从仓库根目录运行（预期退出码 1，复现缺陷）：

```bash
env -u AWS_PROFILE AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
AWS_SESSION_TOKEN=testing AWS_EC2_METADATA_DISABLED=true \
AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null \
.venv/bin/python -m pytest -q --tb=short --disable-socket --allow-unix-socket \
  .scratch/nonpayment-audit-20260921/test_audit_regressions.py
```

PDF 探针：

```bash
PYTHONPATH=src .venv/bin/python \
  .scratch/nonpayment-audit-20260921/pdf_validation_probe.py
```

## 建议处理顺序与限制

先统一家长关系的当前授权和生命周期清理（NP-01/02/03/07），再补会话撤销（NP-04）；随后处理 PDF 依赖与前置隔离、删除游标、数值类型和分页。优先复用现有关系服务、`stored_int`、分页 helper 和 parser worker，避免并行实现另一套规则。

本轮完成源码审计与局部离线反例，没有修复、提交、推送审计材料或部署。没有对生产、完整跨仓库 release gate、整套前端/infra/mobile 或所有可能并发时序作通过声明。既有测试大量通过说明被测试的路径成立，不能替代上述反例覆盖；本报告也不构成“除此之外没有缺陷”的保证。
