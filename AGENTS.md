# AGENTS.md

本文件为仓库级 Agent 开发指引，供 Cursor、Claude Code 及其他 Agent 默认读取。

## Agent Configurations & Customizations (.agents/)

项目所有通用 Agent 规则、技能与 MCP 服务统一维护在 `.agents/` 目录：

- **MCP 配置**: `.agents/mcp_config.json`（已集成 `context7` 服务：`@upstash/context7-mcp`）
- **规则指引**:
  - `.agents/rules/context7-streamlit.md`: 涉及 Streamlit 或第三方库 API/组件变动时，优先通过 Context7 MCP 检索最新文档
- **Skills 技能库**:
  - `metabase-page` (`.agents/skills/metabase-page/SKILL.md`): 将 Metabase SQL 模板落地为 Streamlit 数据页面
  - `nl2sql-metabase` (`.agents/skills/nl2sql-metabase/SKILL.md`): 将自然语言转为 Metabase SQL 模板（依赖 `references/schema.md`）
  - `developing-with-streamlit` (`.agents/skills/developing-with-streamlit/SKILL.md`): Streamlit 应用开发与 UI 调整
  - `grill-me` / `grilling`: 方案交互讨论与需求对齐

## Commands

```bash
# 启动开发服务器
uv run streamlit run app.py

# 安装依赖
uv sync
```

## Architecture

### Entry Point

`app.py` 是唯一入口，负责：登录/登出逻辑、`st.session_state` 初始化（`role`）、侧边栏控件（`render_sidebar_controls()`：查询方式 + tid/camp_id 列表）、多页面导航注册。添加新页面时，在 `app.py` 中声明 `st.Page(...)` 并追加到 `data_pages` 列表。

侧边栏营期列表定义在 `utils/query.py` 的 `CAMP_OPTIONS`（当前仅 `{tid: 378, camp_id: 108108}`，默认第一项）；选中后写入 `session_state.tid` / `camp_id`，供 `SESSION_KEYS` 使用。勿在 `app.py` 里每轮硬编码覆盖这两个值。

### Database / 查询后端

页面与筛选器统一通过 `utils.query.get_conn()` 取连接，**勿再直接写** `st.connection("mysql")`：

| 后端 | 实现 | 场景 |
|------|------|------|
| `mysql` | `st.connection("mysql", type="sql")` | 能直连 StarRocks（MySQL 协议，port 9030） |
| `metabase` | `MetabaseQueryConn` → `/api/dataset` | 本地连不上线上库 |

配置（`.streamlit/secrets.toml`）：

- `[connections.mysql]` — 直连（`database = "warehouse"`，无 schema 前缀也可）
- `[metabase]` — `base_url` / `username` / `password` / `db_id` / `cookies_file`
- `query_backend` — 默认 `"mysql"` 或 `"metabase"`（本地无库建议后者）

侧边栏可随时覆盖默认后端。两种后端均暴露 `conn.query(sql, params=..., ttl=0) -> DataFrame`。

**表名约定（重要）**：Metabase 连接的默认库常为 `doris`，未加 schema 会报
`Table [...] does not exist in database [doris]`。  
业务 SQL / 筛选选项 SQL **一律写** `warehouse.table` 或 `` `warehouse`.`table` ``（直连同样可用）。

**相关模块**

- `utils/metabase_client.py` — 登录/cookie、`:param` 绑定为字面量、`rows`/`cols` → DataFrame；`client_from_secrets()` 读 secrets / 环境变量
- `utils/query.py` — `get_conn()`、`get_query_backend()`、`render_sidebar_controls()`（查询方式默认 Metabase + `CAMP_OPTIONS`）
- 根目录 `metabase.py` — CLI 烟雾测试（`uv run python metabase.py --sql "..."`）

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
- `FilterSpec` dataclass：`widget` 为 `"multiselect"` / `"selectbox"` / `"text_input"`；选项 SQL 必须返回 `value`（整数 ID）和 `label`（显示文本）两列；支持联动字段 `depends_on` + `cascade_clause`（见下）；支持 `default_first`（见下）
- `FILTER_REGISTRY` — DB 驱动的筛选项注册表；同一数据源的单/多选变体共享同一 SQL 常量（如 `_TERM_SQL`），分别注册为 `term_id`（selectbox）和 `term_ids`（multiselect）；**注册顺序即渲染顺序，被依赖项必须在依赖项之前**
- `SESSION_KEYS` — 从 session_state 静默读取、不渲染 widget（目前：`tid`、`camp_id`）
- `render_filters(conn, template_params, fallbacks=None)` — 按注册表渲染 widget；返回 `(values, labels)`：`values` 供 `build_sql`，`labels` 为同键可读文本（供页面文案）；`fallbacks` 传入不需要 DB 查询的简单筛选项（text_input / number_input），与注册表项统一排在同一行；`conn` 须来自 `get_conn()`

**`utils/page_copy.py`**
- `fill_template(template, **ctx)` — `str.format` 填充 `{name}`（与 Metabase `{{param}}` 分开）
- `join_labels(labels, empty="全部")` — 多选 label 拼成短句

