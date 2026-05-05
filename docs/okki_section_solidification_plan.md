# OKKI 公司信息分组固化方案

## 目标范围
- 仅固化 `资料` 页面下两个分组：
- `公司常用信息`
- `公司其他信息`
- 本阶段仅做读取与动作规划，不做保存写入。

## 1) 从“动态”切换到“资料”是否可固化
可以固化。

建议流程：
1. 先 `detect_page_mode()`，确保已在客户详情上下文（drawer 或 full_page）。
2. 读取当前已选 tab；若不是 `资料`，执行语义点击 `资料`（只点击 tab，不点编辑/保存）。
3. 重新 snapshot，验证 `资料` 已 selected。

稳定点：
- 用 tab 文本 `资料` 做锚点。
- 不用固定 `@eXX`，每次切换后重抓 snapshot。

## 2) 公司常用信息/公司其他信息的展开收起是否可固化
可以固化。

建议流程：
1. 确保 `资料` tab 已选中。
2. 定位分组标题文本（`公司常用信息` / `公司其他信息`）。
3. 判断当前状态：
- 若分组下字段（LabelText）数量 > 0，视为展开。
- 若字段不可见，视为收起。
4. 仅在状态不符合预期时点击分组标题或其邻近 toggle 图标。
5. 重新 snapshot 并再次检查字段可见性数量。

安全性：
- 展开/收起属于导航/展示动作，不是写入动作。
- 但仍要遵守黑名单：不点击 `编辑/保存/提交/确认`。

## 3) 字段缺失、顺序变化时如何处理
核心原则：**按字段名匹配，不按位置匹配**。

策略：
- 用 `LabelText -> StaticText(label)` 找字段名。
- 在该 label 附近提取 value。
- 缺字段时返回 `null`，不要抛出致命错误。
- 发现未预置的新字段时放入 `extra_fields`，用于后续 schema 演进。

示例输出结构：
- `fields`: 预定义字段（可能为 null）
- `extra_fields`: 页面新增但未预定义字段

## 4) 已落地的代码骨架
- `okki_agent/writer.py`
- `prepare_switch_to_profile_tab()`
- `prepare_toggle_profile_section()`
- `prepare_read_common_and_other_info()`
- `okki_agent/reader.py`
- `read_profile_section_fields()`
- `read_common_info_fields()`
- `read_other_info_fields()`

## 5) 失败与重试机制
- 失败条件：
- 找不到 `资料` tab
- 找不到分组标题
- 分组切换后字段可见性无变化
- 重试策略：
1. 重新 snapshot
2. 使用同义锚点（如完整标题 + 上下文）
3. 仍失败则返回 structured error，停止后续动作

## 6) 结论
- 这两个分组可以先做“高稳定度固化”。
- 先固化：tab切换 + 分组展开收起 + 全字段读取。
- 写入类（编辑/保存）继续保持 dry-run 计划，不在本阶段执行。
