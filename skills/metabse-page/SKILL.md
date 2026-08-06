---
description: 根据 Metabase SQL 模板 + 变量说明表，生成 Streamlit 数据页面。自动解析参数分类、补全 FILTER_REGISTRY、处理 fallback 筛选项，并注册到 app.py。
argument-hint: <filename> <page_title>
allowed-tools: [Read, Edit, Write, Glob, Grep, Bash]
---

# Metabase Page Generator

根据用户提供的 Metabase SQL 模板和变量说明表，生成完整的 Streamlit 数据查询页面。

## 输入

- **$ARGUMENTS** 格式：`<filename> <page_title>`
  - `filename`：页面文件名（不含 .py），如 `student_list`
  - `page_title`：页面标题（显示在侧边栏），如 `学员列表`
- **SQL 模板**：从用户消息中提取（代码块内的 SQL）
- **变量说明表**：从用户消息中提取，格式如下：

  | 变量名 | 类型 | 说明 | 是否必填 | 是否多选 |
  |--------|------|------|----------|----------|
  | tid    | Number | 团队 ID | 必填 | 否 |

若 $ARGUMENTS 缺失，先向用户询问再继续。

---

## 当前注册表（实时读取）

`utils/filters.py` 当前内容：
!`cat utils/filters.py`

`app.py` 当前内容：
!`cat app.py`

---

## 执行步骤

### Step 1：提取输入

1. 从 SQL 代码块中提取 Metabase SQL 模板
2. 从变量说明表中提取每个变量的属性，构建如下结构：

   ```
   {
     "param_name": {
       "type": "Number" | "Text",
       "required": true | false,   # 必填→true，可选→false
       "multi": true | false       # 是→true，否→false
     }
   }
   ```

3. 用正则 `\{\{(\w+)\}\}` 从 SQL 模板中提取所有参数名（与变量表交叉校验）

### Step 2：参数分类

对照实时读取的 `SESSION_KEYS` 和 `FILTER_REGISTRY`，将每个参数分为四类：

| 类别 | 判断条件 | 处理方式 |
|------|---------|---------|
| **session** | 在 `SESSION_KEYS` 中（tid、camp_id） | 自动从 session_state 读取，无需处理 |
| **registry-match** | 已在 `FILTER_REGISTRY` 中 | 直接复用，无需改动 |
| **registry-add** | 不在注册表，但 `type=Number` 且需要选项 SQL | 需要新增 FilterSpec（见 Step 3） |
| **fallback** | 简单筛选（Text 类型，或 Number 单值文本输入） | 在页面 `fallbacks` 字典中内联定义 |

**widget 类型选择规则**（仅对 registry-add 类参数）：
- `multi=true`  → `widget="multiselect"`
- `multi=false` → `widget="selectbox"`

### Step 3：处理 registry-add 参数

对需要新增的参数，询问用户：
- **label**：显示名称
- **SQL**：选项查询 SQL（必须返回 `value`、`label` 两列）
- **session_params**：SQL 中引用的 session_state 参数名列表
- **联动关系**：该参数是否依赖其他参数的已选值来缩小选项范围？如有，需提供 `depends_on` 和 `cascade_clause`

**注册规则：**
- 若同一语义的参数同时存在单选和多选变体（如 `term_id` 和 `term_ids`），提取共同 SQL 为模块级常量 `_XXXX_SQL`，两个 FilterSpec 共用，**单选在多选之后定义**（两者都不依赖其他参数时顺序不影响，但被其他参数依赖时必须排在前面）
- 有联动关系的参数（dependent）必须定义在其依赖参数（dependency）之后

在 `utils/filters.py` 的 `FILTER_REGISTRY` 末尾追加（无联动时省略后两个字段）：

```python
"<param_name>": FilterSpec(
    label="<label>",
    widget="<multiselect|selectbox>",
    sql=<_XXXX_SQL 或内联字符串>,
    session_params=["<key>"],            # 无则省略
    depends_on=["<dep_param1>", ...],   # 联动：监听的参数名
    cascade_clause="AND <col> IN ({values})",  # 联动：追加的 SQL 片段
),
```

### Step 4：构建 fallbacks 字典

对所有 fallback 类参数，根据变量说明表选择 widget 类型：
- `type=Text` → `"widget": "text_input"`
- `type=Number`, `multi=false` → `"widget": "number_input"`

示例：
```python
fallbacks = {
    "name": {"label": "学员昵称", "widget": "text_input"},
    "account_id": {"label": "账号 ID", "widget": "number_input"},
}
```

若 fallbacks 为空，则不传该参数。

### Step 5：创建页面文件

在 `pages/data/<filename>.py` 创建以下内容（SQL 模板保持 Metabase 原始语法不变）：

```python
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters

TEMPLATE = """
<原始 Metabase SQL 模板，保留 {{param}} 和 [[ ]] 语法>
"""

st.title("<page_title>")

if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
    st.warning("请先登录")
    st.stop()

conn = st.connection("mysql", type="sql")

# 若有 fallback 参数则传入 fallbacks，否则省略该参数
filter_values = render_filters(
    conn,
    extract_params(TEMPLATE),
    fallbacks=<fallbacks dict 或省略>,
)

if st.button("查询", type="primary"):
    # 必填参数校验：session 参数（tid/camp_id）之外，required=true 的参数若为 None 或空列表则阻止查询
    # 逐一检查，收集所有未填的必填项标签，统一提示
    missing = []
    <for each required non-session param p:>
        if not filter_values.get("<p>"):
            missing.append("<label of p>")
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

**必填参数校验规则（生成代码时展开伪代码）：**
- 仅对变量说明表中 `required=true` 且**不在 SESSION_KEYS** 中的参数生成校验
- `selectbox`（单选）：`filter_values.get("<p>") is None` 即为未填
- `multiselect`（多选）：`not filter_values.get("<p>")` 即为未填（空列表）
- `text_input` / `number_input`（fallback）：`not filter_values.get("<p>")` 即为未填
- 将所有未填项的 label 收集到 `missing` 列表，用 `st.warning` 一次性提示，再 `st.stop()`
- 若无任何必填参数（session 之外），则省略整个校验块

### Step 6：注册到 app.py

在 `data_pages = [...]` 定义之前插入：

```python
<filename> = st.Page(
    "pages/data/<filename>.py",
    title="<page_title>",
    icon=":material/table_view:",
)
```

并将变量追加到 `data_pages` 列表。

### Step 7：输出摘要

完成后报告：
- 创建的页面文件路径
- 新增到 `FILTER_REGISTRY` 的参数（若有）
- fallback 内联参数列表（若有）
- 页面在侧边栏的显示名称
