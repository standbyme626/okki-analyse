# 数据库设计

## 选型结论：SQLite3（已安装 v3.45.1）

### 选型依据

| 维度 | 本项目需求 | SQLite3 适合度 |
|------|------|:---:|
| 数据量 | 4 万行 × 4 表 | 千万级以下无压力 |
| 并发 | 单用户单进程 | 零配置，无服务进程 |
| 部署 | WSL 环境，期望零运维 | 单文件 `data/okki.db` |
| Python 依赖 | — | 标准库自带 `sqlite3` |
| 查询类型 | JOIN / 过滤 / UPDATE 状态 | 完全支持 |
| 未来扩展 | 10 万行封顶 | SQL → PostgreSQL 语法兼容，迁移成本低 |

其他数据库（PostgreSQL / MySQL / MariaDB / ClickHouse）均未安装，且对本项目严重过剩。

### 配置

```python
conn = sqlite3.connect("data/okki.db")
conn.execute("PRAGMA journal_mode=WAL")      # 读写不互锁
conn.execute("PRAGMA foreign_keys = ON")      # 启用外键约束
```

## 四张表结构

### 表 1：raw_scrape（原始存档）

单次 eval 返回的全部 ~60 字段，不做裁剪和清洗。不可变，仅追加。

| 列 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `company_id` | TEXT NOT NULL UNIQUE | OKKI 公司 ID |
| `customer_name` | TEXT | 客户名称（h2） |
| `scraped_at` | TEXT | 抓取时间戳 |
| `raw_json` | TEXT NOT NULL | 原始 JSON（完整 eval 返回值） |

### 表 2：clean_customers（清洗后结构化数据）

从 raw_json 提取并清洗的 33 个有用字段。存储为独立列，方便查询过滤。

| 列 | 类型 | 来源 |
|------|------|------|
| `company_id` | TEXT PRIMARY KEY | |
| `customer_name` | TEXT | 联系人姓名 |
| `company_name` | TEXT | 公司名称 |
| `country` | TEXT | 国家地区 |
| `website` | TEXT | 公司网址 |
| `email` | TEXT | 联系人邮箱 |
| `contact_name` | TEXT | 联系人姓名（来自联系人卡片） |
| `contact_title` | TEXT | 职级 |
| `contact_gender` | TEXT | 性别 |
| `source` | TEXT | 客户来源 |
| `source_detail` | TEXT | 来源详情 |
| `stage` | TEXT | 客户阶段 |
| `level` | TEXT | 客户等级（当前值） |
| `biz_type` | TEXT | 客户类型 |
| `sales_channel` | TEXT | 客户销售渠道 |
| `annual_procurement` | TEXT | 年采购额 |
| `procurement_intent` | TEXT | 采购意向 |
| `scale` | TEXT | 规模 |
| `product_group` | TEXT | 产品分组 |
| `inquiry_product` | TEXT | 询盘产品 |
| `address` | TEXT | 详细地址 |
| `remark` | TEXT | 公司备注 |
| `timezone` | TEXT | 时区 |
| `phone` | TEXT | 座机 |
| `short_name` | TEXT | 简称 |
| `customer_code` | TEXT | 客户代码 |
| `customer_no` | TEXT | 客户编号 |
| `last_contact` | TEXT | 最近联系时间 |
| `last_followup` | TEXT | 最近跟进时间 |
| `next_schedule` | TEXT | 下次日程时间 |
| `created_at` | TEXT | 创建时间 |
| `creator` | TEXT | 创建人 |
| `owner` | TEXT | 跟进人 |
| `customer_group` | TEXT | 客群 |
| `cleaned_at` | TEXT | 清洗时间戳 |

### 表 3：enriched_customers（背调分析结果）

在 clean_customers 基础上追加背调结论。一个 company_id 一条记录。

| 列 | 类型 | 说明 |
|------|------|------|
| `company_id` | TEXT PRIMARY KEY REFERENCES clean_customers(company_id) | |
| `country_tier` | TEXT | 核心市场 / 非重点 / 潜力 / 不明 |
| `email_type` | TEXT | 企业邮箱 / Gmail / 虚拟 / 未知 |
| `website_found` | INTEGER | 0/1，是否找到官网 |
| `business_type` | TEXT | 批发 / 零售 / 电商 / 个体 / 不明 |
| `product_match` | TEXT | 高 / 中 / 低 / 无 |
| `contact_role` | TEXT | 老板 / 采购 / 普通职员 / 不明 |
| `active_level` | TEXT | 高 / 中 / 低 / 沉睡 |
| `register_years` | INTEGER | 注册年限 |
| `enriched_at` | TEXT | 背调时间戳 |
| `notes` | TEXT | 背调备注 |

### 表 4：writeback_plan（回填执行计划）

每条记录对应一个需要回填的客户，包含回填内容、状态和执行结果。

| 列 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `company_id` | TEXT NOT NULL REFERENCES clean_customers(company_id) | |
| `target_level` | TEXT | 目标等级（A/B/C/A-/D/P-A~P-D） |
| `target_tags` | TEXT | 新增标签（JSON 数组） |
| `company_note` | TEXT | 公司备注模板 |
| `level_reason` | TEXT | 等级判断依据 |
| `followup_priority` | TEXT | 高 / 中 / 低 |
| `needs_human_review` | INTEGER | 0/1，是否需要人工审核 |
| `status` | TEXT DEFAULT 'pending' | pending / done / failed / skipped |
| `result` | TEXT | 执行结果 |
| `written_at` | TEXT | 回填时间戳 |

## 数据流

```
raw_scrape (JSON 存档)
    │
    ▼ 清洗脚本：提取 33 字段，去零宽字符，统一空值
clean_customers (结构化)
    │
    ▼ 背调分析：LLM + 规则引擎
enriched_customers (分析结果)
    │
    ▼ 回填规则引擎：将分析结果转为 OKKI 可写字段
writeback_plan (执行计划)
    │
    ▼ writer 脚本逐条执行
    └─ status: pending → done / failed
```