参数分辨优先级：SESSION_KEYS → FILTER_REGISTRY → fallbacks → 忽略

**筛选区布局（`render_filters`）：**
- 使用 `st.container(horizontal=True, gap="small")` 横向排列，**不要**用通栏 `st.columns` 拉满整行
- 固定宽度：`multiselect` → `width=400`；`selectbox` / `text_input` → `width=200`
- 多选选中项过多时，依赖 Streamlit 原生标签区高度限制（约 4.5 行内滚动），无需额外 CSS

**期次默认第一项：**
- 所有期次筛选项（`term_id` / `term_ids`）在 `FILTER_REGISTRY` 中必须设 `default_first=True`
- `selectbox`：`index=0`；`multiselect`：`default=[第一项 label]`（仅首次渲染生效，之后由 widget 状态保持）
- 其他筛选项按需设置；未设时 selectbox 为「全部」(None)，multiselect 为空列表

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

约定：用页面级 `_SS_FILTERS` 冻结上次查询条件；**首次进入自动查一次**，之后改筛选不自动重查，需点「查询」才刷新。

```python
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters
from utils.query import get_conn, show_sql_and_query

TEMPLATE = """<Metabase SQL，保留 {{param}} 和 [[ ]] 语法>"""

_SS_FILTERS = "<page_name>_filters"        # 冻结筛选条件；首次进入也会写入
_SS_LABELS = "<page_name>_filter_labels"   # 与筛选一并冻结的可读 label（文案用）

conn = get_conn()
filter_values, filter_labels = render_filters(
    conn,
    extract_params(TEMPLATE),
    fallbacks={"name": {"label": "学员昵称", "widget": "text_input"}},  # 简单参数内联
)

# 查询按钮右对齐；点击后冻结当前筛选与 labels
with st.container(horizontal_alignment="right"):
    if st.button("查询", type="primary"):
        st.session_state[_SS_FILTERS] = filter_values
        st.session_state[_SS_LABELS] = filter_labels

# 首次进入：用当前默认筛选自动查一次
if _SS_FILTERS not in st.session_state:
    st.session_state[_SS_FILTERS] = filter_values
    st.session_state[_SS_LABELS] = filter_labels

saved_filters = st.session_state[_SS_FILTERS]
saved_labels = st.session_state.get(_SS_LABELS, {})
sql, sa_params = build_sql(TEMPLATE, saved_filters)
# ... expander / spinner / dataframe 见「页面结果展示惯例」
```

- `multiselect` → `values` 为 `list[int]`（`build_sql` 内联为 `IN (1,2,3)`），`labels` 为 `list[str]`
- `selectbox` → `values` 为 `int | None`（`None` 时可选块自动丢弃），`labels` 为 `str | None`
- 文案展示必须用冻结后的 `saved_labels`，与 `saved_filters` 同步写入，勿用未点「查询」的当前控件值
- 新增 DB 驱动筛选：在 `FILTER_REGISTRY` 追加 `FilterSpec`；简单文本/数字筛选：直接写入页面 `fallbacks`
- 新增联动筛选：在被依赖项之后添加带 `depends_on` + `cascade_clause` 的 `FilterSpec`，基础 SQL 中不加 `LIMIT`（由 `_build_options_sql` 统一追加）
- `FilterSpec.session_params` — 列出需要透传给选项 SQL 的 session_state 键（如 `["tid"]`），render 时自动注入为 named params
- 新增期次相关筛选项时：务必 `default_first=True`

### 页面结果展示惯例

```python
_SS_FILTERS = "<page_name>_filters"
_SS_LABELS = "<page_name>_filter_labels"

with st.container(horizontal_alignment="right"):
    if st.button("查询", type="primary"):
        st.session_state[_SS_FILTERS] = filter_values
        st.session_state[_SS_LABELS] = filter_labels

if _SS_FILTERS not in st.session_state:
    st.session_state[_SS_FILTERS] = filter_values
    st.session_state[_SS_LABELS] = filter_labels

saved_filters = st.session_state[_SS_FILTERS]
# 必填校验（如仍可能为空时）
if not saved_filters.get("term_id"):
    st.warning("请先选择期次")
    st.stop()

sql, sa_params = build_sql(TEMPLATE, saved_filters)

# 先展示 SQL；失败时 SQL 仍保留，并 st.error
df = show_sql_and_query(conn, sql, sa_params, ttl=0)

# 若同时需要图表和表格：
tab_chart, tab_table = st.tabs(["图表", "表格"])
with tab_chart:
    st.bar_chart(df.set_index("col_name")["value_col"])
with tab_table:
    st.dataframe(df, width="stretch", hide_index=True)
```

