---
name: metabase-page
description: >
  根据 Metabase SQL 模板与变量说明表，生成 Streamlit 数据查询页面：解析参数分类、
  询问页面风格（Dashboard / Report / List）、补全 FILTER_REGISTRY、处理 fallback 筛选项，并注册到 app.py。
  在用户提供 Metabase SQL + 变量表、要求新建/生成数据页面，或从 nl2sql-metabase
  下游落地 Streamlit 页面时使用。（兼容别名 metabse-page）
disable-model-invocation: true
---

# Metabase → Streamlit 页面生成

将 Metabase SQL 模板落地为 `pages/data/` 下的可查询页面，复用 `utils/metabase.py` + `utils/filters.py` + `utils.query.get_conn()`。

查询必须走 `get_conn()`（支持侧边栏在 StarRocks 直连 / Metabase API 间切换），**禁止**再写 `st.connection("mysql", ...)`。详见 `AGENTS.md`「Database / 查询后端」与 `README.md`。

## 输入

用户需提供：

1. **filename** — 页面文件名（不含 `.py`），如 `student_list`
2. **page_title** — 侧边栏标题，如 `学员列表`
3. **SQL 模板** — 代码块内的 Metabase SQL（保留 `{{param}}` / `[[ ]]`）
4. **变量说明表**：

| 变量名 | 类型 | 说明 | 是否必填 | 是否多选 |
|--------|------|------|----------|----------|
| tid | Number | 团队 ID | 必填 | 否 |

5. **page_style (可选)** — 页面风格（Dashboard 统计看板 / Report 分析报告 / List 明细列表）。

> 💡 **风格询问规则**：若用户未指定 `page_style`，在生成代码前**必须询问用户**，提供风格选项供用户选择后再执行。

---

## 页面风格选项说明

当用户未说明页面风格时，提供以下 3 种风格供用户选择：

### 风格 1：标准统计看板（Dashboard 风格）
- **适用场景**：日常指标监控、多维筛选交互对比。
- **布局顺序**：标题与简介 → 横向筛选区 → 右对齐「查询」按钮 → SQL 展开框 → KPI Cards 汇总卡片 → Tabs 切换（图表 / 表格）。

### 风格 2：分析报告文档（Report Document 风格，参考 `category_refund_stats`）
- **适用场景**：专题汇报、深度分析、带有结论总结的报告。
- **布局顺序**：
  1. 📄 报告 Header（含分析专题、`tid/camp_id` 上下文、密级说明）
  2. 📝 带边框卡片的报告前言与概述（`st.container(border=True)`）
  3. 📋 带边框卡片包裹的查询参数配置，内含「生成分析报告」主操作按钮
  4. 一、核心指标概览（带边框卡片包裹 KPI Metrics）
  5. 二、核心结论与风险洞察（带边框卡片包裹高亮洞察与集中度分析）
  6. 三、周度/多维对比与明细数据（Tabs 切换：风险/对比图 + 明细表格 + 附录 SQL 展开框）
  7. 页脚分割线与免责/来源声明

### 风格 3：明细列表工具（List 风格，参考 `student_list`）
- **适用场景**：学员明细、订单列表、带分页的查询清单。
- **布局顺序**：标题与简介 → 筛选区 → 右对齐「查询」按钮 → 结果条数摘要 Caption → SQL 展开框 → 结果 Dataframe 表格 → 底部分页栏。

---

## 执行前必读

用 Read 工具读取（勿凭记忆）：

- `utils/filters.py` — 当前 `SESSION_KEYS`、`FILTER_REGISTRY`、已有 `_XXXX_SQL`
- `utils/query.py` — `get_conn()` 用法（勿直连 `st.connection`）
- `app.py` — 现有 `st.Page` 与 `data_pages` 注册方式
- 可选对照：`pages/data/*.py` 已有页面结构

---

## 工作流

```
Progress:
- [ ] 1. 提取输入并交叉校验参数
- [ ] 2. 确认页面风格（未说明时询问用户）
- [ ] 3. 参数分类（session / registry-match / registry-add / fallback）
- [ ] 4. 处理 registry-add（询问后写入 FILTER_REGISTRY）
- [ ] 5. 构建 fallbacks
- [ ] 6. 创建 pages/data/<filename>.py
- [ ] 7. 注册到 app.py
- [ ] 8. 输出摘要
```

### Step 1：提取输入

1. 从 SQL 代码块提取模板
2. 从变量表构建参数字典
3. 用 `\{\{(\w+)\}\}` 提取 SQL 中全部参数，与变量表交叉校验

### Step 2：确认页面风格

若用户未明确说明想要的页面风格（Dashboard / Report / List）：
- 向用户展示 3 种页面风格及其适用场景，等待用户选择后再继续。

### Step 3：参数分类

对照 `SESSION_KEYS` / `FILTER_REGISTRY` 进行分类（session / registry-match / registry-add / fallback）。

### Step 4：处理 registry-add

针对未在 `FILTER_REGISTRY` 中注册的 DB 驱动参数，补充 `FilterSpec`。

### Step 5：构建 fallbacks

构建文本/日期等简单的内联 fallback 参数。

### Step 6：创建页面

根据选定的页面风格创建 `pages/data/<filename>.py`。

#### 核心数据查询机制（必须遵循）：
- **仅在点击「查询」/「生成分析报告」按钮时触发数据查询**：
  ```python
  _SS_FILTERS = "<filename>_filters"
  _SS_LABELS = "<filename>_filter_labels"
  _SS_DF = "<filename>_df"
  _SS_SQL_PARAMS = "<filename>_sql_params"
  ```
- 点击按钮时执行 `df = conn.query(sql, params=sa_params, ttl=0)` 并存入 `st.session_state[_SS_DF]`。
- 填充数值列的 `None` / `NaN`：
  ```python
  for col in num_cols:
      if col in df.columns:
          df[col] = df[col].fillna(0).astype(int)
  ```
- 再次 rerun / 切换 Tab 时直接复用 `st.session_state[_SS_DF]`，不重复向后端发送请求。

### Step 7：注册 app.py

在 `app.py` 中注册 `st.Page` 并加入 `data_pages` 列表。

### Step 8：摘要

报告页面路径、新增 `FILTER_REGISTRY` 项、选定的页面风格与侧边栏标题。
