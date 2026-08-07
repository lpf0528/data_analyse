"""
Metabase 模板页面的筛选器注册表。

注册规则：
- FILTER_REGISTRY：需要查询数据库获取选项的参数。
  - widget="multiselect"  → {{param_ids}} 风格，返回 list，用于 IN 子句
  - widget="selectbox"    → {{param_id}}  风格，返回 int | None，用于 = 子句
  - default_first=True    → 有选项时默认选中第一项（期次 term_id/term_ids 一律开启）
- SESSION_KEYS：从 st.session_state 静默读取，不渲染 widget（tid、camp_id）。
- 其他参数：通过 fallbacks 传入 render_filters()，渲染为简单内联 widget。
- render_filters 返回 (values, labels)：values 供 SQL；labels 供页面文案，须与筛选一并冻结。

联动筛选：
- depends_on：监听的参数名列表，任一有值即触发联动
- cascade_clause：有值时追加到选项 SQL 末尾，{values} 替换为逗号分隔的整数 ID
  示例："AND camp_term_id IN ({values})"
- FILTER_REGISTRY 的注册顺序即渲染顺序，被依赖项必须在依赖项之前
"""
import streamlit as st
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

# ---------------------------------------------------------------------------
# 共享 SQL 片段（多选/单选变体复用同一查询）
# ---------------------------------------------------------------------------
# 期次选项：按 rank 筛选，显示"第N期 (ID:x)"
# 表名加 warehouse.：Metabase 库连接默认库为 doris，无前缀会报 table does not exist
_TERM_SQL = (
    "SELECT id AS value,"
    " CONCAT('第', `rank`, '期 (ID:', id, ')') AS label"
    " FROM warehouse.dim_lh_teaching_class_term"
    " WHERE tid = :tid ORDER BY `rank` DESC"
)

# 班级选项：按 ID 白名单过滤，排除空名称
_CLASS_SQL = (
    "SELECT id AS value, class_name AS label"
    " FROM warehouse.dwd_lh_classes"
    " WHERE id IN (10060654, 10055057, 10060762) AND class_name <> ''"
)
# 自然周选项：按 ID 白名单过滤，排除空名称
_WEEK_SQL = (
    "SELECT id AS value,"
    "CONCAT(`year`,'年',`month`,'月第',`week`, '周 (', DATE(`start_time`),'~' ,DATE(`end_time`),')') AS label "
    "FROM warehouse.lh_teaching_weeks_conf "
    "WHERE tid = :tid order by end_time desc"
)