- **首次进入自动查询**：页面加载时若 `_SS_FILTERS` 尚未写入，立即用当前 `filter_values`（含期次默认第一项）冻结并执行查询；之后仅点「查询」才更新冻结条件
- `number_input` fallback 实际渲染为 `st.text_input`，输入非纯数字时返回 `None`（已在 `render_filters` 内处理）
- SQL 展示顺序：统一 `show_sql_and_query`（先 expander 再 query；失败不吞掉 SQL）
- 筛选选项查询失败时 `render_filters` 仅 warning + 空选项，不阻断整页
- **禁止**使用已废弃的 `use_container_width`；改用 `width="stretch"` / `width="content"` / 像素值
- 表格统一 `hide_index=True`；一般不必再展示「查询结果 N 条」metric（分页列表用底栏「共 N 条」即可）

**说明 / KPI / 模板洞察（参考 `class_auth_stats` / `student_list`）：**
- 占位顺序：标题 → **静态简介** → 筛选/查询 → SQL expander →（统计页）**KPI metric + 洞察段落** /（列表页）**摘要 caption** → 图表或表格
- 文案模板写在各页常量；动态位用 `fill_template` + 冻结后的 `saved_labels` 与 `df`（或 COUNT）汇总；勿用未点「查询」的当前控件值
- 点「查询」/首次冻结时，`values` 与 `labels` 必须一并写入 session
- `df` 为空时不渲染洞察段，统一 `st.info("暂无数据")`；本阶段不做 LLM 文案

### 列表分页页布局惯例（参考 `pages/data/student_list.py`）

适用于需要 SQL 分页的列表页：筛选 → 查询 → 结果区（SQL / 表格 / 底部分页栏）。

**查询与首次自动加载**
- 筛选下方单独一行，`st.container(horizontal_alignment="right")` 右对齐
- 点击「查询」：写入 `_SS_FILTERS` 与 `_SS_LABELS`，并将 `_SS_PAGE` 置为 `1`
- 首次进入：若 `_SS_FILTERS` 不存在，写入当前 `filter_values` / `filter_labels`，随即走结果区逻辑

**结果区占位顺序（官方 empty + pagination）**
1. 声明 `sql_slot = st.empty()`、`dataframe_slot = st.empty()`
2. 再渲染底部分页栏（需要先拿到 `page` 才能算 `OFFSET`）
3. 最后用占位符填入 SQL expander 与 `dataframe`

**底部分页栏（三列 `[2, 3, 2]`，`vertical_alignment="center"`）**

| 位置 | 内容 |
|------|------|
| 左列 | 留空（平衡居中） |
| 中列 | `st.pagination`，外层 `horizontal_alignment="center"` |
| 右列 | `共 {total} 条` → 每页条数；顺序固定，靠右 |

右列细节：
```python
with st.container(
    horizontal=True,
    horizontal_alignment="right",
    vertical_alignment="center",
    gap="xsmall",
):
    st.caption(f"共 {total} 条", width="content")  # 必须 content，否则 stretch 会撑开间距
    st.selectbox(
        "每页条数",
        PAGE_SIZE_OPTIONS,
        key=...,
        label_visibility="collapsed",
        width=80,
    )
```

- `st.caption` 默认 `width="stretch"`，会把与每页条数之间的空隙拉得很开；务必 `width="content"`
- 每页条数选择框固定 `width=80`，标签折叠
- 右列两项间距用 `gap="xsmall"`（或更小），不要用默认 `small`
- **分页 / 每页条数 widget**：值只通过 `key` + `session_state` 管理；不要同时传 `default` / `index`，否则会触发
  `created with a default value but also had its value set via the Session State API` 告警
- **`st.pagination` 有内置 `default=1`**：首次渲染前**不要**预写 `session_state[page_key]`（含 `setdefault`）；
  仅在 widget 已存在后的后续 rerun 里重置（点「查询」、改每页条数）。首次记录 `_SS_SIZE_PREV` 不算变更，避免误写页码

### 注释约定

- 调整页面 / 布局 / 筛选相关代码时，**尽量同步补充注释**，说明「为什么这样写」（尤其是布局顺序、width、session_state 与 widget 参数取舍等易踩坑点）
- 优先注释非显而易见的约束（如 empty 占位顺序、禁止 `default`+`key` 双设、首次自动查询与冻结筛选）；避免复述代码字面意思
- 列表分页类新页可对照 `pages/data/student_list.py` 的注释风格；图表统计类可对照 `pages/data/class_auth_stats.py`

### 开发注意事项

- 本地 tid/camp_id 由侧边栏 `CAMP_OPTIONS` 选择；正式环境登录流程应从用户选择中写入这两个值
- 当前只有 `role == "Admin"` 时才显示数据页面；新增角色需在 `app.py` 的 `page_dict` 分支中添加
- 新页面一律 `from utils.query import get_conn` + `conn = get_conn()`；筛选器传入的 `conn` 也须同源，保证选项 SQL 与业务查询后端一致
- 查询后端默认 `metabase`；可在 secrets 设 `query_backend = "mysql"` 或侧边栏切换；`cookies.txt` 勿提交
- 验证 Metabase 通道：`uv run python metabase.py --sql "select 1 as n"`
- 新增调试营期：在 `utils/query.py` 的 `CAMP_OPTIONS` 追加 `{"tid": ..., "camp_id": ...}`
