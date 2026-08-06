---
name: metabse-page
description: >
  根据 Metabase SQL 模板与变量说明表，生成 Streamlit 数据查询页面：解析参数分类、
  补全 FILTER_REGISTRY、处理 fallback 筛选项，并注册到 app.py。
  在用户提供 Metabase SQL + 变量表、要求新建/生成数据页面，或从 nl2sql-metabase
  下游落地 Streamlit 页面时使用。
disable-model-invocation: true
---

# Metabase → Streamlit 页面生成

将 Metabase SQL 模板落地为 `pages/data/` 下的可查询页面，复用 `utils/metabase.py` + `utils/filters.py`。

## 输入

用户需提供：

1. **filename** — 页面文件名（不含 `.py`），如 `student_list`
2. **page_title** — 侧边栏标题，如 `学员列表`
3. **SQL 模板** — 代码块内的 Metabase SQL（保留 `{{param}}` / `[[ ]]`）
4. **变量说明表**：

| 变量名 | 类型 | 说明 | 是否必填 | 是否多选 |
|--------|------|------|----------|----------|
| tid | Number | 团队 ID | 必填 | 否 |

缺 filename / page_title 时先询问再继续。SQL 与变量表通常来自用户消息或 `nl2sql-metabase` 产出。

---

## 执行前必读

用 Read 工具读取（勿凭记忆）：

- `utils/filters.py` — 当前 `SESSION_KEYS`、`FILTER_REGISTRY`、已有 `_XXXX_SQL`
- `app.py` — 现有 `st.Page` 与 `data_pages` 注册方式
- 可选对照：`pages/data/*.py` 已有页面结构

---

## 工作流

```
Progress:
- [ ] 1. 提取输入并交叉校验参数
- [ ] 2. 参数分类（session / registry-match / registry-add / fallback）
- [ ] 3. 处理 registry-add（询问后写入 FILTER_REGISTRY）
- [ ] 4. 构建 fallbacks
- [ ] 5. 创建 pages/data/<filename>.py
- [ ] 6. 注册到 app.py
- [ ] 7. 输出摘要
```

### Step 1：提取输入

1. 从 SQL 代码块提取模板
2. 从变量表构建：

```
{
  "param_name": {
    "type": "Number" | "Text" | "Date",
    "required": true | false,
    "multi": true | false
  }
}
```

3. 用 `\{\{(\w+)\}\}` 提取 SQL 中全部参数，与变量表交叉校验；表中有但 SQL 无的忽略，SQL 有但表无的追问补全

### Step 2：参数分类

对照刚读取的 `SESSION_KEYS` / `FILTER_REGISTRY`：

| 类别 | 判断 | 处理 |
|------|------|------|
| session | 在 `SESSION_KEYS`（`tid`、`camp_id`） | 静默读 session，不渲染 |
| registry-match | 已在 `FILTER_REGISTRY` | 直接复用 |
| registry-add | Number + 需要 DB 选项列表 | Step 3 新增 FilterSpec |
| fallback | Text / Date，或 Number 手输单值 | 页面 `fallbacks` 内联 |

**widget（仅 registry-add）**：`multi=true` → `multiselect`；`multi=false` → `selectbox`

**fallback widget**：
- `Text` / `Date` → `text_input`（Date 的 label 注明格式，如 `YYYY-MM-DD`）
- `Number` 且非选项列表 → `number_input`

### Step 3：处理 registry-add

对每个待新增参数询问用户：

- **label**、选项 SQL（必须返回 `value`、`label` 两列）
- **session_params**（选项 SQL 用到的 session 键，如 `["tid"]`）
- **联动**：是否依赖其他参数？有则要 `depends_on` + `cascade_clause`

**注册规则：**

- 同一语义单/多选变体（如 `term_id` / `term_ids`）抽公共 `_XXXX_SQL`，两 FilterSpec 共用
- 注册顺序 = 渲染顺序：**被依赖项必须在依赖项之前**；有联动的参数写在其 `depends_on` 目标之后
- 基础选项 SQL **不加** `LIMIT`（由 `_build_options_sql` 处理联动拼接）

追加到 `FILTER_REGISTRY`（无则省略可选字段）：

```python
"<param_name>": FilterSpec(
    label="<label>",
    widget="<multiselect|selectbox>",
    sql=<_XXXX_SQL 或字符串>,
    session_params=["<key>"],
    depends_on=["<dep>", ...],
    cascade_clause="AND <col> IN ({values})",
),
```

### Step 4：构建 fallbacks

```python
fallbacks = {
    "name": {"label": "学员昵称", "widget": "text_input"},
    "account_id": {"label": "账号 ID", "widget": "number_input"},
    "start_date": {"label": "开始日期 (YYYY-MM-DD)", "widget": "text_input"},
}
```

无 fallback 参数则不传 `fallbacks=`。

### Step 5：创建页面

路径：`pages/data/<filename>.py`

```python
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters

TEMPLATE = """
<原始 Metabase SQL，保留 {{param}} 与 [[ ]]>
"""

st.title("<page_title>")

if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
    st.warning("请先登录")
    st.stop()

conn = st.connection("mysql", type="sql")

filter_values = render_filters(
    conn,
    extract_params(TEMPLATE),
    fallbacks=<dict 或省略该参数>,
)

if st.button("查询", type="primary"):
    missing = []
    # 仅校验 required=true 且非 SESSION_KEYS 的参数；展开为真实 if
    # selectbox: is None；multiselect/text/number: not value
    if not filter_values.get("<required_param>"):
        missing.append("<中文 label>")
    if missing:
        st.warning(f"请先选择：{'、'.join(missing)}")
        st.stop()

    sql, sa_params = build_sql(TEMPLATE, filter_values)

    with st.expander("执行的 SQL", expanded=False):
        st.code(format_display_sql(sql, sa_params), language="sql")

    with st.spinner("查询中..."):
        df = conn.query(sql, params=sa_params, ttl=0)

    st.metric("查询结果", f"{len(df)} 条")
    st.dataframe(df, use_container_width=True)
```

**校验规则：**

- 只对变量表 `必填` 且不在 `SESSION_KEYS` 的参数生成
- `selectbox`：`is None`；`multiselect` / fallback：`not value`
- 收集全部未填 label，一次 `st.warning` + `st.stop()`
- 无此类必填项则省略整个 `missing` 块

**图表（可选）：** 用户或上游给出图表推荐且适合时，用 tabs：

```python
tab_chart, tab_table = st.tabs(["图表", "表格"])
with tab_chart:
    st.bar_chart(df.set_index("<维列>")["<指标列>"])
with tab_table:
    st.dataframe(df, use_container_width=True)
```

仅表格场景保持单一 `st.dataframe`。

### Step 6：注册 app.py

在 `data_pages = [...]` 之前增加：

```python
<filename> = st.Page(
    "pages/data/<filename>.py",
    title="<page_title>",
    icon=":material/table_view:",  # 有图表可用 :material/bar_chart: 等
)
```

并将变量追加进 `data_pages`。

### Step 7：摘要

报告：页面路径、新增 `FILTER_REGISTRY` 项、fallback 列表、侧边栏标题。

---

## 约束

- SQL 模板保持 Metabase 原样，不改写为裸 SQL
- 不硬编码 `tid` / `camp_id`；页面只校验 session 已登录
- 未知参数勿静默 invent FilterSpec——归入 registry-add 并询问
- 改动范围：`pages/data/<filename>.py`、必要时 `utils/filters.py`、`app.py`；勿改无关文件
