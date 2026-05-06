# OKKI Writeback Sync Plan

本文档定义 OKKI 批量回填前后的本地同步方案、接口调用顺序、数据表建议和风控边界。

目标不是“本地数据库永久实时等于 OKKI”，而是：

```text
每次回填时：
写前抓一份 OKKI 最新现场
写入
写后再抓一份 OKKI 最新结果
把这次写入事务完整记录到本地
```

这样可以保证：

- 不拿旧快照整包覆盖 OKKI 当前值；
- 每次写入都有写前基线、写后结果和读回证据；
- 本地库能追溯“写入当时 OKKI 是什么状态”。

## 1. 当前已确认的事实

### 已确认接口

```text
GET  /api/customerV2Read/detail?company_id=...&scene=edit
GET  /api/customerV2Read/detail?company_id=...&scene=detail
POST /api/customerV3Write/edit
```

### 已完成的真实写入验证

测试客户：

```text
company_id = 30879782397234
customer_name = Tracy Mpata
```

已验证往返：

```text
company.remark
"" -> "ai测试修改" -> ""
```

验证结果：

- 两次 `POST /api/customerV3Write/edit` 返回 `code=0`
- 写后 `detail` 读回 `remark="ai测试修改"`
- 还原后 `detail/edit` 读回 `remark=""`
- 非目标字段 `address` 未被带坏
- roundtrip diff = 0

结论：

- 单客户、单字段、受控写回路径已经打通；
- 该接口是 **full-form save**，不是单字段 patch；
- 因此不能用历史旧 payload 直接整包回填。

## 2. 为什么必须写前再读一次

风险不在“接口变了”，而在“数据会变”。

示例：

```text
你在 5 月 1 日抓了一份客户 edit 数据
业务员在 5 月 6 日改了客户的地址、等级或联系人
你在 5 月 7 日还拿 5 月 1 日的整份 payload 回填
结果就可能把业务员 5 月 6 日的新修改覆盖掉
```

因为 `POST /api/customerV3Write/edit` 是整表单保存，所以正确方式只能是：

```text
写前 fresh read 一次最新 scene=edit
以这份最新数据为底
只覆盖目标字段
再提交
```

一句话：

```text
不要用历史快照整包写回
要用写前最新现场数据生成本次 payload
```

## 3. 推荐的单客户写回事务

每个客户一次写入都走完整事务。

### 事务步骤

```text
1. 从本地分析结果表中取出“准备写入的目标值”
2. 从 OKKI fresh read：GET scene=edit
3. 把这次写前基线保存到本地，带时间戳
4. 用写前基线生成完整 payload
5. 只覆盖允许修改的目标字段
6. diff 校验：只允许目标字段变化
7. POST /api/customerV3Write/edit
8. GET scene=detail 或 scene=edit 做写后读回
9. 把写后结果保存到本地，带时间戳
10. 记录 success / failed / skipped / drift
```

### 推荐流程图

```text
analysis_result
    │
    ▼
fresh GET scene=edit  -----------> write_baseline (with timestamp)
    │
    ▼
overlay target fields
    │
    ▼
diff check (only allowed fields changed)
    │
    ▼
POST /api/customerV3Write/edit
    │
    ▼
fresh GET scene=detail/edit -----> write_after_snapshot (with timestamp)
    │
    ▼
writeback_log / current_state update
```

## 4. 本地数据库应该怎么存

你前面说的意思是对的：

```text
修改前后都抓一次
都写回本地数据表
这样本地库和 OKKI 在这次写入时点上是同步的
```

这里要强调：

```text
这是“写入时点同步”
不是“永久实时同步”
```

因为你写完后，业务员还是可能继续在 OKKI 里改数据。

### 建议的表分层

基于当前仓库已有的 `clean_customers / enriched_customers / writeback_plan`，建议再补下面几层。

#### A. `analysis_result`

用途：保存你分析后“准备写什么”。

建议字段：

```text
company_id
analysis_version
analysis_time
target_fields_json
target_values_json
analysis_reason
needs_human_review
```

说明：

- 这张表不代表 OKKI 当前现场值；
- 只代表“本地分析建议写什么”。

#### B. `write_baseline`

用途：每次真正写入前，从 OKKI fresh read 到的最新基线。

建议字段：

```text
id
company_id
write_job_id
captured_at
scene
raw_json
okki_edit_time
okki_update_time
target_fields_json
```

说明：

- 这是防止旧数据覆盖新数据的关键表；
- 一次写入一条或两条都可以，建议至少保存 `scene=edit`。

#### C. `writeback_log`

用途：记录一次写入事务本身。

建议字段：

```text
id
company_id
write_job_id
started_at
finished_at
status
request_payload_json
request_field_diff_json
response_json
readback_json
error_message
retry_count
```

状态建议：

```text
pending
running
success
failed
skipped
drift_blocked
readback_mismatch
```

#### D. `write_after_snapshot`

