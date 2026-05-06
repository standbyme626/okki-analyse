# OKKI Interface Notes

本文档记录本项目已通过 OKKI 页面真实请求确认过的接口。除明确说明外，接口信息只作为自动化设计依据，不代表允许直接批量调用写入接口。

## 安全原则

- `Read` 类接口可用于读取和验证数据，但仍需要限速、断点和日志。
- `Write` 类接口不得擅自批量调用。
- 写入前必须先读取旧值、生成写入计划、人工确认范围、单客户试写、写后读回验证。
- 批量回填必须有停止条件、错误日志、旧值备份和可审计记录。
- 私有接口不是官方开放 API，字段和行为可能随 OKKI 前端版本变化。

## 已确认只读接口

### 客户列表采集

```text
POST /api/customerV3Read/companyList
```

用途：阶段一采集客户列表页数据。

确认方式：刷新客户列表页并记录 HAR，页面自身调用该接口渲染列表。

请求类型：`application/x-www-form-urlencoded`

关键参数：

```text
pageSize=100
show_field_key=company.private.list.field
user_num[0]=1
user_num[1]=2
show_all=1
sort_scene=setting
swarm_id=<当前客群ID>
curPage=<页码>
layout_flag=1
```

关键响应路径：

```text
data.list
```

已用于输出字段：

```text
company_id
name / name_info
country
province
city
country_region
order_time / order_time_info
```

项目映射：

```text
customer_name  <- name / name_info
customer_url   <- /crm/customer/personal?company_id=<company_id>
country        <- country_region 转中文国家名后拼接省/市
last_contact   <- order_time_info.info_label 或 order_time
```

当前固化位置：

```text
okki_agent/list_page.py::collect_list_page_rows_via_api()
scripts/collect_stage1_urls.py
scripts/collect_stage1_page_batch.py
```

## 已确认写入接口

### 客户详情编辑保存

```text
POST /api/customerV3Write/edit
```

用途：客户详情页点击 `编辑` 后保存客户资料。

确认方式：对单个测试客户 `Tracy Mpata` 执行 UI 保存探查，记录 HAR，并在保存后读回验证。

测试客户：

```text
company_id=30879782397234
customer_name=Tracy Mpata
```

请求类型：`application/x-www-form-urlencoded`

顶层参数：

```text
company_id=<company_id>
archive_flag=0
lead_id=
data=<完整客户编辑表单 JSON>
```

公司备注字段：

```json
{
  "remark": "ai测试修改"
}
```

恢复为空时：

```json
{
  "remark": ""
}
```

重要区分：

```text
data.remark              公司备注
data.customers[0].remark 联系人备注，不是公司备注
```

关键风险：

- 该接口是整份客户编辑表单保存，不是单字段 patch。
- 不能只提交 `remark`，否则可能覆盖其他字段。
- 批量写入必须先通过详情读接口构造完整 payload，再只替换目标字段。
- 写入后必须使用详情读接口读回验证。

探查结果摘要：

```text
address="ai测试修改" 误填详细地址，已恢复为空
remark="ai测试修改"  正确写入公司备注
remark=""            正确恢复公司备注为空
所有 /api/customerV3Write/edit 写请求状态码均为 200
最终页面读回：详细地址为空，公司备注为空，页面不包含 ai测试修改
```

证据文件：

```text
logs/recon/company_remark_probe_20260505-192734.har
logs/recon/company_remark_probe_20260505-192734.summary.json
logs/experiment-runs.jsonl
```

相关截图：

```text
screenshots/interface_probe_before-read_20260505-192734.png
screenshots/interface_probe_before-write_restore_address_20260505-192734.png
screenshots/interface_probe_after-write_restore_address_20260505-192734.png
screenshots/interface_probe_before-write_set_remark_20260505-192734.png
screenshots/interface_probe_after-write_set_remark_20260505-192734.png
screenshots/interface_probe_before-write_clear_remark_20260505-192734.png
screenshots/interface_probe_after-write_clear_remark_20260505-192734.png
```

## 已确认辅助校验接口

### 公司名称唯一性检查

```text
POST /api/customerRead/fieldUniqueCheck
```

用途：保存客户编辑表单前，页面检查字段唯一性。

观察到的请求体：

```text
refer_type=4
value=Tracy Mpata
field_id=name
refer_id=30879782397234
```

备注：这是保存流程中的辅助读/校验接口，不是目标写接口。

### 客户编号检查

```text
GET /api/customerWrite/checkCustomerNo?serial_id=1505&company_id=30879782397234
```

用途：保存客户编辑表单前，页面检查客户编号。

备注：路径含 `Write`，但观察到是 GET 校验请求；批量流程中不应单独假设其无副作用，需按保存流程整体验证。

## 已确认读回接口

### 客户详情读取

```text
GET /api/customerV2Read/detail?company_id=<company_id>&scene=detail
GET /api/customerV2Read/detail?company_id=<company_id>&scene=edit
```

用途：

- `scene=detail` 用于保存后详情读回验证。
- `scene=edit` 用于进入编辑模式时读取可编辑表单数据。

批量回填设计建议：

```text
1. scene=edit 读取完整可编辑数据
2. 基于原始数据构造 edit payload
3. 只替换目标字段，例如 data.remark
4. POST /api/customerV3Write/edit
5. scene=detail 读回验证目标字段
6. 记录 old_value/new_value/response/readback/error
```

## 未确认候选接口

以下接口曾在前端资源或网络记录中出现，但尚未完成参数与响应验证，不得固化使用：

```text
/api/customerRead/companyList
/api/customerRead/list
/api/customerRead/CustomerList
/api/customerRead/searchList
/api/customerRead/LastContactList
/api/customerRead/contactList
/api/customerRead/attachmentList
/api/GroupRead/groupDetail
```

使用前必须通过对应页面动作、HAR、请求体、响应字段和读回验证确认。
