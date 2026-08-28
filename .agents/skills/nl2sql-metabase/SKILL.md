---
name: nl2sql-metabase
description: >
  将用户自然语言问题转换为 StarRocks SQL 报表模板，供 Metabase 平台使用。
  使用场景：用户描述想查询的业务指标（如"各班级授权人数""某营期外诉次数""复购订单金额""实体商品支付情况"），
  需要生成带 Metabase 变量语法（{{variable}}）的 SQL 模板时，必须启用此 skill。
---

# NL2SQL Metabase Skill

## 核心定位

生成的是 **Metabase 报表模板**，不是一次性查询：
- 用户提到「某营期、某班级、某周」时，这些是**筛选条件**，必须用 `{{variable}}`，不可硬编码
- 具体值由 Metabase 用户运行时填入
- 职责：识别「分组维度」+「聚合指标」+「可筛选字段」→ 产出标准模板
- 下游若需 Streamlit 页面，将本 skill 产出的 SQL + 变量说明表交给 `metabase-page` skill

## 业务层级

团队(tid) → 训练营(camp_id) → 营期(term_id) → 班级(class_id) → 学员(account_id)

---

## 第一步：动态检索 Schema 元数据（工具调用）

**生成任何 SQL 前，禁止盲目依赖记忆或全量读取大文件，必须使用 CLI 工具动态检索相关的表结构与模板**：

### 动态元数据工具 (`scripts/query_meta.py`)

运行以下命令行工具检索准确的表结构、别名、强制条件 `required_filters`、可选条件 `optional_filters` 与字段字典：

1. **关键词搜索表结构**（推荐首选）：
   ```bash
   uv run python scripts/query_meta.py --search "<问题关键词，如: 学员 授权 班级>"
   ```
2. **精准查询指定表**：
   ```bash
   uv run python scripts/query_meta.py --table "<表名，如: dws_lh_teaching_term_class_week>"
   ```
3. **检索复杂特定 SQL 模板**（如最新周基数、率值计算等）：
   ```bash
   uv run python scripts/query_meta.py --template "<关键词，如: 最新周>"
   ```
4. **查看全量数据表目录概览**：
   ```bash
   uv run python scripts/query_meta.py --list
   ```

### 元数据约束协议

| 字段 | 含义 |
|------|------|
| `alias` | SQL 别名；WHERE / JOIN ON 必须用别名 |
| `use_for` | 业务场景；多表可选时据此选型 |
| `required_filters` | **必须**注入 WHERE，且不加 `[[]]`；CTE 型则为固定 `WITH` 块 |
| `optional_filters` | 可选条件，加 `[[]]`；未列出时按业务需要自行添加 |

Metabase 模板中表名保留 `` `warehouse`.`表名` `` 前缀。

---

## 筛选条件通用规则

### 标准 WHERE 结构
```sql
WHERE 1=1
  AND <alias>.tid = {{tid}}              -- 若表有 tid，强制，无 [[]]
  AND <alias>.camp_id = {{camp_id}}      -- 若表有 camp_id，强制，无 [[]]
  AND <表 required_filters 中的条件>     -- 强制，无 [[]]
  [[ AND <用户可选筛选> ]]               -- 可选，有 [[]]
```

### 通用可选筛选模板
```sql
[[ AND <alias>.class_id IN ({{class_ids}}) ]]
[[ AND <alias>.wechat_nickname LIKE CONCAT('%', {{name}}, '%') ]]
[[ AND <alias>.col BETWEEN {{start_time}} AND {{end_time}} ]]
```

---

## 业务术语映射

### 第N期/N期
- 「第N期/N期」→ `term_id` 筛选：`AND ct.id IN ({{term_ids}})`（或事实表上的 `term_id`）
- `rank` 仅作 SELECT 展示字段，不用于筛选

---

## 歧义澄清规则

收到用户问题后，先评估歧义程度：

### 需要追问（生成前必须确认）

| 歧义场景 | 追问示例 |
|---------|---------|
| 多张表均可满足且语义差异大 | 列出两种方案的区别，请用户选择 |

### 可继续生成（在注意事项中提示）

