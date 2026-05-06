# Changelog

## 2026-05-06 — 截图证据增加页面稳定门禁，避免白屏日志

### 背景

- 现有 checkpoint 截图规则只定义了 `before-read / before-write / after-write / on-error`，但没有统一的“页面稳定后再截图”实现；
- 浏览器在 `open` / `reload` 后如果立即截图，容易留下白屏或未完成加载的无效证据；
- 需要把稳定性等待逻辑收敛成共享 helper，并接入实际写入脚本。

### 改动

- 更新 `okki_agent/edge_bridge.py`：
  - 新增 `wait_ms()`、`get_url()`、`get_title()`、`snapshot_i()`；
  - 新增页面探针、稳定等待和 `capture_checkpoint()`；
  - helper 改为支持自定义 `run/eval` 包装器，方便旧 session 脚本和新 bridge 脚本共用同一套截图门禁；
  - checkpoint 截图默认要求页面 ready 后再执行，并同步输出 probe/snapshot 证据。
- 更新 `scripts/batch_set_restore_customer_level.py`、`scripts/validate_dropdown_fields_paced.py`、`scripts/batch_read_profile_fields.py`、`scripts/verify_next_10_customers_readonly.py`、`scripts/probe_okki_customer.py`、`scripts/test_fill_restore_7fields.py`：
  - 将直接 `screenshot` 改为统一走 `capture_checkpoint()`；
  - 截图旁同时落盘 `.ready.json` 与 `.snapshot_i.txt`，便于复盘为什么跳过或成功；
  - 日志中保留 `capture_ready / capture_success / screenshot_error / snapshot_error` 等元数据。
- 更新 `AGENTS.md`、`CLAUDE.md`、`RUN_REVIEW_AND_SOLIDIFICATION.md`：
  - 明确普通 checkpoint 不允许在页面未稳定时直接截图；
  - 若超时仍未 ready，应记录 probe/snapshot，跳过普通截图，而不是保留白屏 PNG。

### 影响范围

- 后续通过 edge bridge 执行的 checkpoint 截图默认更严格，日志证据更可读；
- 不改变 OKKI 写入范围，也不新增任何批量写入行为。

## 2026-05-06 — 将接口/UI 固化规则写入 AGENTS 与 CLAUDE

### 背景

- `RUN_REVIEW_AND_SOLIDIFICATION.md` 已定义每次脚本运行后的复盘与固化流程；
- `OKKI_INTERFACES.md` 已记录阶段一只读接口和客户详情写入接口；
- 需要让新会话读取 `AGENTS.md` / `CLAUDE.md` 时直接看到这些强制规则和文档入口。

### 改动

- 更新 `AGENTS.md`：
  - 增加 run review and solidification 规则；
  - 增加 interface/UI solidification 规则；
  - 明确接口主路径、UI 兜底路径、语义 selector 和写入安全策略。
- 更新 `CLAUDE.md`：
  - 增加 knowledge solidification workflow；
  - 增加已确认 OKKI 接口入口和关键接口摘要；
  - 明确 full-form save endpoint 不允许 partial payload。

### 影响范围

- 仅文档与工作流约束更新，不执行 OKKI 页面操作或接口调用。

## 2026-05-05 — 新增运行复盘与固化流程文档

### 背景

- 每次脚本运行都会产生可能复用的新知识，包括接口、字段映射、UI 结构和失败模式；
- 后续阶段需要同时维护接口主路径和 UI 兜底路径；
- 需要把“运行后复盘并固化”的流程写成根目录规范。

### 改动

- 新增 `RUN_REVIEW_AND_SOLIDIFICATION.md`：
  - 明确“接口固化 = 主路径，UI 固化 = 兜底路径 + 验证路径”；
  - 定义每次 run 后必须检查的 10 个问题；
  - 规定接口固化、UI 固化、写入场景和批量前门禁；
  - 给出后续建议模块：`detail_page.py`、`edit_payload.py`、`ui_model.py`、`OKKI_UI_MODEL.md`。

### 影响范围

- 仅新增流程文档，不执行 OKKI 页面操作或接口调用。

## 2026-05-05 — 记录已确认 OKKI 接口

### 背景

- 阶段一已确认客户列表只读接口；
- 单客户公司备注 UI 探查已确认客户详情编辑写入接口；
- 后续批量回填前需要把接口、字段映射、风险边界和证据路径固化到根目录文档。

### 改动

- 新增 `OKKI_INTERFACES.md`：
  - 记录 `/api/customerV3Read/companyList` 只读列表接口；
  - 记录 `/api/customerV3Write/edit` 客户详情编辑保存接口；
  - 明确公司备注字段为 `data.remark`，联系人备注为 `data.customers[0].remark`；
  - 记录保存前辅助校验接口和保存后详情读回接口；
  - 补充批量回填前必须遵守的安全门禁和证据文件路径。

