"""
Metabase 模板页面的筛选器注册表。

注册规则：
- FILTER_REGISTRY：需要查询数据库获取选项的参数。
  - widget="multiselect"  → {{param_ids}} 风格，返回 list，用于 IN 子句
  - widget="selectbox"    → {{param_id}}  风格，返回 int | None，用于 = 子句
- SESSION_KEYS：从 st.session_state 静默读取，不渲染 widget（tid、camp_id）。
- 其他参数：通过 fallbacks 传入 render_filters()，渲染为简单内联 widget。

联动筛选：
- depends_on：监听的参数名列表，任一有值即触发联动
- cascade_clause：有值时追加到选项 SQL 末尾，{values} 替换为逗号分隔的整数 ID
  示例："AND camp_term_id IN ({values})"
- FILTER_REGISTRY 的注册顺序即渲染顺序，被依赖项必须在依赖项之前
"""
import streamlit as st
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# 共享 SQL 片段（多选/单选变体复用同一查询）
# ---------------------------------------------------------------------------

# 期次选项：按 rank 筛选，显示"第N期 (ID:x)"
_TERM_SQL = (
    "SELECT id AS value,"
    " CONCAT('第', `rank`, '期 (ID:', id, ')') AS label"
    " FROM dim_lh_teaching_class_term"
    " WHERE tid = :tid AND `rank` IN (84, 71)"
)

# 班级选项：按 ID 白名单过滤，排除空名称
_CLASS_SQL = (
    "SELECT id AS value, class_name AS label"
    " FROM dwd_lh_classes"
    " WHERE id IN (10060654, 10055057, 10060762) AND class_name <> ''"
)
# 自然周选项：按 ID 白名单过滤，排除空名称
_WEEK_SQL = (
    "SELECT id AS value,"
    "CONCAT(`year`,'年',`month`,'月第',`week`, '周 (', DATE(`start_time`),'~' ,DATE(`end_time`),')') AS label "
    "FROM lh_teaching_weeks_conf "
    "WHERE tid = :tid order by end_time desc"
)

# ---------------------------------------------------------------------------
# 注册表数据结构
# ---------------------------------------------------------------------------


@dataclass
class FilterSpec:
    label: str
    widget: Literal["multiselect", "selectbox", "text_input"]
    # multiselect / selectbox 必须提供，选项 SQL 须返回 value（整数 ID）和 label 两列
    sql: str | None = None
    # 需要透传给选项 SQL 的 session_state 键（如 ["tid"]）
    session_params: list[str] = field(default_factory=list)
    # 联动：监听的参数名列表，任一有值即缩小本筛选项的范围
    depends_on: list[str] = field(default_factory=list)
    # 联动时追加到选项 SQL 末尾的 WHERE 子句，{values} 为逗号分隔的整数 ID
    cascade_clause: str | None = None


FILTER_REGISTRY: dict[str, FilterSpec] = {
    # 期次 — 多选（必须在班级之前注册，班级联动依赖其值）
    "term_ids": FilterSpec(
        label="期次",
        widget="multiselect",
        sql=_TERM_SQL,
        session_params=["tid"],
    ),
    # 期次 — 单选
    "term_id": FilterSpec(
        label="期次",
        widget="selectbox",
        sql=_TERM_SQL,
        session_params=["tid"],
    ),
    # 班级 — 多选（联动期次，选了期次后自动缩小班级范围）
    "class_ids": FilterSpec(
        label="班级",
        widget="multiselect",
        sql=_CLASS_SQL,
        depends_on=["term_ids", "term_id"],
        cascade_clause="AND camp_term_id IN ({values})",
    ),
    # 班级 — 单选
    "class_id": FilterSpec(
        label="班级",
        widget="selectbox",
        sql=_CLASS_SQL,
        depends_on=["term_ids", "term_id"],
        cascade_clause="AND camp_term_id IN ({values})",
    ),
    "week_id": FilterSpec(
        label="自然周",
        widget="selectbox",
        sql=_WEEK_SQL,
        session_params=["tid"]
    ),
    "start_week_id": FilterSpec(
        label="自然周",
        widget="selectbox",
        sql=_WEEK_SQL,
        session_params=["tid"]
    ),
    "end_week_id": FilterSpec(
        label="自然周",
        widget="selectbox",
        sql=_WEEK_SQL,
        session_params=["tid"]
    ),
}

