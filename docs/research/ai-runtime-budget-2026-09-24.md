# AI 生成运行时预算：平台上限与三仓现状（#18 研究）

日期：2026-09-24
票据：`.scratch/audit-fix-plan-20260924/issues/07-runtime-budget-research.md`（供票据 08 决策）
GitHub：[stoasystem/stoa-backend#18](https://github.com/stoasystem/stoa-backend/issues/18)

本文只列事实，不做决定、不做推荐。每条事实带官方文档链接或 `路径:行号`。
核对的修订：

- 后端：本 worktree `ef0827c9`（`main` 之后无业务改动；issue 审计时为 `5a6ba852`，下文引用的行号以 `ef0827c9` 为准）。
- infra：远端 `stoasystem/stoa-infra` `main` = `c0d79df903e74dded11aed340ef7b1a6b741b577`（通过 `gh api` 读取，行号来自远端文件 `nl -ba`）。
- 前端：远端 `stoasystem/stoa-frontend` `830e1b7ea3c3f43697b717eeba84d13a89fb1d83`（`useStreamingChat.ts` 用本地副本 `.scratch/ai-audit-20260924/remote/useStreamingChat.ts`，其余文件通过 `gh api ...?ref=830e1b7` 读取）。

没有实测的延迟数字一律写"未测"。

---

## 1. 平台上限（AWS 官方文档）

### 1.1 API Gateway 集成超时

| 项 | 数值 | 能否提高 | 来源 |
|---|---|---|---|
| HTTP API（v2）最大集成超时 | 30 秒 | **否** | [HTTP API quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html)："Maximum integration timeout \| 30 seconds \| No" |
| HTTP API 载荷上限 | 10 MB | 否 | 同上 |
| REST API（v1）Regional / Private 集成超时 | 50 ms – 29 s | **是**（Service Quotas 代码 `L-E5AE38E3`） | [REST API execution quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-execution-service-limits-table.html) |
| REST API Edge-optimized 集成超时 | 50 ms – 29 s | 否 | 同上 |
| REST API 提高后的上限 | 文档未给数值 | — | 同上脚注："might require a reduction in your Region-level throttle quota" |
| REST API 空闲连接超时 | 310 秒 | 否 | 同上 |

- REST API 超过 29 秒的公告（2024-06-04）：[What's New](https://aws.amazon.com/about-aws/whats-new/2024/06/amazon-api-gateway-integration-timeout-limit-29-seconds/)，仅限 Regional 与 Private REST API，并可能要求降低账户级限流。
- 现有 infra 用的是 **HTTP API v2**（见 §2.1），30 秒不可提高。

### 1.2 Lambda 函数上限

- 函数超时上限：900 秒（15 分钟）。来源：[Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)。
- 内存：128 MB – 10,240 MB。同上。
- 同步调用载荷：请求/响应各 6 MB；流式响应 200 MB。同上。
- 流式带宽：前 6 MB 不限速，之后 2 MBps。同上。

### 1.3 Lambda 响应流式传输（response streaming）

来源：[Configuring a Lambda function to stream responses](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html)

- 支持的调用路径：**Function URL**（`InvokeMode=RESPONSE_STREAM`）、**`InvokeWithResponseStream` API** 直调、以及 **API Gateway 代理集成**（内部走 `InvokeWithResponseStream`，只对 REST API 有效，见 §1.4）。
- 该页未提及 ALB。2023-04 的 AWS 博客写明 ALB 目标集成不支持 chunked 传输（[博客](https://aws.amazon.com/blogs/compute/introducing-aws-lambda-response-streaming/)，二手来源）；Lambda Web Adapter 用户指南也写 "ALB does not support streaming"（见下）。
- 载荷上限 200 MB；前 6 MB 不限速，之后 2 MBps。
- 运行时：**仅 Node.js 托管运行时原生支持**（`awslambda.streamifyResponse()`，[写法](https://docs.aws.amazon.com/lambda/latest/dg/config-rs-write-functions.html)）。**Python 需要自定义运行时或 Lambda Web Adapter**（原文："For other languages, including Python, you can use a custom runtime ... or use the Lambda Web Adapter"）。自定义运行时协议见 [runtimes-custom](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-custom.html#runtimes-custom-response-streaming)。
- VPC 内的 Function URL 不支持流式。
- 客户端断开后流式调用**不会中止**，仍按函数超时计费——文档提醒 "exercise caution when configuring long function timeouts"。
- Function URL 两种模式（[config-rs-invoke-furls](https://docs.aws.amazon.com/lambda/latest/dg/config-rs-invoke-furls.html)）：`BUFFERED`（默认，6 MB）与 `RESPONSE_STREAM`（200 MB）。CloudFormation 属性 `AWS::Lambda::Url` → `InvokeMode`。
- **文档没有单独给出 Function URL 的最大时长**；唯一的上限是函数超时 900 秒。不要把"Function URL 15 分钟"当成独立条目引用。
- Lambda Web Adapter（Python/FastAPI 的流式路径，GitHub/awslabs 来源，非 docs.aws.amazon.com）：环境变量 `AWS_LWA_INVOKE_MODE=response_stream`，需与 Function URL 的 invoke mode 一致；"Response streaming works with Lambda Function URLs and API Gateway. ALB does not support streaming."；开启流式时不支持压缩。来源：[LWA response streaming](https://aws.github.io/aws-lambda-web-adapter/configuration/response-streaming.html)、[README](https://github.com/awslabs/aws-lambda-web-adapter)（列有 "FastAPI with Response Streaming" 示例）。

### 1.4 API Gateway 对流式响应的支持

- **REST API 支持，HTTP API 不支持**。来源：[Response transfer mode](https://docs.aws.amazon.com/apigateway/latest/developerguide/response-transfer-mode.html)："Response streaming is only supported for REST APIs."
- 仅 `HTTP_PROXY` / `AWS_PROXY` 集成类型；最长可流式 15 分钟（`timeoutInMillis` 最大 900000，[配置页](https://docs.aws.amazon.com/apigateway/latest/developerguide/response-streaming-http.html)）；空闲超时 Regional/Private 5 分钟、Edge 30 秒；前 10 MB 不限速，之后 2 MB/s；不支持缓存、内容编码、VTL 响应转换、请求流式；额外计费。
- Lambda 集成细节：[response-transfer-mode-lambda](https://docs.aws.amazon.com/apigateway/latest/developerguide/response-transfer-mode-lambda.html)——集成 URI 走 `.../response-streaming-invocations`，输出格式为元数据 JSON + 8 个空字节分隔符 + 载荷；[Lambda 配置页](https://docs.aws.amazon.com/apigateway/latest/developerguide/response-streaming-lambda-configure.html)写 "Use the latest Node.js runtime."
- 公告日期：2025-11-19，[What's New](https://aws.amazon.com/about-aws/whats-new/2025/11/api-gateway-response-streaming-rest-apis)。
- 含义：要经 API Gateway 流式，需从 HTTP API v2 换成 REST API v1；现有 infra 是 HTTP API v2（§2.1）。

### 1.5 Function URL 鉴权、CORS、限流

来源：[Function URLs 配置](https://docs.aws.amazon.com/lambda/latest/dg/urls-configuration.html)、[调用](https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html)

- AuthType 只有 `AWS_IAM` 或 `NONE`；`AWS_IAM` 时每个请求需 SigV4 签名，权限 `lambda:InvokeFunctionUrl` + `lambda:InvokeFunction`。**没有 JWT/Cognito 授权器**——现有 HTTP API 的 Cognito JWT 授权（§2.1）在 Function URL 上没有等价物，鉴权要落回应用层。
- 支持 CORS 配置（AllowOrigins / AllowMethods / AllowHeaders / ExposeHeaders / AllowCredentials / MaxAge）。
- 端点格式 `https://<url-id>.lambda-url.<region>.on.aws`，仅公网可达。
- 请求载荷与 API Gateway payload format 2.0 相同（Mangum 可解析同一格式，此为推论，未在本仓验证）。
- 限流：RPS 上限为 reserved concurrency 的 10 倍，超出返回 429。

### 1.6 CloudFront 前置 Function URL

- OAC（Origin Access Control）：Function URL 必须 `AuthType=AWS_IAM`；给 `cloudfront.amazonaws.com` 加 `lambda:InvokeFunctionUrl` 与 `lambda:InvokeFunction` 的资源策略并限定 `source-arn` 为分发 ARN；**PUT/POST 必须带 `x-amz-content-sha256` 载荷哈希**（Lambda 不支持未签名载荷）；Lambda 控制台不能编辑该策略，需 CLI/CFN。来源：[Restricting access to a Lambda function URL origin](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-lambda.html)。
- 源域名格式 `{function-URL-ID}.lambda-url.{region}.on.aws`；不用 OAC 则 AuthType 必须为 `NONE`。来源：[Using Lambda function URLs as origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistS3AndCustomOrigins.html#concept_lambda_function_url)。
- 源响应超时（response timeout）是**包间空闲超时**而非总时长：默认 30 秒，配额范围 1–120 秒，可申请提高；keep-alive 默认 5 秒。另有可选的 "response completion timeout"，不设则不限总时长。来源：[Origin settings](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesOrigin.html#DownloadDistValuesOriginResponseTimeout)、[CloudFront quotas](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cloudfront-limits.html)。
- CloudFront 支持源返回 `Transfer-Encoding: chunked`，边缘收到即转发给客户端（[custom origin 行为](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/RequestAndResponseBehaviorCustomOrigin.html#ResponseCustomTransferEncoding)）。API Gateway 的流式文档也写可通过提高 CloudFront 响应超时获得大于 30 秒的空闲超时（[response-transfer-mode](https://docs.aws.amazon.com/apigateway/latest/developerguide/response-transfer-mode.html)）。

### 1.7 Bedrock 侧

- `InvokeModelWithResponseStream`（`POST /model/{modelId}/invoke-with-response-stream`）与 `ConverseStream` 存在；错误码含 `ModelTimeoutException`（HTTP 408，"Processing time exceeded the model timeout length."，未给数值）。来源：[API 参考](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModelWithResponseStream.html)。
- boto3 提供 `BedrockRuntime.Client.invoke_model_with_response_stream` / `converse_stream`（[boto3 文档](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/invoke_model_with_response_stream.html)）。本仓 boto3/botocore 版本 1.43.16（`uv.lock:90-91`, `uv.lock:117-118`）。
- **Bedrock 文档没有列出最大调用时长配额**，只有 TPM/RPM/每日 token 等吞吐配额。来源：[quotas-runtime](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-runtime.html)、[general reference](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)。
- 模型端到端生成延迟：**未测**。

---

## 2. infra 现状（远端 stoa-infra `c0d79df9`）

### 2.1 API Lambda 与 API Gateway

- 构造 `lambda_.Function(self, "StoaApiFunction")`，`function_name="stoa-api"`：`stacks/api_stack.py:61-110`。
  - runtime `PYTHON_3_12`（`:65`），`ARM_64`（`:66`），handler `stoa.main.handler`（`:67`）。
  - **memory_size 1024**（`:69`），**timeout `Duration.seconds(29)`**（`:70`）。
  - 未设 ephemeral storage、reserved concurrency；production alias 明确不开 provisioned concurrency（`:238-249`）。无 Layer。
- 环境变量 `BEDROCK_MODEL_ID="eu.anthropic.claude-sonnet-4-6"`（`:101`），与后端默认值一致（§5）。声明块与线上快照合并（`:85`, `:107`；`stacks/lambda_environment.py:60-79`）。
- Bedrock IAM：`bedrock:InvokeModel`、`bedrock:InvokeModelWithResponseStream`、`bedrock:CountTokens`，资源 `*`（`api_stack.py:363-370`）。
- API Gateway：**`apigwv2.HttpApi`（HTTP API v2）**，`api_name="stoa-api"`（`:538-547`）。集成 `HttpLambdaIntegration` 指向 **production alias**（`:594-596`），**未显式设 integration timeout 与 payload_format_version**（CDK 默认）。Cognito `HttpJwtAuthorizer`（`:527-536`）挂在 `/{proxy+}`（`:651-662`）。
- **没有自定义域名**（`api_url = http_api.url`，`:668-669`）；**API 前面没有 CloudFront**——仅有的 CloudFront 分发是 SPA（`stacks/frontend_stack.py:18, 61-113`，S3 源）。

### 2.2 已有的异步基础设施

| 资源 | 有/无 | 位置 |
|---|---|---|
| SQS FIFO 队列 `stoa-teacher-escalation.fifo`（可见性 60 秒，DLQ maxReceive 3） | 有 | `stacks/notification_stack.py:35-43`，DLQ `:25-32` |
| **SQS 触发的 Lambda（event source mapping）** | **无**——全仓没有 `SqsEventSource` / `add_event_source`；API 仅 `grant_send_messages`（`api_stack.py:117`），队列 URL 作为 `TEACHER_QUEUE_URL`（`:95`） | — |
| Lambda Function URL | **无** | — |
| EventBridge Rule（`aws_events`） | 无 | — |
| **EventBridge Scheduler（`aws_scheduler.CfnSchedule`）** | 有，3 条 | 见 §2.3 |
| Step Functions | 无 | — |
| DynamoDB Streams | 无 | `stacks/database_stack.py:21-33` 未配置 |
| Scheduler DLQ（普通 SQS） | 有，3 个 | `api_stack.py:390-395, 430-435, 468-473` |

### 2.3 现有 job Lambda 的声明与触发

四个函数共用同一份 `code=lambda_code` 资产（`api_stack.py:68, 126, 167, 205`），都是 `PYTHON_3_12` + `ARM_64`。

| 函数 | handler | 内存 | 超时 | 触发 | 声明位置 |
|---|---|---|---|---|---|
| `stoa-weekly-report` | `stoa.jobs.weekly_reports.handler` | 1024 | 15 min | Scheduler `cron(0 6 ? * MON *)` Europe/Zurich（`:444-467`）；也可由 API alias 直接 invoke（`:303`） | `:119-143` |
| `stoa-dispatch-reconciler` | `stoa.jobs.dispatch_reconciler.handler` | 512 | 5 min | Scheduler `rate(5 minutes)`（`:484-506`） | `:160-191` |
| `stoa-account-deletion` | `stoa.jobs.account_deletion.handler` | 1024 | 10 min | Scheduler `rate(5 minutes)`，input `{"source":"stoa.scheduler","job":"account_deletion","limit":25}`，重试 maxAge 3600 s / 3 次，DLQ（`:404-428`） | `:198-226` |

- Scheduler 目标一律是 **production alias**，不是 `$LATEST`（`tests/test_release_topology.py:313-341` 有断言）。
- **infra 里没有任何名为 teacher-escalation 的 Lambda**；后端的 `stoa.jobs.teacher_escalation.handler`（§3.4）在 infra 中没有对应函数、也没有 SQS 消费者。
- 版本/别名：API 与 weekly-report 有 `staging` + `production` 别名，另两个只有 `production`（`:231-278`）。GitHub 部署角色可 `UpdateFunctionCode/PublishVersion/UpdateAlias` 这四个函数（`:310-358`）。

### 2.4 打包方式：`scripts/build_lambda_dist.py` 能否再装一个函数

- infra 侧：`lambda_.Code.from_asset(str(lambda_dist.path), asset_hash=..., asset_hash_type=CUSTOM)`（`api_stack.py:54-58`），路径由 `stacks/lambda_dist_guard.py:22-69` 解析为 `<infra 父目录>/stoa-backend/dist`，synth 时运行 `stoa-backend/scripts/build_lambda_dist.py --verify-only` 并读 `dist/.stoa-build-manifest.json` 的 `cdk_asset_hash`（`:43-56`, `:65-69`）。无 Docker bundling、无 Layer。
- 后端侧：一份 zip 装全部 `src/stoa`（`scripts/build_lambda_dist.py:468-475` `copy_source`，`:500-552` `build_dist`，`:554-588` `zip_dist`）。`EXPECTED_HANDLERS` 只列了三个 handler——`stoa.main.handler`、`stoa.jobs.weekly_reports.handler`、`stoa.jobs.account_deletion.handler`（`:46-50`）；`require_handlers`（`:168-174`）与 `boot_smoke`（`:301-352`）按这张表做导入冒烟。`stoa.jobs.dispatch_reconciler.handler` 虽已部署但不在表里，说明这张表不是"已部署函数清单"而是验证集合。
- 部署：`.github/workflows/deploy-production.yml:105-108` 构建并校验 zip，`:125-150` 对 `stoa-api stoa-weekly-report stoa-dispatch-reconciler stoa-account-deletion` 四个函数名循环 `aws lambda update-function-code`，`:160-180` 把 `production` 别名指向新版本。函数名列表写死在 workflow 里。
- 结论性事实：新增一个函数**不需要改打包方式**——同一 zip 已包含所有模块；需要改的是 (a) infra 新增 `lambda_.Function` + 触发器 + IAM，(b) 后端 workflow 的函数名循环，(c) 可选地把新 handler 加进 `EXPECTED_HANDLERS`。

---

## 3. 后端现状（`ef0827c9`）

### 3.1 请求入口与运行时形态

- Lambda 入口 `handler = Mangum(app, lifespan="off")`（`src/stoa/main.py:126`）；README 写明 "API Gateway HTTP API"（`README.md:8`）。
- 路由：`POST /conversations/{conv_id}/messages`（`src/stoa/routers/conversations.py:1412`）与 `POST /conversations/{conv_id}/messages/stream`（`:1449`），二者都调用同一个 `_execute_message_command`（`:1430-1434`, `:1473-1477`, 定义 `:1830`）。
- `stream_message` 的顺序：**先同步跑完整个 `_execute_message_command`**（生成、持久化、结算全部结束，`:1473-1487`），**再**构造 `StreamingResponse`，把已完成的 `assistant_msg.content` 切成 100 字符的 `message_delta` 回放（`:1495-1528`）。docstring 自述 "API Gateway buffers the full response ... this is pseudo-streaming"（`:1462-1466`）。所以首个 SSE 字节在答案完全生成之后才可能发出。
- 常量：`_AI_LEASE_SECONDS = 120`（`:1531`），`_AI_INVOCATION_DEADLINE_SECONDS = 90`（`:1532`），`_MESSAGE_POLL_ATTEMPTS = 20`、`_MESSAGE_POLL_SECONDS = 0.05`（`:1529-1530`，即重放等待最多约 1 秒，`:1736-1756`）。
- `_generate_title`（`:1111`）会调 Bedrock，但全文件只有定义没有调用点；`_adopt_question_as_title`（`:1245-1265`）只做字符串截取，不调模型。请求内只有一次模型调用。

### 3.2 message command 生命周期（状态机）

命令行的 key：`message_command_key(conversation_id, idempotency_key)`（`src/stoa/db/repositories/attachment_repo.py:425`）；`command_id = uuid5(NAMESPACE_URL, "stoa.conversation.send.v1:{conv_id}:{idempotencyKey}")`（`conversations.py:1887-1889`），学生/助手消息 id 由 `command_id` 派生（`:1890-1891`）。

状态与分类（`attachment_repo.classify_message_command`，`:910-983`）：

| `status` | 分类 | 备注 |
|---|---|---|
| `claimed` | `CLAIMED`，`expires_at` 到期则 `EXPIRED` | `expires_at = now + 172800`（`conversations.py:1919-1923`） |
| `message_committed` | `RESUME` | 学生消息已落库、AI 未开始 |
| `ai_running` | `expiresAt <= now` → `RESUME`，否则 `LEASE_HELD` | `expiresAt` 即 120 秒 lease（`attachment_repo.py:950-955`） |
| `completed` | 有 `result_json` → `COMPLETED`，否则 `RETRYABLE` | |
| `rejected` / `terminal_failed` / `expired` | `REJECTED` / `TERMINAL` / `EXPIRED` | |

请求内的阶段顺序（`_execute_message_command`，`conversations.py:1830-2471`）：

1. Stage A（依赖注入）：读现有命令并分类；fingerprint 不同 → 409 `MESSAGE_IDEMPOTENCY_CONFLICT`（`:756-786`）。
2. `LEASE_HELD` → `_wait_for_message_command` 轮询最多 20×50 ms，仍未完成则抛 `MESSAGE_IN_PROGRESS`（`:1727-1763`, `:1869-1876`）。
3. 新命令：读历史（`:1965-1969`）、算 quota（`:1971-1973`）、准备附件（`:2039-2053`）、取 entitlement 并写入 allowance 字段（`:2054-2063`）、`claim_message_command_and_quota` 事务（`:2064-2076`，状态 → `claimed`）。
4. `bind_message_attachments` 事务把**学生消息落库**（`:2120-2130`；状态 → `message_committed`）。
5. 补齐 allowance 字段（`:2199-2217`），读 memory context（`:2222`）。
6. **`claim_message_ai_lease`**（`:2226-2238`）：`expires_at = now + 120`；仓库侧条件是 `message_committed`，或 `ai_running` 且 `expiresAt <= now` 且 `attempt < 3`（`attachment_repo.py:2755-2760`, `:2799-2803`）。状态 → `ai_running`，`attempt += 1`。未拿到且 `attempt >= 3` 时 `mark_message_command_terminal` → `terminal_failed`（`conversations.py:2245-2272`；`attachment_repo.py:3123-3166`，条件 `status=ai_running AND attempt>=3`）。
7. lease 之后才做：S3 附件正文提取（`:2288-2312`）、locale、**`ai_deadline = time.monotonic() + 90`（`:2315`）**、构造 `_ConversationAllowanceBedrockClient(command)`（`:2317`）。
8. `ai_service.get_ai_answer(..., deadline_monotonic=ai_deadline, client=allowance_client, on_step=_publish_generation_step(...))`（`:2320-2335`）。
9. 异常路径（`:2366-2395`，`except Exception as exc:` 在 `:2368`）：若已产生 allowance 元数据则观测并回补额度；发 `conversation_ai_failed` 事件；抛 `UPLOAD_SERVICE_UNAVAILABLE`。**这段不改命令状态**——命令停留在 `ai_running`，直到 120 秒 lease 自然到期，下一次同 key 请求才会以 `RESUME` 重新拿 lease。
10. 成功路径：`renew_message_ai_lease`（`:2399-2411`）→ `complete_message_command` 事务写助手消息与 `result_json`（`:2457-2471`；状态 → `completed`）→ `_finalize_message_allowance`。

Lambda 在第 8 步被硬终止时，第 9、10 步都不会执行：学生消息（第 4 步）和 allowance 预留（wrapper 内，见 §3.5）已写，助手消息与 `result_json` 未写，命令 `ai_running`、lease 120 秒——与 issue #18 的复现表一致。

### 3.3 进度轮询端点

- `GET /conversations/{conv_id}/generation`（`conversations.py:1392-1409`）返回 `GenerationProgressResponse{conversationId, steps: list[str], updatedAt: str}`（`:1384-1389`）。只返回已完成的 step 文本，**不返回命令状态、不返回 assistant message id、不返回终态**。
- 数据源：单行 `PK=CONV#{id}, SK=GENERATION`（`attachment_repo.py:521-522`），`record_generation_progress` 每次整表覆写 `steps`、`updated_at`、`expires_at`（`:525-563`，best-effort，异常吞掉返回 False）；`read_generation_progress` 强一致读，owner 不符返回空（`:565-590`）。
- 写入方：`_publish_generation_step`（`conversations.py:1182-1201`）作为 `on_step` 回调，在流式解析每完成一个 step 时写一次；TTL `GENERATION_PROGRESS_TTL_SECONDS = 3600`（`:1179`）。
- 该行是按 conversation 存的，不是按命令存的；前端靠 `updatedAt >= askedAt` 区分上一题的 step（§4）。
- **没有** "按 idempotencyKey 查命令状态" 的 GET 端点；`conversations.py` 全部路由见 `:1157, 1268, 1341, 1392, 1412, 1449`。

### 3.4 两个异步命令的继续模式

**teacher escalation（SQS 消费者形态）**

- 生产者：`POST .../escalate` 的 docstring "Escalate a question to a human teacher via SQS FIFO queue"（`src/stoa/routers/questions.py:1688`），末尾调 `notify_service.enqueue_teacher_request(...)`（`:1821`）。
- `enqueue_teacher_request` 只发不透明坐标 `{operation_id, question_id, generation}`，`sqs.send_message(QueueUrl=settings.teacher_queue_url, MessageGroupId=operation_id, ...)`（`src/stoa/services/notify_service.py:20-46`）；`teacher_queue_url` 配置项（`src/stoa/config.py:376`）。
- 消费者：`src/stoa/jobs/teacher_escalation.py:73-78` 的 `handler(event, _context)` 遍历 `event["Records"]`；`consume_message`（`:34-70`）解 body、按 `generation` 校验账户围栏、调 `teacher_dispatch_service.dispatch_question`。`_record_body` 同时接受 Lambda 事件源的 `body` 与 `receive_message` 的 `Body`（`:16-31`）。
- **infra 中没有这个函数，也没有 SQS event source mapping**（§2.2、§2.3）；`EXPECTED_HANDLERS` 也没列它（§2.4）。即：代码写成了 SQS 触发形态，但未部署为消费者。

**account deletion（Scheduler 扫描 + 请求内即时继续）**

- 定时扫描：`handler(event, _context)` → `run_pending_deletions(limit=event["limit"])`（`src/stoa/jobs/account_deletion.py:140-143`）。`run_pending_deletions` 用 `scan_pending_deletion_commands` 分页找命令（`:36-79`），每条 `claim_deletion_command(lease_owner=uuid4, lease_expires_at=now+2min)` 后 `worker.continue_command(claim)`（`:84-106`），返回 `DeletionJobSummary{discovered, claimed, continued, retryable}`（`:15-20`）。
- 请求内继续：`continue_deletion_command(command_id)` 是 async，拿 2 分钟 lease 后 `asyncio.to_thread(worker.continue_command, claim)`，任何异常静默返回并留给定时扫描（`:115-137`）。
- 触发：EventBridge Scheduler `rate(5 minutes)`，目标 `stoa-account-deletion` production alias，input 带 `limit=25`（§2.3）。
- 同类型还有 `stoa.jobs.dispatch_reconciler.handler`（`src/stoa/jobs/dispatch_reconciler.py:19-47`）：无入参、直接调 `teacher_dispatch_service.reconcile_dispatches()`，Scheduler 每 5 分钟。

### 3.5 Bedrock 客户端：直调 Config 与 allowance wrapper 的差异

**`get_ai_answer` 在 `client is None` 时**（`src/stoa/services/ai_service.py:606-616`）：

```python
read_timeout = max(1, min(90, int((remaining or 90) - 5)))
client = boto3.client("bedrock-runtime", region_name=settings.aws_region,
    config=Config(connect_timeout=5, read_timeout=read_timeout,
                  retries={"total_max_attempts": 1, "mode": "standard"}))
```

`Config` 来自 `botocore.config`（`:22`）。即 connect 5 秒、read 最多 85 秒、**不重试**。

**`_ConversationAllowanceBedrockClient`**（`conversations.py:572-677`）是生产路径唯一传入的 client（`:2317, 2333`）：

- 运行时 client 在 `invoke_model` 内懒建：`ai_service.boto3.client("bedrock-runtime", region_name=...)`，**没有 `config=`**（`:605-609`）——botocore 默认 connect/read 各 60 秒、standard 模式默认重试。
- 同一个 client 先做 **`count_tokens`**（`:621-627` → `bedrock_token_count_service.count_input_tokens`，`src/stoa/services/bedrock_token_count_service.py:255-276`，走 runtime `count_tokens` API，`:224-252`），再 **`reserve_token_allowance`**（`conversations.py:643-652`），最后 `invoke(**kwargs)`（`:666-669`）。
- `invoke_model_with_response_stream` 只是切换方法名后复用同一段 `invoke_model`（`:671-677`）。
- **wrapper 内没有任何 deadline 检查**；`count_tokens` 与 `reserve_token_allowance` 的耗时不受 `deadline_monotonic` 约束。

**deadline 检查位置**（相对 token 计数与首个流事件）：

1. `get_ai_answer` 入口：`remaining <= 0` 抛 `deadline_exceeded`（`ai_service.py:602-605`）。
2. 构造 body 后、调用 client 前再检查一次（`:631-632`）。
3. 之后进入 `client.invoke_model_with_response_stream(...)`（`_stream_ai_answer`，`:400-402`）——这一步内部先跑 wrapper 的 count_tokens + reserve + 真正的 invoke，**全程无检查**。
4. 下一次检查在 `for event in stream:` 循环体第一行（`:415-417`），即**收到首个流事件之后**才判 `deadline_exceeded`；之后每收一个事件判一次。
5. 非流式分支在 `invoke_model` 返回后检查（`:646-647`）。

所以：admission（count + reserve）可以把 90 秒耗尽后仍然启动生成；首 token 迟迟不来时，唯一能打断的是 botocore 的 read timeout——而 wrapper 建的 client 用的是默认 60 秒且可能重试，不是直调的 85 秒单次。

### 3.6 流式 API 的使用

- 只要传了 `on_step`，`get_ai_answer` 走 `_stream_ai_answer`（`ai_service.py:633-643`），调 `invoke_model_with_response_stream`（`:400-402`），逐 `content_block_delta` 累计文本、每完成一个 step 回调 `on_step`（`:415-436`）；在 `message_start` / `message_delta` 事件里收集 usage 与 stop_reason（`:437-444`）。
- 生产路径总是传 `on_step`（`conversations.py:2334`），所以**对 Bedrock 用的是流式 API**；但对客户端不是流式（§3.1）。
- `inventory_ai_invocation_classes` 把 `conversations.py:invoke_model_with_response_stream` 登记为 `USER_ALLOWANCE`（`ai_service.py:147-165`）。

---

## 4. 前端契约（stoa-frontend `830e1b7`）

文件：`src/hooks/chat/useStreamingChat.ts`（本地副本 `.scratch/ai-audit-20260924/remote/useStreamingChat.ts`），`src/services/chat/chatStreamApi.ts`，`src/services/api/httpClient.ts`，`src/lib/env.ts`。

- 主请求：`fetch(POST ${apiBaseUrl}/conversations/{id}/messages/stream)`，带 `Authorization: Bearer` 与 `Accept-Language`，**没有超时**，只有 `AbortSignal`（`chatStreamApi.ts:29-43`）。`!response.ok` 直接 `throw new Error("Streaming request failed with status ...")`（`:52-55`；`allowDemoFallback` 常量为 `false`，`env.ts:31`）。响应按 `\n\n` 切 SSE 事件解析（`:64-88`），事件类型 `message_start` / `message_delta` / `message_done` / `message_error`（`useStreamingChat.ts:67-133`）。
- **同步请求打开期间轮询**：`setInterval(1000ms)` 调 `getGenerationProgress(conversationId, signal)`（`useStreamingChat.ts:187-202`）→ `httpClient.get('/conversations/{id}/generation')`（`chatStreamApi.ts:129-136`）。读取字段 `steps`、`updatedAt`；若 `steps.length === 0 || updatedAt < askedAt` 忽略；否则把 assistant 占位消息的 `content` **整体替换**为 `steps.join('\n\n')`（`useStreamingChat.ts:191-199`）。轮询错误静默（`:201`）。`httpClient` 是 `axios.create({ baseURL, headers })`，**未设 timeout**（`httpClient.ts:21-26`）。
- 主请求成功：清轮询、`invalidateConversation()` 重取会话与列表、清空本地消息（`:223-228`）。
- **主请求失败**（`catch`，`:229-270`）：清轮询；若是用户主动 abort → assistant 标 `stopped`、student 标 `completed`；否则 student 消息标 `failed`（除非收到过 `message_error` 事件）、assistant 消息标 `failed` 并填错误文案。**失败后不再轮询、不查命令状态、不重取会话**。
- **重试是否复用 idempotencyKey：否。** 注释 "A retry is a new attempt and gets its own key."（`:14-15`）；`idempotencyKey: studentMessageId`，而 `studentMessageId = createLocalId('student')` 每次 `sendStreamingMessage` 重新生成（`:143`, `:204-211`）；`retryMessage` 删掉失败的本地消息后用不含 key 的 `retryPayload` 再调 `sendStreamingMessage`（`:289-305`）。因此重试在后端是**新命令**，会再次经过 quota 与 allowance 认领。
- API 源：`apiBaseUrl = runtimeConfig.api.origin`（`env.ts:10`），运行时配置校验 `api.origin` 为纯 origin（`runtimeConfig.ts:296-297`）。infra 侧 `ApiUrl` 输出即 HTTP API 默认 URL（§2.1）。

---

## 5. 模型配置

- `bedrock_model_id: str = "eu.anthropic.claude-sonnet-4-6"`（`src/stoa/config.py:335`，注释：EU 跨区域 inference profile），infra 环境变量同值（`api_stack.py:101`）。
- `bedrock_max_tokens: int = 2048`（`config.py:336`），作为请求体 `max_tokens`（`ai_service.py:619`），也是 allowance 预留的 `max_output_tokens`（`conversations.py:628-631`, `:648`）。
- `temperature 0.4`，`anthropic_version bedrock-2023-05-31`（`ai_service.py:617-623`）。
- 流式 API：对 Bedrock **用**（`invoke_model_with_response_stream`，§3.6）；对客户端**不用**（§3.1）。
- 延迟数字：首 token 时间、2048 token 完整生成时间、count_tokens 往返、DynamoDB 事务耗时——**全部未测**。issue #18 的复现用的是注入的单调时钟，不是真实读数。

---

## 6. 票据 08 可选的架构方向（只列举，不排序、不推荐）

### 方向 A：留在请求内，压缩预算

把整条命令压进 Lambda 剩余生命周期：更小的 `max_tokens`、以请求开始时刻而非 lease 之后起算的 deadline、admission 之后复检 deadline、给 wrapper 带上与直调相同的 `Config`、超时落成可恢复终态（如把 `ai_running` 改写为可重试状态并释放预留）。

- 涉及仓库：**stoa-backend**（`conversations.py`、`ai_service.py`、`attachment_repo.py`）。
- 可能涉及 **stoa-infra**：API Lambda `timeout` 若要接近 HTTP API 的 30 秒上限（`api_stack.py:70`）；HTTP API v2 的 30 秒不可提高（§1.1）。
- 前端契约不变（仍是同步 SSE 回放 + `/generation` 轮询）。
- 平台约束：单次 HTTP 往返上限 30 秒，含鉴权、历史读、附件提取、count_tokens、预留、生成、落库。

### 方向 B：生成搬到独立 worker，请求只返回命令状态，前端轮询终态

请求做到 `message_committed`（或拿到 lease）后即返回；生成由另一个 Lambda 完成（触发方式可选：SQS event source mapping、API Lambda 直接 `Invoke` 异步调用、Scheduler 扫描 `message_committed`/过期 `ai_running` 命令）；前端改为轮询命令终态。

- 涉及仓库：**stoa-backend**（拆 `_execute_message_command` 为"提交"与"生成"两段；新 `jobs/*.handler`；新的命令状态查询端点——现有 `/generation` 只有 steps，没有终态，§3.3；`EXPECTED_HANDLERS`、`deploy-production.yml` 函数名列表，§2.4）。
- **stoa-infra**（新 `lambda_.Function` 共用同一 zip；SQS 队列或 Scheduler 或 invoke 权限；Bedrock/CountTokens/DynamoDB IAM；worker 超时可到 900 秒，§1.2）。
- **stoa-frontend**（`useStreamingChat.ts` 的成功/失败分支目前假设同步拿到 SSE 终态，§4；重试换 key 的行为会产生新命令，§4）。
- 现成模式：Scheduler + lease 的 account-deletion 模式（§3.4）；SQS 消费者代码形态已有但未部署（§3.4、§2.2）。

### 方向 C：Lambda Function URL 流式响应，绕开 API Gateway

为对话生成单独开一个带 `InvokeMode=RESPONSE_STREAM` 的 Function URL（可选 CloudFront + OAC 前置），真正边生成边推 SSE。

- 涉及仓库：**stoa-backend**（Python 托管运行时不原生支持流式，需 Lambda Web Adapter 或自定义运行时，§1.3；`stream_message` 改为真流式，§3.1；Function URL 无 JWT 授权器，Cognito 校验需落到应用层或 CloudFront 层，§1.5）。
- **stoa-infra**（Function URL 或 REST API v1 的 `responseTransferMode=STREAM`，§1.4；可选 CloudFront 分发 + OAC + POST 载荷哈希要求，§1.6；LWA 层或镜像打包方式与现有 zip 方式不同，§2.4）。
- **stoa-frontend**（新的 API origin 或路径；SSE 解析器已存在，§4；轮询是否保留）。
- 平台约束：客户端断开不会中止 Lambda（§1.3）；CloudFront 响应超时是包间空闲超时、默认 30 秒、配额 1–120 秒（§1.6）；HTTP API v2 不支持流式，若走 API Gateway 需换 REST API（§1.4）。

### 与方向无关的共同事实

- wrapper 无 `Config`、admission 后不复检 deadline（§3.5）。
- 失败路径不改命令状态，`ai_running` 靠 120 秒 lease 到期解锁；3 次 attempt 后 `terminal_failed`（§3.2）。
- 前端重试换 key，后端视为新命令（§4）。
- 所有延迟数字未测（§5）。
