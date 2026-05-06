# Run Review And Solidification

本文档定义每次脚本运行后的复盘与固化流程。目标是把临时探查得到的接口、UI、字段映射和失败经验沉淀下来，避免每次新会话重新分析页面。

## 核心原则

每次脚本运行后都要判断是否有可固化内容。

```text
接口固化 = 主路径
UI 固化 = 兜底路径 + 验证路径
```

接口适合批量读写，UI 适合验证、兜底和发现前端规则。两者不冲突，应该同时维护。

## 为什么需要 UI 固化

OKKI 使用私有前端接口，接口和字段可能随版本变化。即使最终批量执行优先走接口，也必须保留 UI 固化能力。

UI 固化的价值：

- 接口失效时，可以退回 UI 流程验证；
- 新字段找不到接口映射时，可以从 UI label 定位；
- 写接口 payload 不确定时，可以用 UI 保存做对照；
- 读回接口结果和页面显示不一致时，UI 可作为人工可见证据；
- 某些字段有前端校验、联动、下拉编码，UI 能暴露这些规则；
- 页面操作流程可用于单客户试写和异常复现。

## 每次 Run 后必须复盘的问题

每次脚本运行结束后，至少检查以下问题：

```text
1. 是否发现新接口
2. 是否发现新请求参数
3. 是否发现新响应字段
4. 是否发现新字段映射
5. 是否发现新的 UI selector / 页面结构
6. 是否发现新的页面状态或模式
7. 是否发现新的失败模式
8. 是否可以沉淀成脚本函数
9. 是否需要写入接口/UI 文档
10. 是否需要更新 CHANGELOG.md
```

如果答案为“是”，必须选择一种固化方式：

```text
可复用且稳定 -> 写入代码
暂时只确认一次 -> 写入文档
影响流程/风险 -> 写入 CHANGELOG.md
涉及实验运行 -> 写入 logs/experiment-runs.jsonl
```

## 接口固化内容

接口固化记录在 `OKKI_INTERFACES.md`，必要时再沉淀到代码模块。

每个接口至少记录：

```text
endpoint
method
content-type
触发方式
请求参数
payload schema
关键字段映射
成功响应判断
失败响应判断
读回验证方式
证据 HAR / summary / screenshot 路径
风险边界
```

示例：

```text
POST /api/customerV3Write/edit
公司备注字段: data.remark
详细地址字段: data.address
联系人备注字段: data.customers[0].remark
```

如果接口是写入接口，还必须记录：

```text
是否整表单保存
是否单字段 patch
是否需要读旧值
是否需要完整 payload
写后如何读回验证
是否有辅助校验接口
批量执行门禁
```

## UI 固化内容

UI 固化不应记录临时 `@eXX` ref。`@eXX` 只在一次 fresh snapshot 后临时有效，不能写入长期脚本。

UI 固化应记录语义定位策略。

错误方式：

```text
公司备注 = @e85
```

正确方式：

```text
在客户详情编辑抽屉中找到 label 文本 “公司备注”
向上找到同一个 `.paas-form-item`
再在该 form item 内找到 textarea/input
```

推荐定位模式：

```text
label -> form item -> input/textarea/select
section title -> section container -> field item
button text -> nearest drawer/footer/header context
page URL/title -> page mode
```

应固化的 UI 内容：

```text
页面模式识别：list / full_page_detail / drawer_detail / edit_drawer
进入编辑模式：通过 “编 辑” 按钮
展开公司可选字段：通过公司字段区域内 “展开全部 (选填)”
保存按钮：编辑抽屉 footer 内 “确 定”
取消按钮：编辑抽屉 footer 内 “取 消”
字段定位：根据 label 文本定位控件
读回验证：详情页资料 tab 中对应字段显示值
错误截图：on-error snapshot + screenshot
```

## 固化层级建议

### 文档层

用于记录已确认但还没完全自动化的知识。

```text
OKKI_INTERFACES.md              接口、payload、字段映射、风险
RUN_REVIEW_AND_SOLIDIFICATION.md 每次 run 后复盘和固化流程
CHANGELOG.md                    每次文件修改日志
```

建议后续新增：

```text
OKKI_UI_MODEL.md                UI 页面模型、语义定位、字段控件映射
```

### 代码层

用于沉淀可复用且稳定的逻辑。

建议模块：

```text
okki_agent/detail_page.py       详情页读取、详情接口封装
okki_agent/edit_payload.py      从 edit raw JSON 构建完整写入 payload
okki_agent/ui_model.py          UI 语义定位、字段控件查找、读回验证
```

已有相关模块：

```text
okki_agent/edge_bridge.py       Edge CDP bridge
okki_agent/list_page.py         阶段一列表页采集模型
okki_agent/writer.py            现有 UI 写入函数
okki_agent/reader.py            现有详情读取函数
```

## 推荐 Run 后流程

每次脚本或探查运行结束后执行：

```text
1. 检查输出结果是否符合预期
2. 检查失败、异常、慢请求、空字段、重复数据
3. 检查是否出现新接口或新字段
4. 检查是否出现新 UI 结构或稳定 selector
5. 判断哪些内容需要固化
6. 更新文档或代码
7. 更新 CHANGELOG.md
8. 如涉及浏览器实验，追加 logs/experiment-runs.jsonl
9. 如涉及写操作，确认截图、旧值、新值、读回验证齐全
10. 再决定是否扩大批量规模
```

## 写入场景额外要求

写入场景比读取风险高，必须更严格。

写入前：

```text
读取旧值
截图 before-read
构建 proposed payload
diff 检查只允许目标字段变化
截图 before-write
用户确认范围和停止条件
```

写入后：

```text
读取接口响应
截图 after-write
读回详情确认目标字段
记录 old_value / new_value / restored_value
记录 success / failure / error
失败立即停止或进入人工复核
```

批量前必须先通过：

```text
单客户 UI 试写
单客户接口试写
10 条小批量
100 条小批量
错误率为 0 才能扩大
```

## 当前已形成的固化结论

当前项目已确认：

```text
阶段一主路径：POST /api/customerV3Read/companyList
客户详情写接口：POST /api/customerV3Write/edit
公司备注字段：data.remark
详情读回接口：GET /api/customerV2Read/detail?company_id=...&scene=detail
编辑原始数据接口：GET /api/customerV2Read/detail?company_id=...&scene=edit
```

当前仍需补充：

```text
阶段二 detail/edit raw JSON 采集脚本
clean_customers 清洗脚本
write payload 构建与 diff 校验模块
OKKI_UI_MODEL.md
```