用途：保存写后 fresh read 的结果。

建议字段：

```text
id
company_id
write_job_id
captured_at
scene
raw_json
```

#### E. `customer_current`

用途：保存当前你本地认为“最新的客户状态”。

建议字段：

```text
company_id
last_synced_at
source
raw_json
structured_json
```

说明：

- 写成功后可以用 `write_after_snapshot` 更新这张表；
- 这样后续分析和检索直接读 `customer_current`；
- 历史过程仍保留在 `write_baseline / write_after_snapshot / writeback_log`。

## 5. 最推荐的字段更新策略

### 正确做法

```text
本地分析结果给出目标值
↓
写前 fresh read 一次 scene=edit
↓
以最新 scene=edit 为底构造 payload
↓
只覆盖目标字段
↓
写入
↓
写后读回
```

### 错误做法

```text
拿几天前抓到的整条客户 JSON
直接改一点点字段
整包打回 OKKI
```

这个错误做法最大的问题是：

```text
它会把别人在 OKKI 中途改过的值覆盖掉
```

## 6. 哪些字段现在可以写，哪些还需要再验证

### 已经真实验证过

```text
company.remark
```

### 高概率同接口可写，但建议先做代表性实测

```text
公司文本字段
公司下拉字段
公司枚举字段
联系人子字段 data.customers[]
```

建议最少补 3 组代表性验证：

```text
1. 文本字段：例如 address / short_name
2. 下拉字段：例如 level / scale / annual_procurement
3. 联系人子字段：例如 customers[0].remark 或 post
```

原因不是怀疑接口失效，而是：

- 下拉字段可能涉及编码值；
- 联系人字段是子对象，不完全等于公司字段；
- 某些字段可能有前端联动或校验。

## 7. 写入前什么情况下应该跳过

建议引入“漂移保护”。

以下情况不要直接写：

### 情况 A：当前现场值和分析基线差异太大

```text
本地分析基于旧数据得出结论
但写前 fresh read 发现客户等级、备注、负责人、联系人等核心字段已经明显变了
```

处理建议：

```text
标记 drift_blocked
不写
进入人工复核或重新分析
```

### 情况 B：目标字段已被人工填好

例如：

```text
你的目标是补公司备注
写前 fresh read 发现业务员已经填了非空备注
```

处理建议：

```text
默认跳过
除非规则明确允许覆盖
```

### 情况 C：写后读回不一致

处理建议：

```text
标记 readback_mismatch
立即停或转人工
不要继续扩大批量
```

## 8. 请求量和压力分析

### 单客户最基本请求量

如果按推荐事务走，单客户最少大约：

```text
1 x GET scene=edit   写前基线
1 x POST edit        实际写入
1 x GET scene=edit/detail 写后读回
```

即：

```text
约 3 个核心请求 / 客户
```

### 3 万条量级估算

```text
30,000 * 3 = 90,000 个核心请求
```

结论：

- 本地数据库压力很小，几乎可以忽略；
- 主要压力在 OKKI 侧，不在本地表；
- 但相比 UI 自动化，接口方式通常更轻、更稳定。

## 9. 风控与反爬建议

### 风险结论

不是“不能做”，而是“不能高并发机械猛打”。

### 推荐节奏

```text
单线程
不并发写
每客户随机间隔 2-5 秒
每 20-50 条增加一次 30-120 秒休息
失败不要立即无限重试
```

### 立即停机条件

```text
出现登录跳转
出现 403 / 429
出现验证码
连续多条 readback mismatch
连续多条 payload diff 异常
连续多条接口 response 非 code=0
```

### 批量放大顺序

```text
1 客户真实写回验证
10 条 smoke test
50 条小批量
100 条稳定批量
再逐步扩大
```

## 10. 推荐的本地状态流转

```text
analysis_ready
    ↓
prewrite_snapshot_done
    ↓
payload_built
    ↓
diff_validated
    ↓
write_sent
    ↓
postwrite_snapshot_done
    ↓
success / failed / skipped / drift_blocked / readback_mismatch
```

## 11. 与当前项目文档的关系

本方案与现有文档的关系如下：

- `OKKI_INTERFACES.md`
  - 记录已确认接口和字段映射
- `docs/database_design.md`
  - 记录基础数据库设计
- `RUN_REVIEW_AND_SOLIDIFICATION.md`
  - 记录每次 run 后如何复盘、固化、记日志
- 本文档
  - 聚焦“批量回填时如何保证写前写后同步、避免旧数据覆盖、控制风控”

## 12. 当前结论

最终结论可以压缩成一句话：

```text
OKKI 接口写回路径已经打通；
正式批量回填时，必须每条写入前 fresh read，一次一条生成最新 payload，写后再读回并更新本地表；
不要直接拿历史快照整包写回。
```

再压缩一点就是：

```text
可以回填
但要按“写前抓、写后抓、全程留痕、低速串行”的事务方式做
```
