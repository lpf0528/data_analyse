# 梨花效能数据分析平台

基于 Streamlit 构建的多页面数据分析仪表盘，用于查询和可视化学员授权、班级统计等业务数据。  
SQL 模板沿用 Metabase 语法；查询可走 **StarRocks 直连** 或 **Metabase API**（本地连不上线上库时用后者）。

## 快速开始

```bash
# 安装依赖
uv sync

# 启动开发服务器
uv run streamlit run app.py

# （可选）CLI：经 Metabase 跑一条 SQL，验证账号与 cookie
uv run python metabase.py
uv run python metabase.py --sql "select 1 as n"
```

访问 `http://localhost:8501`，以 `Admin` 角色登录即可查看数据页面。  
侧边栏「查询方式」可在 **数据库（StarRocks）** 与 **Metabase API** 之间切换。

## 项目结构

```
data_analyse/
├── app.py                      # 入口：登录/导航/查询方式切换
├── metabase.py                 # Metabase 查询 CLI（复用 client）
├── pages/
│   └── data/
│       ├── student_list.py     # 学员列表（分页）
│       ├── class_auth_stats.py # 班级授权统计
│       └── category_refund_stats.py  # 品类退款分析
├── utils/
│   ├── metabase.py             # SQL 模板解析（{{param}} / [[ ]]）
│   ├── metabase_client.py      # Metabase API：登录、查询、结果转 DataFrame
│   ├── query.py                # get_conn()：mysql / metabase 统一入口
│   ├── filters.py              # 筛选器注册表与渲染
│   └── page_copy.py            # 页面文案填充
└── .streamlit/
    └── secrets.toml            # 连接与 Metabase 配置（不入库）
```

## 配置（secrets.toml）

在 `.streamlit/secrets.toml` 中配置：

```toml
[connections.mysql]
dialect = "mysql"
host = "<host>"
port = 9030
database = "warehouse"
username = "<user>"
password = "<password>"

# 默认查询后端：mysql（直连）或 metabase（经 API）
# 本地无库建议 metabase；侧边栏仍可随时切换
query_backend = "metabase"

[metabase]
base_url = "https://metabase.goweike.cn"
username = "<metabase-user>"
password = "<metabase-password>"
db_id = 246
cookies_file = "cookies.txt"
```

也可用环境变量覆盖 Metabase 账号（CLI / 无 secrets 时）：

- `METABASE_USERNAME` / `METABASE_PASSWORD`
- `METABASE_BASE_URL` / `METABASE_DB_ID` / `METABASE_COOKIES_FILE`

`cookies.txt` 为本地会话缓存，已加入 `.gitignore`，勿提交。

## 查询后端切换

| 方式 | 实现 | 适用场景 |
|------|------|----------|
| `mysql` | `st.connection("mysql", type="sql")` | 能直连 StarRocks（如内网） |
| `metabase` | `utils.metabase_client` → `/api/dataset` | 本地无法连线上库 |

页面与筛选器统一：

```python
from utils.query import get_conn

conn = get_conn()
df = conn.query(sql, params=sa_params, ttl=0)  # 两种后端签名一致
```

- `app.py` 调用 `render_query_backend_selector()` 渲染侧边栏切换
- Metabase 路径会把 `:param` 绑定为 SQL 字面量，并将返回的 `rows` / `cols` 转为 `pandas.DataFrame`
- 切换后端后整页 rerun，筛选选项与业务查询都会走新后端
- **表名必须带 `warehouse.`**：Metabase 默认库常为 `doris`，无前缀会报
  `Table [...] does not exist in database [doris]`；直连同样兼容带前缀写法

## 核心机制

### Metabase SQL 模板

`utils/metabase.py` 将 Metabase 风格的 SQL 模板转换为可执行语句 + 参数字典：

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

`utils/filters.py` 的 `FILTER_REGISTRY` 统一注册所有 DB 驱动筛选项，`render_filters(conn, ...)` 根据当前模板参数自动渲染对应 widget。  
`conn` 必须来自 `get_conn()`，以便选项 SQL 也走当前查询后端。

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

1. 在 `pages/data/` 下新建 `.py` 文件，按以下结构编写（完整约定见 `AGENTS.md`）：

```python
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters
from utils.query import get_conn

TEMPLATE = """SELECT ... FROM ... WHERE tid = {{tid}} [[AND term_id = {{term_id}}]]"""

conn = get_conn()
filter_values, filter_labels = render_filters(conn, extract_params(TEMPLATE))

if st.button("查询", type="primary"):
    sql, sa_params = build_sql(TEMPLATE, filter_values)
    with st.expander("执行的 SQL"):
        st.code(format_display_sql(sql, sa_params), language="sql")
    with st.spinner("查询中..."):
        df = conn.query(sql, params=sa_params, ttl=0)
    st.dataframe(df, width="stretch", hide_index=True)
```

2. 在 `app.py` 的 `data_pages` 列表中注册该页面：

```python
st.Page("pages/data/your_page.py", title="页面标题", icon=":material/bar_chart:")
```

新增 DB 驱动筛选项在 `FILTER_REGISTRY` 追加 `FilterSpec`；简单文本/数字筛选通过 `fallbacks` 传入 `render_filters()`。

## 技术栈

| 组件 | 说明 |
|------|------|
| [Streamlit](https://streamlit.io) `>=1.61` | Web 框架与多页面路由 |
| [StarRocks](https://www.starrocks.io) | 分析型数据库（MySQL 协议） |
| [Metabase](https://www.metabase.com) | 可选查询通道（`/api/dataset`） |
| [SQLAlchemy](https://www.sqlalchemy.org) `>=2.0` | 直连时的 SQL 参数化执行 |
| [requests](https://requests.readthedocs.io) | Metabase HTTP 客户端 |
| [pandas](https://pandas.pydata.org) | Metabase 结果转表 |
| [Altair](https://altair-viz.github.io) `>=6.1` | 图表渲染 |
| [uv](https://docs.astral.sh/uv/) | 依赖管理与运行时 |

## 开发说明

- `app.py` 顶部硬编码 `tid=20` / `camp_id=102150` 供本地调试；正式环境应由登录流程写入
- 当前仅 `Admin` 角色可访问数据页面；新增角色需在 `app.py` 的 `page_dict` 分支中添加
- 新页面一律 `get_conn()`，**不要**再写 `st.connection("mysql", ...)`
- **禁止**已废弃的 `use_container_width`，改用 `width="stretch"` / `width="content"` / 像素值
- `.streamlit/secrets.toml`、`cookies.txt` 已加入 `.gitignore`，不要提交凭据与会话文件
- Agent / 页面约定详见仓库根目录 `AGENTS.md`
