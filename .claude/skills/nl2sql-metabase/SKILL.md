---
name: nl2sql-metabase
description: >
  将用户自然语言问题转换为 Apache Doris SQL 报表模板，供 Metabase 平台使用。
  使用场景：用户描述想查询的业务指标（如"各班级授权人数""某营期外诉次数""复购订单金额""实体商品支付情况"），
  需要生成带 Metabase 变量语法（{{variable}}）的 SQL 模板时，必须启用此 skill。
  涵盖：梨花效能平台的学员/班级/营期/团队多层级数据，支持 dws 周汇总表、ods 学员明细表、以及授权学员订单视图，CTE 型（authorize_student_pay）。
  凡是涉及 NL2SQL、Doris SQL 生成、Metabase 模板、训练营业务数据查询、复购订单分析，均应使用此 skill。
compatibility: Designed for Claude Code and similar skill-compatible clients. Scripts require Python 3.10+ and (for live execution) pymysql.
---

# NL2SQL Metabase Skill

## 核心定位

生成的是 **Metabase 报表模板**，不是一次性查询：
- 用户提到"某营期/某班级/某周"时，这些是**筛选维度**，不是要硬编码的值
- 具体值由 Metabase 用户运行时填入
- 职责：识别「分组维度」+「聚合指标」+「可筛选字段」→ 产出标准模板

## 业务层级

团队(tid) → 训练营(camp_id) → 营期(term_id) → 班级(big_class_id) → 学员(account_id)

---

## 第一步：读取 Schema 与派生字段定义

**生成任何 SQL 前，必须同时读取以下两个文件：**
1. `references/schema.md` — 找到涉及的所有表，提取元数据
2. `references/fields.md` — 查找用户描述中是否命中已定义的派生字段

两个文件的约束都不依赖记忆，必须实际读取。

---

## 派生字段协议

fields.md 中每个派生字段包含触发词、依赖表、SQL 表达式和业务说明，按以下规则使用：

- **命中触发词** → 直接将 SQL 表达式嵌入 SELECT 或 SUM(IF(...)) 等聚合中，不得改写逻辑
- **未命中但用户描述了判断逻辑** → 根据描述生成表达式，同时提示用户可将其补充进 fields.md
- **派生字段可用于** SELECT 展示、WHERE/HAVING 过滤、SUM/COUNT 等聚合计算

---

## 表元数据协议

schema.md 中每张表用以下结构描述自己的约束，生成 SQL 时按此协议应用：

### `别名`（alias）
- 用于在 SQL 中引用该表，避免重复写表名
- 例如：`warehouse`.`dws_lh_teaching_term_class_week` 可以用 `w` 表示，`warehouse`.`dim_lh_teaching_class_term` 可以用 `ct` 表示
- 生成 SQL 时，必须在 WHERE 中使用别名，不能直接引用表名
- 例如：`WHERE w.tid = {{tid}}`


### `use_for`（业务场景）
- 描述该表适合回答哪类问题
- 用于在多表可选时做出正确的表选择决策

### `required_filters`（表级强制筛选）
- 列出的所有条件**必须**注入 WHERE，且**不加 `[[]]`**
- 原因：这些字段是该表的"定位键"，缺失会导致数据错误或越权
- 部分表的 required_filters 以 **CTE 形式**定义（而非 WHERE 条件），使用时须在 SQL 开头以 `WITH ... AS (...)` 声明，主查询再 JOIN 该 CTE


---

## 筛选条件通用规则

### 标准 WHERE 结构
```sql
WHERE 1=1
  AND <alias>.tid = {{tid}}              -- 若表有 tid 字段，强制，无 [[]]
  AND <alias>.camp_id = {{camp_id}}      -- 若表有 camp_id 字段，强制，无 [[]]
  AND <表 required_filters 中的条件>     -- 强制，无 [[]]
  [[ AND <用户可选筛选> ]]               -- 可选，有 [[]]
```

### 通用可选筛选模板
```sql
[[ AND <alias>.term_id IN ({{term_ids}}) ]]
[[ AND <alias>.big_class_id IN ({{class_ids}}) ]]
[[ AND <alias>.wechat_nickname LIKE {{name}} ]]  -- WAF 拦截 CONCAT，由调用方在变量值中拼好 % 通配符（如 %张三%）
[[ AND <alias>.col >= {{start_time}} ]]
[[ AND <alias>.col <= {{end_time}} ]]
```

### 业务术语映射（硬编码枚举，不用变量）
- "已授权/授权学员" → `AND s.authorization_status = 'authorized'`
- "未授权" → `AND s.authorization_status = 'unauthorized'`
- "已添加/添加好友" → `AND s.add_status = 'added'`
- "第N期/N期" → `[[ AND ct.term_id IN ({{term_ids}}) ]]`
  - `rank` 仅作为展示字段（出现在 SELECT 中），不用于筛选条件

### 铁律（任何情况不可违反）
- `tid` / `camp_id` 强制筛选，永远不加 `[[]]`
- `required_filters` 中的条件永远不加 `[[]]`
- 变量名：营期筛选用 `{{term_ids}}`（复数），班级筛选用 `{{class_ids}}`（复数）
- 不硬编码任何业务 ID
- **统计学员人数时，必须 LEFT JOIN `ods_mdb_account_main_relation`，以 `NVL(amr.account_main_id, s.account_id)` 作为 COUNT DISTINCT 的去重键**，避免同一学员多 account_id 重复计算

