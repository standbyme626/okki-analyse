# OKKI 客户数据爬取计划

## 目标

爬取 OKKI 中 31,914 条"客户等级为空"的客户资料，用于后续背调分析和回填。

### 连接前置条件（必须）

- 浏览器连接统一走 Windows Edge CDP bridge。
- 禁止使用 `agent-browser --session okki`。
- 优先使用 `okki_agent.edge_bridge._run()` / `_eval()`。
- 运行前确认 bridge 可访问（`OKKI_BRIDGE_URL`，默认 `http://172.22.208.1:21002`）。

## 数据需求分析

### 文档依据

- `docs/ziliao/OKKI_Writeback_Rules_v7.md` — 回写规则（补全字段、等级机制、跟进模板）
- `docs/ziliao/阿里巴巴客户背调SOP.docx` — 背调 SOP（头像、姓名、邮箱、官网分析、行为数据、商业类型等）
- `docs/ziliao/客户等级划分+跟进SOP.docx` — ABCD 等级划分标准

### 需要爬取的字段（共约 33 个，从 4 个区块提取）

#### 资料表单：公司常用信息（8 个，全部保留）

公司网址、公司名称、简称、国家地区、客户来源、客户阶段、客户编号、座机

#### 资料表单：公司其他信息（14 个，全部保留）

客户类型、年采购额、采购意向、时区、规模、产品分组、传真、详细地址、公司备注、公司logo、客户代码、客户等级、客户销售渠道、询盘产品

#### 联系人卡片（4 个，全部保留）

姓名、邮箱、职级、性别

#### 跟进信息（~19 个，只保留 3 个）

| 保留 | 丢弃 |
|------|------|
| 最近联系时间、最近跟进时间、下次日程时间 | 其余 TM/WhatsApp/EDM 时间线等（全空或无关） |

#### 系统信息（~16 个，只保留 4 个）

| 保留 | 丢弃 |
|------|------|
| 创建时间、创建人/跟进人、来源详情、客群 | 创建方式、关联线索、同步时间等 |

### 字段与背调用途对照

| 阶段 | OKKI 字段 | 背调用途 |
|------|------|------|
| 背调输入 | 公司名称 | Google 搜索、LinkedIn 查公司 |
| | 公司网址 | 官网分析 SOP（主营产品、市场定位、联系方式） |
| | 国家地区 | 核心市场/非重点市场判断 |
| | 邮箱（联系人） | 邮箱类型判断（企业/Gmail/虚拟）→ 跟进优先级 |
| | 姓名（联系人） | LinkedIn/Facebook/Instagram 搜索 |
| | 客户来源 + 来源详情 | Alibaba 店铺信息 |
| 等级判断 | 最近联系时间、创建时间 | 活跃度 + 注册年限（判定流失风险） |
| | 年采购额、规模 | 只读参考，等级划分依据 |
| | 客户阶段 | 当前跟进进度 |
| 回填目标 | 客户等级 | 等级打标（P-A~P-D 或 A~D） |
| | 客户类型、客户销售渠道、询盘产品、产品分组 | 资料补全 |
| | 详细地址、公司备注 | 资料补全 + 背调摘要 |

### 不在 OKKI 的数据（需从 Alibaba 或外部获取）

注册时间（Alibaba）、登录天数（Alibaba）、产品浏览数（Alibaba）、有效 RFQ 数（Alibaba）、商业类型（Alibaba）、买家标签/特征（Alibaba）、最常采购行业（Alibaba）、头像（Alibaba → Google 反向搜图）、公司官网分析（Google 外部搜索）

## 爬取策略

### 阶段0：单客户 Dry-Run 门禁（先于批量执行）

- 仅执行 1 个测试客户：搜索、打开详情、读取现有标签、产出 proposed tags。
- 明确禁止保存（stop before save）。
- 门禁通过后，才进入阶段一/阶段二批量流程。

### 两阶段方案

### 页面模式检测与分流

- 每个客户先检测 `page_mode`：`drawer` / `full_page` / `unknown`。
- `full_page`：直接访问 `/crm/customer/personal?company_id=...`。
- `drawer`：在列表页点击客户进入右侧抽屉。
- `unknown`：重抓一次 `snapshot -i`，仍失败则记录到失败日志并跳过。

#### 阶段一：采集 company_id 列表

1. 在筛选"客户等级=空"后的列表页，从第 1 页开始逐页翻页
2. 每页用 JS eval 提取 20 条客户的 `company_id` + 公司名称 + 国家 + 最近联系时间
3. 写入 `data/master_customer_ids.csv`
4. 总页数 1,596，每页 ~4s，总耗时约 2 小时

#### 阶段二：逐条打开详情页抓取

1. 读取 `data/master_customer_ids.csv`，逐条 `open` 详情页 URL
2. 一次 eval 同时抓取资料表单 + 联系人卡片
3. Python 侧过滤，只保留 33 个有用字段
4. 写入 `logs/scrape_results.jsonl`（每条写完立即 flush）
5. 断点续爬：启动时读取已完成 company_id 集合，跳过
6. 失败写 `logs/scrape_failed.jsonl`，重试 3 次后跳过

### 安全措施

| 措施 | 具体做法 |
|------|------|
| 随机间隔 | 每个客户之间 `random(4, 8)` 秒 |
| 模拟滚动 | 打开详情后随机 scroll 100-300px |
| 分批执行 | 每 500 条休息 30 分钟 |
| 每日上限 | 每天 4 批，约 2,000 条/天 |
| 断点续爬 | 每条实时写 JSONL + progress.json 记录进度 |
| 失败隔离 | 单条失败不阻塞整体流程 |

### 实验日志与截图检查点（强制）

- 每次 run 记录：objective, start_url, page_mode, commands_executed, clicked_target, expected_result, actual_result, screenshot_paths, conclusion。
- 截图检查点：`before-read`、`on-error`；`before-write`/`after-write` 仅在用户明确授权写入时启用。

### 时间估算

| 项目 | 耗时 |
|------|------|
| 阶段一 | ~2 小时 |
| 阶段二（31,914 × 平均 6s） | ~53 小时 |
| 按 2,000 条/天 | **约 16 天** |
| 加速（缩短间隔 + 晚上跑） | **约 10 天** |

### 加速选项

- 缩短间隔到 `random(2, 5)` → 约 10 天
- 晚上也跑 → 周末可达 5000+/天
- 先抓高优先级（欧美、有邮箱/网址、最近活跃），低优先级后抓

### 风险判断

OKKI 是企业付费 SaaS，非公开网站，反爬机制较电商/内容平台弱。最大风险是账号异常行为被运营/风控注意到，而非自动化拦截。分批、间隔、模拟人类行为的策略可有效降低风险。批量写操作（回填）风险高于纯读取（爬取）。

## 输出文件

| 文件 | 内容 |
|------|------|
| `data/master_customer_ids.csv` | company_id, customer_name, country, last_contact, list_url |
| `logs/scrape_results.jsonl` | 每条完整抓取结果（33 字段） |
| `logs/scrape_failed.jsonl` | 失败记录（company_id + 错误信息） |
| `logs/scrape_progress.json` | 进度：`{"done": 5230, "total": 31914, "last_updated": "..."}` |
