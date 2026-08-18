---
description: 通过 Context7 拉取最新 Streamlit / 第三方库文档后再写代码
alwaysApply: true
---

# Context7 文档查询

涉及以下场景时，先用 Context7 MCP 查文档，再写或改代码，不要只靠训练记忆：

- Streamlit API、组件用法、参数变更（如 `st.pagination`、`st.dataframe`、`width` 等）
- 第三方库的 API 参考、配置示例、升级后的破坏性变更

## Streamlit（本项目主栈）

优先查询库：`/streamlit/docs`

典型触发：`pages/**/*.py`、`app.py`、筛选/分页/图表等页面交互。

## 用法

1. 用 Context7 解析并拉取相关文档（可带 topic，如 `pagination`、`dataframe`）
2. 按当前项目已安装的 Streamlit 版本（见 `pyproject.toml` / 环境）选用对应 API
3. 再落地到本仓库惯例（Metabase 模板、`render_filters`、SQL 分页等）

用户说 `use context7` 或明确要查库文档时，必须走 Context7。