# 品类选项：商品品类维度表
_CATEGORY_SQL = (
    "SELECT id AS value, name AS label"
    " FROM warehouse.dim_mdb_product_category"
    " WHERE name <> ''"
    " ORDER BY id"
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
    # 有选项时默认选中第一项：selectbox → index=0；multiselect → default=[第一项]
    # 期次筛选项（term_id / term_ids）一律 True
    default_first: bool = False


FILTER_REGISTRY: dict[str, FilterSpec] = {
    # 期次 — 多选（必须在班级之前注册；默认选中第一项）
    "term_ids": FilterSpec(
        label="期次",
        widget="multiselect",
        sql=_TERM_SQL,
        session_params=["tid"],
        default_first=True,
    ),
    # 期次 — 单选（默认选中第一项）
    "term_id": FilterSpec(
        label="期次",
        widget="selectbox",
        sql=_TERM_SQL,
        session_params=["tid"],
        default_first=True,
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
    # 品类 — 多选（复购/退款订单等按品类筛选；无联动）
    "category_ids": FilterSpec(
        label="品类",
        widget="multiselect",
        sql=_CATEGORY_SQL,
    ),
}

# 从 session_state 静默读取的参数，不渲染任何 widget
SESSION_KEYS: set[str] = {"tid", "camp_id"}

# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

# default：text_input / number_input 的初始值（仅首次渲染生效，之后由 widget 状态保持）
FallbackSpec = dict  # {"label": str, "widget": "text_input" | "number_input", "default"?: str}


def _query_filter_options(conn, options_sql: str, query_params: dict, label: str):
    """
    加载筛选项；失败时告警并返回空表，避免整页因选项 SQL 超时而崩溃。
    """
    try:
        return conn.query(options_sql, params=query_params, ttl=300)
    except Exception as exc:
        st.warning(f"加载「{label}」选项失败（页面仍可继续）：{exc}")
        return pd.DataFrame(columns=["label", "value"])


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
) -> tuple[dict, dict]:
    """
    为 template_params 中涉及的参数渲染筛选 widget。

    返回 ``(values, labels)``：
      - values：{param: value}，供 ``build_sql()`` 使用（ID / 列表 / 文本）
      - labels：同键的可读展示文本，供页面文案模板填充
          multiselect → list[str]；selectbox → str | None；
          text_input / number_input → 与 value 相同或 str(value)；
          SESSION_KEYS → str(value)（无值则为 None）

    参数解析优先级：
      1. SESSION_KEYS    → 从 st.session_state 读取，不渲染 widget
      2. FILTER_REGISTRY → 渲染 DB 驱动的 multiselect 或 selectbox
                           （注册顺序即渲染顺序，依赖项须在被依赖项之前）
      3. fallbacks       → 渲染简单内联 widget（text_input 等）
      4. 未知参数         → 静默忽略
    """
    values: dict = {}
    labels: dict = {}
    fallbacks = fallbacks or {}

    # 1. 从 session_state 读取会话参数
    for key in SESSION_KEYS:
        if key in template_params:
            values[key] = st.session_state.get(key)
            labels[key] = str(values[key]) if values[key] is not None else None

    # 2 + 3. 确定需要渲染 widget 的参数列表
    active_registry = [p for p in FILTER_REGISTRY if p in template_params]
    active_fallback = [
        p for p in fallbacks
        if p in template_params and p not in FILTER_REGISTRY and p not in SESSION_KEYS
    ]
    all_active = active_registry + active_fallback
    if not all_active:
        return values, labels

    # 横向排列固定宽：避免通栏 columns 把控件拉满；多选 400、其余 200
    _MULTI_WIDTH = 400
    _WIDGET_WIDTH = 200
    with st.container(horizontal=True, gap="small"):
        # 按注册表顺序渲染 DB 驱动筛选项；values 逐步更新，使联动项能读到依赖值
        for param in active_registry:
            spec = FILTER_REGISTRY[param]
            # 将 session_params 中声明的 session key 透传给选项查询
            query_params = {k: st.session_state.get(
                k) for k in spec.session_params}
            options_sql = _build_options_sql(spec, values)

            if spec.widget == "multiselect":
                opt_df = _query_filter_options(
                    conn, options_sql, query_params, spec.label
                )
                # 构建 label → value 映射，保持选项顺序
                opt_map: dict = dict(
                    zip(opt_df["label"], opt_df["value"].astype(int)))
                opt_labels = list(opt_map.keys())
                # default_first：有选项时预选第一项（仅首次渲染生效，之后由 widget 状态保持）
                default = (
                    [opt_labels[0]] if spec.default_first and opt_labels else None
                )
                selected = st.multiselect(
                    spec.label,
                    opt_labels,
                    default=default,
                    width=_MULTI_WIDTH,
                )
                values[param] = [opt_map[s] for s in selected]
                labels[param] = list(selected)

            elif spec.widget == "selectbox":
                opt_df = _query_filter_options(
                    conn, options_sql, query_params, spec.label
                )
                opt_map = dict(
                    zip(opt_df["label"], opt_df["value"].astype(int)))
                opt_labels = list(opt_map.keys())
                # default_first：有选项时选第一项；否则保持「全部」(None) 供可选块丢弃
                if spec.default_first and opt_labels:
                    chosen = st.selectbox(
                        spec.label,
                        options=opt_labels,
                        index=0,
                        width=_WIDGET_WIDTH,
                    )
                else:
                    chosen = st.selectbox(
                        spec.label,
                        options=opt_labels,
                        index=None,
                        placeholder="全部",
                        width=_WIDGET_WIDTH,
                    )
                values[param] = opt_map[chosen] if chosen is not None else None
                labels[param] = chosen

            elif spec.widget == "text_input":
                text = st.text_input(spec.label, width=_WIDGET_WIDTH)
                values[param] = text
                labels[param] = text

        # 渲染 fallback 简单参数（排在注册表参数之后）
        for param in active_fallback:
            fb = fallbacks[param]
            widget = fb.get("widget", "text_input")
            label = fb.get("label", param)
            # 勿与 key 同时再写 session_state；value 仅作首次默认
            default = fb.get("default", "")
            if widget == "number_input":
                # 用 text_input 接收输入，非纯数字时返回 None 而非报错
                raw = st.text_input(
                    label,
                    value=str(default) if default not in (None, "") else "",
                    placeholder="留空表示不筛选",
                    width=_WIDGET_WIDTH,
                )
                values[param] = int(raw) if raw.strip().isdigit() else None
                labels[param] = (
                    str(values[param]) if values[param] is not None else None
                )
            else:
                text = st.text_input(
                    label,
                    value=str(default) if default not in (None, "") else "",
                    width=_WIDGET_WIDTH,
                )
                values[param] = text
                labels[param] = text

    return values, labels