| 歧义场景 | 处理方式 |
|---------|---------|
| 时间字段未指定精度（日/周/月） | 默认最细粒度，注意事项中说明 |
| 排序方式未指定 | 选合理默认值，注意事项中说明 |
| 可选筛选较多，用户未全部指定 | 全部生成为 `[[]]` 可选，注意事项中列出 |
| 查询订单数据，未指定时间范围 | `start_date`/`end_date` 仍作为必填变量，不硬编码具体日期 |

---

## 输出格式规范

按以下顺序组织输出：

### 1. 理解说明（1-3 句）
主表选择依据、分组维度、核心指标。

### 2. SQL 模板
````sql
代码块输出完整 SQL，包含所有 CTE。
````

### 3. Metabase 变量说明
**只列出本次 SQL 中实际出现的** `{{variable}}`：

| 变量名 | 类型 | 说明 | 是否必填 | 是否多选 |
|--------|------|------|---------|---------|
| … | Number / Text / Date | … | 必填 / 可选 | 是 / 否 |

约定：`tid`/`camp_id` 几乎总是必填单选；`term_ids`/`class_ids` 等多选 ID 用 Number + 多选=是；订单 CTE 的 `start_date`/`end_date` 为 Date 必填。

### 4. 图表推荐

| 场景 | 推荐图表 |
|------|---------|
| 单指标随时间变化 | 折线图 |
| 多维度横向对比（营期/班级） | 柱状图 |
| 单一汇总数字 | 数字卡片 |
| 多字段明细 | 表格 |
| 多维度交叉分析 | 透视表 |

### 5. 注意事项（如有）
表选择依据、歧义默认处理、需用户确认的判断等。

---

## SQL 语法规范

- 以 `WHERE 1=1` 起手
- 表名、保留字（`rank`/`partition`/`values`/`order`）、字段均加反引号
- 禁止 `SELECT *`，显式列出字段
- 每个表设别名，字段引用带别名；函数字段必须加英文别名
- 百分比：`ROUND(x * 100, 2) AS xxx_rate`（纯数值，不拼 `%`；Metabase 列设「百分比」）
- GROUP BY 字段必须同时出现在 SELECT

---

## 生成前自检清单

输出 SQL 前逐项确认：

1. ✅ 已使用 `query_meta.py --search` 检索到匹配表的 Schema 元数据（`required_filters`、`use_for`）
2. ✅ `WHERE 1=1`；有 `tid`/`camp_id` 的表已强制注入（无 `[[]]`）
3. ✅ 各表 `required_filters` 已全部注入（无 `[[]]`）；可选筛选均在 `[[]]` 内
4. ✅ 无业务 ID 硬编码
5. ✅ 分组维度同时在 `GROUP BY` 与 `SELECT`；指标已聚合
6. ✅ 统计学员人数时，已用 `NVL(s.account_main_id, s.account_id)` 去重（见 schema 学员表）
7. ✅ `dws` 含自然周维度时，已 JOIN `dim_lh_teaching_weeks_conf` 且条件完整
8. ✅ 使用 `authorize_account_order` 时，已完整粘贴 CTE 块
9. ✅ 已给出图表推荐；变量表仅含本次实际变量

## 参考文件与数据库配置

所有表元数据、字段字典与 SQL 模板持久化存储于 **SQLite 数据库** (`data/nl2sql_meta.db`)，建表定义维护在 `scripts/schema_sqlite.sql`。

- `scripts/query_meta.py` — **动态检索工具 (首选)**：`uv run python scripts/query_meta.py --search "<关键词>"`
- `references/schema.md` — 从 SQLite 自动同步导出的表结构与元数据（静态兜底）
- `references/queries.md` — 从 SQLite 自动同步导出的特定/常用查询模板（静态兜底）

### 管理与同步工具命令

- **动态检索工具**: `uv run python scripts/query_meta.py --search "<关键词>"`
- **建表 DDL**: `scripts/schema_sqlite.sql` (数据库结构变更时同步维护此 SQL)
- **修改配置**: Streamlit 页面「系统配置」 -> 「NL2SQL配置管理」
- **SQLite -> Markdown 同步导出**: `uv run python scripts/export_sqlite_to_md.py`
- **Markdown -> SQLite 初始化迁移**: `uv run python scripts/migrate_md_to_sqlite.py`
