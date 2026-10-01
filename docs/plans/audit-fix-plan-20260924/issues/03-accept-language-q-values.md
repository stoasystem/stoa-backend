# Accept-Language 的权重与 q=0 应如何进入语言协商（#20）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: [#20](https://github.com/stoasystem/stoa-backend/issues/20)

## Question

`locale_from_accept_language` 丢掉 `;` 之后的一切并取第一个受支持语言，于是 `de;q=0, en;q=1` 选出德语并写进 OUTPUT LANGUAGE 指令。

要决定：
1. 协商规则：按 q 降序取第一个受支持语言，q=0 排除，等权按头部顺序稳定（RFC 9110 §12.4.2）。是否接受 `de-CH` 这类带地区的标签映射到 `de`。
2. 全部受支持语言都被 q=0 排除时回退到什么：现有 profile 偏好，还是 DEFAULT_LOCALE。
3. 单语言请求覆盖与缺头回退的既有对照必须保持；新增两条失败用例转绿。
4. 前端目前只发单一 `activeLanguage()`，这条不解释用户看到的语言不匹配，决议里要写清。

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

解析每项 `q`（缺省 1.0），非数字、NaN、超出 0–1 的项**跳过该项**（不抛请求异常、不恢复成默认权重），q≤0 剔除，按 q 降序、同权按头部顺序稳定排序，取第一个 `normalize_locale` 接受的（`de-CH → de`）；全部不可接受返回 None，走现有 profile 回退。
验收：`de;q=0,en;q=1 → en`、`fr;q=0.2,en;q=1 → en`、全 q=0 → None、同权保持顺序、`de-CH → de`、畸形 q 跳过；单语言与缺头对照保持。说明：它不解释前端单语言请求下的语言错配。实施票据 [E3](../exec/E03-accept-language-q.md)。