# 从 session_state 静默读取的参数，不渲染任何 widget
SESSION_KEYS: set[str] = {"tid", "camp_id"}

# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

FallbackSpec = dict  # {"label": str, "widget": "text_input" | "number_input"}


def _build_options_sql(spec: FilterSpec, current_values: dict) -> str:
    """根据已选的依赖值动态拼接联动 SQL。无依赖或依赖未选时返回原始 SQL。"""
    if not spec.cascade_clause or not spec.depends_on:
        return f"{spec.sql}"

    # 收集所有依赖参数的已选 ID
    dep_ids: list[int] = []
    for dep in spec.depends_on:
        val = current_values.get(dep)
        if isinstance(val, list):
            dep_ids.extend(val)
        elif isinstance(val, int):
            dep_ids.append(val)

    if not dep_ids:
        return f"{spec.sql}"

    # 将依赖 ID 列表注入联动子句
    clause = spec.cascade_clause.format(
        values=", ".join(str(i) for i in dep_ids))
    return f"{spec.sql} {clause}"


# ---------------------------------------------------------------------------
# 筛选器渲染
# ---------------------------------------------------------------------------


def render_filters(
    conn,
    template_params: set[str],
    fallbacks: dict[str, FallbackSpec] | None = None,
) -> dict:
    """
    为 template_params 中涉及的参数渲染筛选 widget，返回 {param: value} 字典供 build_sql() 使用。

    参数解析优先级：
      1. SESSION_KEYS    → 从 st.session_state 读取，不渲染 widget
      2. FILTER_REGISTRY → 渲染 DB 驱动的 multiselect 或 selectbox
                           （注册顺序即渲染顺序，依赖项须在被依赖项之前）
      3. fallbacks       → 渲染简单内联 widget（text_input 等）
      4. 未知参数         → 静默忽略
    """
    values: dict = {}
    fallbacks = fallbacks or {}

    # 1. 从 session_state 读取会话参数
    for key in SESSION_KEYS:
        if key in template_params:
            values[key] = st.session_state.get(key)

    # 2 + 3. 确定需要渲染 widget 的参数列表
    active_registry = [p for p in FILTER_REGISTRY if p in template_params]
    active_fallback = [
        p for p in fallbacks
        if p in template_params and p not in FILTER_REGISTRY and p not in SESSION_KEYS
    ]
    all_active = active_registry + active_fallback
    if not all_active:
        return values

    # 所有 widget 排列在同一行的等宽列中
    cols = st.columns(len(all_active))

    # 按注册表顺序渲染 DB 驱动筛选项；values 逐步更新，使联动项能读到依赖值
    for col, param in zip(cols, active_registry):
        spec = FILTER_REGISTRY[param]
        # 将 session_params 中声明的 session key 透传给选项查询
        query_params = {k: st.session_state.get(
            k) for k in spec.session_params}
        options_sql = _build_options_sql(spec, values)

        with col:
            if spec.widget == "multiselect":
                opt_df = conn.query(options_sql, params=query_params, ttl=300)
                # 构建 label → value 映射，保持选项顺序
                opt_map: dict = dict(
                    zip(opt_df["label"], opt_df["value"].astype(int)))
                selected = st.multiselect(spec.label, list(opt_map.keys()))
                values[param] = [opt_map[s] for s in selected]

            elif spec.widget == "selectbox":
                opt_df = conn.query(options_sql, params=query_params, ttl=300)
                opt_map = dict(
                    zip(opt_df["label"], opt_df["value"].astype(int)))
                chosen = st.selectbox(
                    spec.label,
                    options=list(opt_map.keys()),
                    index=None,
                    placeholder="全部",
                )
                # 未选时返回 None，build_sql 会丢弃对应可选块
                values[param] = opt_map[chosen] if chosen is not None else None

            elif spec.widget == "text_input":
                values[param] = st.text_input(spec.label)

    # 渲染 fallback 简单参数（排在注册表参数之后的列）
    for col, param in zip(cols[len(active_registry):], active_fallback):
        fb = fallbacks[param]
        with col:
            widget = fb.get("widget", "text_input")
            label = fb.get("label", param)
            if widget == "number_input":
                # 用 text_input 接收输入，非纯数字时返回 None 而非报错
                raw = st.text_input(label, placeholder="留空表示不筛选")
                values[param] = int(raw) if raw.strip().isdigit() else None
            else:
                values[param] = st.text_input(label)

    return values
