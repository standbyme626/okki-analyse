# Changelog

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
