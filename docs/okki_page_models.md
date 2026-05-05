# OKKI Page Models

## drawer mode

### Landmarks
- 客户列表/搜索结果区域（左/中）
- 右侧详情抽屉容器（通常包含 `资料` / `动态` / `商机&交易` 等 tab）
- 抽屉顶部客户名称
- 抽屉关闭按钮（右上角 X）

### Readable fields
- 客户名称
- 客户等级（通常在 `资料` 内）
- 客户标签（通常在 `资料` 内）
- 公司基础信息块（公司名、国家/地区、联系方式）

### Candidate actions
- read_customer_name
- read_customer_level
- read_customer_tags
- read_customer_identity_fields
- close_drawer

### Forbidden actions
- 点击任何 `保存/提交/发送/删除/确认/归档/合并` 按钮
- 点击会触发写入的 `编辑后保存` 流程
- 通过固定坐标点击

### Variable parts
- 列表点击后可能进入抽屉，也可能跳转 full_page
- 抽屉字段顺序可能受权限/布局配置影响
- 标签、等级控件可能按角色显示不同交互形态

## full_page mode

### Landmarks
- URL: `/crm/customer/personal?company_id=...`
- 页面标题：`客户详情-OKKI 客户管理`
- 客户主标题（本次证据：`Waleed Alrakide`）
- tab 区：`动态` / `资料` / `商机&交易` / `Tips` / `AI 背调` / `数据分析` / `文档` / `操作历史`
- 信息分组：`公司常用信息` / `公司其他信息` / `跟进信息` / `系统信息`

### Readable fields
- 客户名称（标题区）
- 客户等级（通常在 `资料` 分组内）
- 客户标签（通常在 `资料` 分组内）
- 公司名/邮箱/电话/国家地区（若在当前分组渲染）

### Candidate actions
- read_customer_name
- read_customer_level
- read_customer_tags
- read_customer_identity_fields
- read_followup_summary

### Forbidden actions
- `合并客户`
- `编 辑`（在侦查阶段）
- `写邮件`
- 任何 `保存/提交/发送/删除/确认/归档/合并` 行为

### Variable parts
- 字段展示可能懒加载，需滚动后才渲染
- 不同租户的字段名/顺序/可见性可能不同
- 某些字段仅在展开分组后可见