### 影响范围

- 仅新增接口文档，不执行 OKKI 页面操作或接口调用。

## 2026-05-05 — 固化 OKKI 列表页 URL 采集模型

### 背景

- OKKI 客户列表已改为 `100 条/页`，但页面使用虚拟滚动，静态 DOM 只能看到当前渲染窗口内的部分客户链接；
- 阶段一需要稳定采集客户详情 URL，并过滤 `（示例）` 客户；
- 列表页提取逻辑需要从临时 JS 固化为可复用代码，供当前页、下一页和后续分页采集复用。

### 改动

- 新增 `okki_agent/list_page.py`：
  - 固化列表虚拟滚动容器定位；
  - 提供当前页滚动扫描、详情 URL 解析、示例客户过滤和页面状态读取；
  - 固化 `li[title="下一页"].okki-pagination-next` 分页方式，并等待翻页后虚拟列表内容刷新；
  - 输出 `raw_count`、`demo_count`、`valid_count` 以及 raw/valid/demo rows。
- 新增 `scripts/collect_stage1_urls.py`：
  - 只读采集当前列表页客户 URL；
  - 输出仓库既有 CSV 格式：`customer_index,customer_name,customer_url,note`；
  - 同步写 raw JSON、summary JSON 和最终 snapshot 证据。

### 影响范围

- 只新增阶段一读操作工具，不执行写入、保存、提交或客户资料修改。

## 2026-05-05 — 扩展阶段一 CSV：国家地区与最近联系时间

### 背景

- 列表行 DOM 已确认包含 `国家地区` 与 `最近联系时间` 两列；
- 后续背调优先级排序需要直接使用国家和活跃度字段；
- 原 CSV 只包含客户名与详情 URL，不便于人工检查。

### 改动

- 更新 `okki_agent/list_page.py`：
  - 从每行 `.cell` 中读取 `country` 与 `last_contact`；
  - 保留 raw JSON 中完整行字段，便于复核。
- 更新 `scripts/collect_stage1_urls.py`：
  - 默认 CSV 字段调整为 `customer_index,customer_name,customer_url,country,last_contact,note`；
  - 增加 `--limit` 参数，用于先输出小样本预览。

### 影响范围

- 阶段一采集输出格式变更；仍为只读采集，不执行任何 OKKI 写操作。

## 2026-05-05 — 增加阶段一多页采集脚本与健康检查

### 背景

- 需要从单页采集推进到 10 页 smoke test；
- 连续翻页采集需要随机节奏、翻页后刷新等待和异常即停，避免过快读取或污染输出。

### 改动

- 新增 `scripts/collect_stage1_page_batch.py`：
  - 从当前页开始连续采集多页；
  - 每页执行虚拟滚动扫描并写 combined CSV；
  - 每页检查页码、页大小、列表容器、raw_count、重复 company_id、空国家数量；
  - 翻页与页间加入随机等待，每 3 页加入额外休息；
  - 任一健康检查失败时保存 `on-error` snapshot 并停止。
- 调整 `okki_agent/list_page.py`：
  - 采集步长改为按估算行高小步扫描，降低虚拟列表漏行概率。
  - 过滤虚拟列表中 `translateY(-9999px)` 的缓存行，并按真实 `translateY` 位置恢复页面顺序。
  - 新增 `collect_list_page_rows_via_api()`，复用当前列表 URL 筛选条件调用 OKKI 自身只读接口 `/api/customerV3Read/companyList`，避免 `100 条/页` 虚拟滚动 DOM 漏行。
  - API 采集输出继续保持 `customer_index,customer_name,customer_url,country,last_contact,note`，国家字段使用浏览器 `Intl.DisplayNames('zh-CN')` 转为中文国家名，省/市保留原始文本。
- 更新 `scripts/collect_stage1_urls.py`：
  - 默认改为只读 API 采集单页，DOM 仅用于确认当前页面状态和保存 snapshot。
- 更新 `scripts/collect_stage1_page_batch.py`：
  - 连续页采集改为按 `curPage` 调用只读 API，不再依赖翻页点击或虚拟滚动；
  - 保留随机节奏、健康检查、异常即停、combined CSV、raw JSON、summary JSON 和最终 snapshot；
  - 批量运行结束后追加 `logs/experiment-runs.jsonl` 实验记录。

### 影响范围

- 新增只读批量采集入口；不执行客户详情打开、写入、保存或消息发送。

## 2026-05-05 — 文档一致性修正：执行命令统一 + 变更日志强制记录

### 背景

