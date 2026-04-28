# 梨花效能数据分析平台

基于 Streamlit 构建的多页面数据分析仪表盘，用于查询和可视化学员授权、班级统计等业务数据。后端连接 StarRocks（MySQL 协议），使用 Metabase SQL 模板系统驱动各数据页面。

## 快速开始

```bash
# 安装依赖
uv sync

# 启动开发服务器
uv run streamlit run app.py
```

访问 `http://localhost:8501`，以 `Admin` 角色登录即可查看数据页面。

## 项目结构

```
data_analyse/
├── app.py                    # 入口：登录/导航注册
├── pages/
│   └── data/
│       ├── student_list.py   # 学员列表查询
│       └── class_auth_stats.py  # 班级授权统计
├── utils/
│   ├── metabase.py           # SQL 模板解析与构建
│   └── filters.py            # 筛选器注册表与渲染
└── .streamlit/
    └── secrets.toml          # 数据库连接配置（不入库）
```

## 数据库配置

在 `.streamlit/secrets.toml` 中配置 StarRocks 连接：

```toml
[connections.mysql]
dialect = "mysql"
host = "<host>"
port = 9030
database = "warehouse"
username = "<user>"
password = "<password>"
```

## 核心机制

### Metabase SQL 模板

`utils/metabase.py` 将 Metabase 风格的 SQL 模板转换为 SQLAlchemy 可执行语句：

- `{{param}}` — 命名参数，有值时替换为 `:param` 占位符
- `[[ ... {{param}} ... ]]` — 可选块，`param` 无值时整块丢弃

```python
TEMPLATE = """
SELECT * FROM students
WHERE tid = {{tid}}
[[AND term_id = {{term_id}}]]
[[AND name LIKE {{name}}]]
"""

sql, sa_params = build_sql(TEMPLATE, {"tid": 20, "term_id": 5})
# -> "SELECT * FROM students WHERE tid = :tid AND term_id = :term_id"
# -> {"tid": 20, "term_id": 5}
```

### 筛选器系统

`utils/filters.py` 的 `FILTER_REGISTRY` 统一注册所有 DB 驱动筛选项，`render_filters()` 根据当前模板参数自动渲染对应 widget。

**参数解析优先级**：`SESSION_KEYS`（`tid`/`camp_id`）→ `FILTER_REGISTRY` → `fallbacks`（页面内联）

**联动筛选**：通过 `depends_on` + `cascade_clause` 实现，例如选择期次后自动缩小班级范围：

```python
"class_ids": FilterSpec(
    label="班级",
    widget="multiselect",
    sql=_CLASS_SQL,
    depends_on=["term_ids", "term_id"],
    cascade_clause="AND camp_term_id IN ({values})",
),
```

## 新增数据页面

1. 在 `pages/data/` 下新建 `.py` 文件，按以下结构编写：

```python
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters

TEMPLATE = """SELECT ... FROM ... WHERE tid = {{tid}} [[AND term_id = {{term_id}}]]"""

conn = st.connection("mysql", type="sql")
filter_values = render_filters(conn, extract_params(TEMPLATE))

if st.button("查询", type="primary"):
    sql, sa_params = build_sql(TEMPLATE, filter_values)
    with st.expander("执行的 SQL"):
        st.code(format_display_sql(sql, sa_params), language="sql")
    with st.spinner("查询中..."):
        df = conn.query(sql, params=sa_params, ttl=0)
    st.dataframe(df, use_container_width=True)
```

2. 在 `app.py` 的 `data_pages` 列表中注册该页面：

```python
st.Page("pages/data/your_page.py", title="页面标题", icon="📊")
```

新增 DB 驱动筛选项在 `FILTER_REGISTRY` 追加 `FilterSpec`；简单文本/数字筛选通过 `fallbacks` 参数传入 `render_filters()`。

## 技术栈

| 组件 | 说明 |
|------|------|
| [Streamlit](https://streamlit.io) `>=1.56` | Web 框架与多页面路由 |
| [StarRocks](https://www.starrocks.io) | 分析型数据库（MySQL 协议） |
| [SQLAlchemy](https://www.sqlalchemy.org) `>=2.0` | SQL 参数化执行层 |
| [Altair](https://altair-viz.github.io) `>=6.1` | 图表渲染 |
| [uv](https://docs.astral.sh/uv/) | 依赖管理与运行时 |

## 开发说明

- `app.py` 顶部硬编码 `tid=20` / `camp_id=102150` 供本地调试使用
- 当前仅 `Admin` 角色可访问数据页面；新增角色需在 `app.py` 的 `page_dict` 分支中添加
- `.streamlit/secrets.toml` 已加入 `.gitignore`，不要提交数据库凭据
