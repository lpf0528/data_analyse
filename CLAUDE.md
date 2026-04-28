# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# 启动开发服务器
uv run streamlit run app.py

# 安装依赖
uv sync
```

## Architecture

### Entry Point

`app.py` 是唯一入口，负责：登录/登出逻辑、`st.session_state` 初始化（`role`、`tid`、`camp_id`）、多页面导航注册。添加新页面时，在 `app.py` 中声明 `st.Page(...)` 并追加到 `data_pages` 列表。

### Database

通过 `st.connection("mysql", type="sql")` 连接 StarRocks（MySQL 协议，port 9030），配置位于 `.streamlit/secrets.toml`，database 为 `warehouse`。SQL 中直接使用表名无需加 schema 前缀。

### Metabase 模板系统（`utils/`）

项目的核心抽象层，允许将 Metabase SQL 模板直接用于 Streamlit 页面。

**`utils/metabase.py`**
- `extract_params(template)` — 提取模板中所有 `{{param}}` 参数名
- `build_sql(template, values)` — 将模板转换为 SQLAlchemy SQL + params dict：
  - `[[ ... {{param}} ... ]]` 可选块：param 无值时整块丢弃
  - 列表值（IN 子句）直接内联为整数字符串
  - 标量值变为 `:param` 占位符
- `format_display_sql(sql, sa_params)` — 将 `:param` 替换回实际值，用于页面展示

**`utils/filters.py`**
- `FilterSpec` dataclass：`widget` 为 `"multiselect"` / `"selectbox"` / `"text_input"`；选项 SQL 必须返回 `value`（整数 ID）和 `label`（显示文本）两列；支持联动字段 `depends_on` + `cascade_clause`（见下）
- `FILTER_REGISTRY` — DB 驱动的筛选项注册表；同一数据源的单/多选变体共享同一 SQL 常量（如 `_TERM_SQL`），分别注册为 `term_id`（selectbox）和 `term_ids`（multiselect）；**注册顺序即渲染顺序，被依赖项必须在依赖项之前**
- `SESSION_KEYS` — 从 session_state 静默读取、不渲染 widget（目前：`tid`、`camp_id`）
- `render_filters(conn, template_params, fallbacks=None)` — 按注册表渲染 widget；`fallbacks` 传入不需要 DB 查询的简单筛选项（text_input / number_input），与注册表项统一排列在同一行 columns 中

参数分辨优先级：SESSION_KEYS → FILTER_REGISTRY → fallbacks → 忽略

**联动筛选（Cascading Filters）：**

`FilterSpec` 的两个可选字段：
- `depends_on: list[str]` — 监听的参数名列表，取其已选值的并集
- `cascade_clause: str` — 有值时追加到选项 SQL 末尾，`{values}` 替换为逗号分隔的整数 ID

```python
# 示例：class_ids 在选了 term_ids/term_id 后自动缩小班级范围
"class_ids": FilterSpec(
    label="班级",
    widget="multiselect",
    sql=_CLASS_SQL,                          # 基础选项 SQL（不含 LIMIT）
    depends_on=["term_ids", "term_id"],      # 任一有值即触发
    cascade_clause="AND camp_term_id IN ({values})",
),
```

`_build_options_sql(spec, current_values)` 在渲染时动态拼接最终选项 SQL。

### 新建数据页面的标准结构

```python
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters

TEMPLATE = """<Metabase SQL，保留 {{param}} 和 [[ ]] 语法>"""

conn = st.connection("mysql", type="sql")
filter_values = render_filters(
    conn,
    extract_params(TEMPLATE),
    fallbacks={"name": {"label": "学员昵称", "widget": "text_input"}},  # 简单参数内联
)

if st.button("查询", type="primary"):
    sql, sa_params = build_sql(TEMPLATE, filter_values)
    st.code(format_display_sql(sql, sa_params), language="sql")
    df = conn.query(sql, params=sa_params, ttl=0)
```

- `multiselect` → 返回 `list[int]`，`build_sql` 内联为 `IN (1,2,3)`
- `selectbox` → 返回 `int | None`，`None` 时可选块自动丢弃
- 新增 DB 驱动筛选：在 `FILTER_REGISTRY` 追加 `FilterSpec`；简单文本/数字筛选：直接写入页面 `fallbacks`
- 新增联动筛选：在被依赖项之后添加带 `depends_on` + `cascade_clause` 的 `FilterSpec`，基础 SQL 中不加 `LIMIT`（由 `_build_options_sql` 统一追加）
- `FilterSpec.session_params` — 列出需要透传给选项 SQL 的 session_state 键（如 `["tid"]`），render 时自动注入为 named params

### 页面结果展示惯例

```python
if st.button("查询", type="primary"):
    # 必填校验（如 selectbox 必须有值）
    if not filter_values.get("term_id"):
        st.warning("请先选择期次")
        st.stop()

    sql, sa_params = build_sql(TEMPLATE, filter_values)

    with st.expander("执行的 SQL", expanded=False):   # 或 expanded=True
        st.code(format_display_sql(sql, sa_params), language="sql")

    with st.spinner("查询中..."):
        df = conn.query(sql, params=sa_params, ttl=0)

    st.metric("查询结果", f"{len(df)} 条")

    # 若同时需要图表和表格：
    tab_chart, tab_table = st.tabs(["图表", "表格"])
    with tab_chart:
        st.bar_chart(df.set_index("col_name")["value_col"])
    with tab_table:
        st.dataframe(df, use_container_width=True)
```

- `number_input` fallback 实际渲染为 `st.text_input`，输入非纯数字时返回 `None`（已在 `render_filters` 内处理）
- SQL 展示顺序：先 expander 再 spinner/dataframe（避免结果出现前看不到 SQL）

### 开发注意事项

- `app.py` 顶部硬编码了 `tid=20` / `camp_id=102150` 供本地开发使用；正式环境登录流程应从用户选择中写入这两个值
- 当前只有 `role == "Admin"` 时才显示数据页面；新增角色需在 `app.py` 的 `page_dict` 分支中添加