- `AGENTS.md` 中仍存在 `agent-browser --session okki` 示例；
- 连接层已切换到 Edge CDP bridge，`--session okki` 在本项目中不可用；
- 需要把“每次修改都要写日志”上升为明确规则，避免后续变更无记录。

### 改动

- 更新 `AGENTS.md` 的 Agent Browser Workflow：
  - 移除 `--session okki` 示例；
  - 改为 `--cdp <ws_url>` 或 `okki_agent.edge_bridge._run()` 方式；
  - 补充 bridge 前置条件与登录前置条件。
- 更新 `CLAUDE.md` 的提交规范：
  - 明确记录路径为仓库根目录 `CHANGELOG.md`；
  - 明确“每次文件修改必须追加 changelog 记录”。
- 更新 `docs/scraping_plan.md`：
  - 增加 CDP bridge 前置条件；
  - 增加 page_mode（drawer/full_page）检测与分流；
  - 增加单客户 dry-run 门禁；
  - 增加实验日志字段与截图检查点要求。

### 影响范围

- 仅文档与流程约束更新，不改变业务逻辑代码。

## 2026-05-05 — 连接层重构：CDP bridge 接入 + 翻页函数

### 背景

项目所有脚本此前硬编码 `agent-browser --session okki`，指向 agent-browser 自动拉起的 headless Chrome。该浏览器无 OKKI 登录态，所有浏览器操作实际无法生效。

唯一可用的浏览器是 Windows 宿主机上通过 `okki_edge_cdp_bridge.ps1` 启动的 Edge（携带用户手动登录的 OKKI Cookie），CDP 通过 bridge（`172.22.208.1:21002`）暴露给 WSL。

### 改动

#### 新建 `okki_agent/edge_bridge.py`

- `_get_ws_url()` — 从 bridge `/json/version` 动态获取 CDP WebSocket URL，支持 `OKKI_BRIDGE_URL` 环境变量覆盖
- `_run(*args)` — `agent-browser --cdp <ws>` 封装，取代 `--session okki`
- `_eval(js)` — JS eval 封装，返回解析后的值
- `_get_current_page()` — 读取当前分页页码
- `next_page()` — 点击"下一页"，轮询等待页码变化（默认 10s 超时），返回 `(old_page, new_page)`
- `prev_page()` — 点击"上一页"，轮询等待页码变化，第 1 页时抛异常

#### 修改 `okki_agent/writer.py`（+1 -25）

- 删除旧的 `_ab_run` / `_ab_eval`（硬编码 `--session okki`）
- 改为 `from .edge_bridge import _run as _ab_run, _eval as _ab_eval`
- `session=` 参数通过 `**_kw` 兼容，16 个业务函数无需改动

### 影响范围

- `batch_set_restore_customer_level.py` — 自动复活，无需改动
- `validate_dropdown_fields_paced.py` — 自动复活，无需改动
- 其余脚本不受影响

## 2026-05-05 — 爬取计划文档

新建 `docs/scraping_plan.md`：
- 数据需求分析：从三份 docs/ziliao 文档反推需爬字段（~33 个，从 4 区块提取）
- 两阶段方案：阶段一列表页采集 ID（~2h）+ 阶段二逐条详情抓取（~53h）
- 安全措施：随机间隔、分批、断点续爬、模拟人类行为
- 时间估算：按 2,000 条/天约 16 天，可加速至 10 天

## 2026-05-05 — 数据库选型及设计

新建 `docs/database_design.md`：
- 选型 SQLite3（已安装 3.45.1），分析 PostgreSQL/MySQL/MariaDB/ClickHouse 均不适合
- 设计四张表：`raw_scrape`（原始存档 JSON）、`clean_customers`（33 字段结构化）、`enriched_customers`（背调结论）、`writeback_plan`（回填执行计划+状态追踪）
- 配置 WAL 模式 + 外键约束

## 2026-05-05 — 补充 CLAUDE.md（安全规则 + 交互规则 + 页面模式 + 截图策略）

从 AGENTS.md 提炼关键操作规则到 CLAUDE.md：
- Safety rules：6 条硬约束（dry_run 默认、禁止保存/批量操作、写后验证等）
- Browser interaction rules：语义选择器优先于 @eXX ref，每次 DOM 变化后 re-snapshot
- Page modes：drawer vs full-page，操作前必须检测
- Screenshot checkpoints：before-read / before-write / after-write / on-error 四处

## 2026-05-05 — 新建 CLAUDE.md

项目初始化文档，供后续 Claude Code 实例了解：
- 浏览器连接架构（CDP bridge → Windows Edge）
- 核心模块关系（edge_bridge → writer → scripts）
- 脚本编写范式
- 提交规范（每次修改记录 CHANGELOG）