---

## 歧义澄清规则

收到用户问题后，先评估歧义程度，再决定是追问还是继续生成：

### 需要追问的较大歧义（生成前必须确认）

| 歧义场景 | 追问示例 |
|---------|---------|
| 查询订单，未说明类型 | "请问查询的是实体商品订单、高价课订单，还是两者合并？" |
| 统计人数，未说明去重方式 | "统计人数是按荔课ID(account_id)计，还是需要按主账号(account_main_id)去重？" |
| 多张表均可满足需求且语义差异大 | 列出两种方案的区别，请用户选择 |

### 可继续生成的较小歧义（在注意事项中给出提示）

| 歧义场景 | 处理方式 |
|---------|---------|
| 时间字段未指定精度（日/周/月） | 默认选最细粒度，注意事项中说明 |
| 排序方式未指定 | 选合理默认值，注意事项中说明 |
| 可选筛选字段较多，用户未全部指定 | 全部生成为 [[]] 可选，注意事项中列出 |
| 派生字段逻辑与 fields.md 定义略有出入 | 按 fields.md 执行，注意事项中提示差异 |

---

## 输出格式规范

生成 SQL 时，输出内容按以下顺序组织：

### 1. 理解说明（1-3 句）
说明识别到的查询意图：主表选择依据、分组维度、核心指标，以及是否命中派生字段。

### 2. SQL 模板
```sql 代码块输出完整 SQL，包含所有 CTE。
```

### 3. Metabase 变量说明
以表格形式列出 SQL 中所有 {{variable}} 变量：

| 变量名 | 类型 | 说明 | 是否必填 |是否多选 |
|--------|------|------|---------|---------|
| tid | Number | 团队 ID | 必填 | 否 |
| camp_id | Number | 训练营 ID | 必填 | 否 |
| term_ids | Number | 营期 ID（可多选） | 必填 | 是 |
| class_ids | Number | 班级 ID（可多选） | 可选 | 是 |
| ... | ... | ... | ... | ... |

### 4. 注意事项（如有）
如果生成过程中存在需要用户确认的判断（如表选择依据、派生字段逻辑未收录于 fields.md、歧义处理方式），在此说明。

---

## SQL 语法规范

- 以 `WHERE 1=1` 起手
- 表名、Doris 保留字（`rank`/`partition`/`values`/`order`）、字段均加反引号
- 禁止 `SELECT *`，显式列出所有字段
- 每个表设有意义的别名，所有字段引用带表别名
- 函数字段必须加英文别名
- 百分比：`ROUND(x * 100, 2) AS xxx_rate`（纯数值，不拼 `%` 后缀；在 Metabase 列设置「百分比」格式展示）
- 禁止 `NULLIF`：用 `IF(x = 0, NULL, x)` 等效替代（WAF 拦截 `NULLIF` 和 `CONCAT` 关键字）
- GROUP BY 出现的字段必须同时在 SELECT 中

---

## 生成前自检清单

> 在输出 SQL 之前，按顺序逐项过一遍。

1. ✅ 已读取 schema.md（确认每张表的 required_filters 和 use_for）和 fields.md（确认是否命中派生字段触发词）
2. ✅ WHERE 1=1 起手
3. ✅ 涉及表中有 `tid` 字段 → 已强制 `AND <alias>.tid = {{tid}}`（无 [[]]）；
4. ✅ 涉及表中有 `camp_id` 字段 → 已强制 `AND <alias>.camp_id = {{camp_id}}`（无 [[]]）
5. ✅ 每张表的 required_filters 全部注入（无 [[]]）
6. ✅ 其他可变筛选都在 [[]] 内，且变量名不为空
7. ✅ 营期筛选变量名为 `term_ids`、班级筛选变量名为 `class_ids`，均用 `IN` 形式
8. ✅ 无任何业务 ID 硬编码
9. ✅ 分组维度在 GROUP BY 和 SELECT 中都出现，指标字段都加了聚合函数
10. ✅ 统计学员人数时，已 LEFT JOIN `ods_mdb_account_main_relation`，COUNT DISTINCT 使用 `NVL(amr.account_main_id, s.account_id)` 去重
11. ✅ 已根据 GROUP BY 维度和指标类型，给出图表推荐（折线图/柱状图/数字卡片/表格/透视表）

---

## 参考文件

- `references/schema.md` — 所有表的结构与元数据，每张表附典型 SQL 示例（**每次生成 SQL 必须查阅**）
- `references/fields.md` — 预定义派生字段（**每次生成 SQL 必须查阅**，命中触发词则套用对应表达式）

---

## 保存结果

当用户明确表示"保存"、"存下来"、"记录这个结果"、"保存这个模板"、"保存这个查询"、"保存这个报表"、"保存这个SQL"时，执行以下脚本：

```
scripts/save_result.py
```

**调用方式**：

```bash
python scripts/save_result.py \
  --sql_template        "<SQL模板内容>" \
  --variables  "<Metabase变量说明（JSON字符串）>"
```

**保存内容**：
1. SQL 模板（含 Metabase `{{variable}}` 语法）
2. Metabase 变量说明（变量名、类型、说明、是否必填、是否多选）

脚本内部通过 API 接口持久化，详见脚本注释。