"""
Filter registry for Metabase-template pages.

Registry rules:
- FILTER_REGISTRY: params that need a DB-backed options query.
  - widget="multiselect"  → {{param_ids}} style, returns list → used in IN clause
  - widget="selectbox"    → {{param_id}}  style, returns int | None → used in = clause
- SESSION_KEYS: pulled silently from st.session_state, never rendered as widgets.
- Anything else: pass via `fallbacks` to render_filters() for simple inline widgets.

Cascading filters:
- Set depends_on to a list of param names this filter watches.
- Set cascade_clause to the SQL snippet appended when any dependency has a value.
  Use {values} as the placeholder for the comma-separated dep IDs.
  Example: "AND camp_term_id IN ({values})"
- The FILTER_REGISTRY order determines render order — put dependencies before dependents.
"""
import streamlit as st
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Shared SQL fragments (reused between multi/single variants)
# ---------------------------------------------------------------------------

_TERM_SQL = (
    "SELECT id AS value,"
    " CONCAT('第', `rank`, '期 (ID:', id, ')') AS label"
    " FROM dim_lh_teaching_class_term"
    " WHERE tid = :tid AND `rank` IN (84, 71)"
)

_CLASS_SQL = (
    "SELECT id AS value, class_name AS label"
    " FROM dwd_lh_classes"
    " WHERE id IN (10060654, 10055057, 10060762) AND class_name <> ''"
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class FilterSpec:
    label: str
    widget: Literal["multiselect", "selectbox", "text_input"]
    # Required for multiselect / selectbox. Must return columns: value, label.
    sql: str | None = None
    # session_state keys forwarded as query params to `sql`.
    session_params: list[str] = field(default_factory=list)
    # Cascade: param names whose selected values inject into this filter's SQL.
    depends_on: list[str] = field(default_factory=list)
    # SQL clause appended when any depends_on param has a value.
    # {values} is replaced with comma-separated integer IDs.
    cascade_clause: str | None = None


FILTER_REGISTRY: dict[str, FilterSpec] = {
    # 期次 — multi  (must be defined before class so values are ready for cascade)
    "term_ids": FilterSpec(
        label="期次",
        widget="multiselect",
        sql=_TERM_SQL,
        session_params=["tid"],
    ),
    # 期次 — single
    "term_id": FilterSpec(
        label="期次",
        widget="selectbox",
        sql=_TERM_SQL,
        session_params=["tid"],
    ),
    # 班级 — multi  (cascades from whichever term param is active)
    "class_ids": FilterSpec(
        label="班级",
        widget="multiselect",
        sql=_CLASS_SQL,
        depends_on=["term_ids", "term_id"],
        cascade_clause="AND camp_term_id IN ({values})",
    ),
    # 班级 — single
    "class_id": FilterSpec(
        label="班级",
        widget="selectbox",
        sql=_CLASS_SQL,
        depends_on=["term_ids", "term_id"],
        cascade_clause="AND camp_term_id IN ({values})",
    ),
}

# Params taken from session_state; never rendered as UI widgets.
SESSION_KEYS: set[str] = {"tid", "camp_id"}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

FallbackSpec = dict  # {"label": str, "widget": "text_input" | "number_input"}


def _build_options_sql(spec: FilterSpec, current_values: dict) -> str:
    """Append cascade_clause to spec.sql when any dependency has selected values."""
    if not spec.cascade_clause or not spec.depends_on:
        return f"{spec.sql}"

    dep_ids: list[int] = []
    for dep in spec.depends_on:
        val = current_values.get(dep)
        if isinstance(val, list):
            dep_ids.extend(val)
        elif isinstance(val, int):
            dep_ids.append(val)

    if not dep_ids:
        return f"{spec.sql}"

    clause = spec.cascade_clause.format(
        values=", ".join(str(i) for i in dep_ids))
    return f"{spec.sql} {clause}"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_filters(
    conn,
    template_params: set[str],
    fallbacks: dict[str, FallbackSpec] | None = None,
) -> dict:
    """
    Render filter widgets for params found in `template_params` and return
    {param_name: value} ready for build_sql().

    Resolution order per param:
      1. SESSION_KEYS      → read from st.session_state, no widget
      2. FILTER_REGISTRY   → render DB-backed multiselect or selectbox
                             (registry order matters: dependents must come after dependencies)
      3. fallbacks         → render simple inline widget (text_input, etc.)
      4. Unknown           → silently ignored
    """
    values: dict = {}
    fallbacks = fallbacks or {}

    # 1. Session params
    for key in SESSION_KEYS:
        if key in template_params:
            values[key] = st.session_state.get(key)

    # 2 + 3. Active widget params
    active_registry = [p for p in FILTER_REGISTRY if p in template_params]
    active_fallback = [
        p for p in fallbacks
        if p in template_params and p not in FILTER_REGISTRY and p not in SESSION_KEYS
    ]
    all_active = active_registry + active_fallback
    if not all_active:
        return values

    cols = st.columns(len(all_active))

    # Render registry params in order; values dict is updated incrementally so
    # dependents can read their dependency's value via _build_options_sql.
    for col, param in zip(cols, active_registry):
        spec = FILTER_REGISTRY[param]
        query_params = {k: st.session_state.get(
            k) for k in spec.session_params}
        options_sql = _build_options_sql(spec, values)

        with col:
            if spec.widget == "multiselect":
                opt_df = conn.query(options_sql, params=query_params, ttl=300)
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
                values[param] = opt_map[chosen] if chosen is not None else None

            elif spec.widget == "text_input":
                values[param] = st.text_input(spec.label)

    # Render fallback params
    for col, param in zip(cols[len(active_registry):], active_fallback):
        fb = fallbacks[param]
        with col:
            widget = fb.get("widget", "text_input")
            label = fb.get("label", param)
            if widget == "number_input":
                raw = st.text_input(label, placeholder="留空表示不筛选")
                values[param] = int(raw) if raw.strip().isdigit() else None
            else:
                values[param] = st.text_input(label)

    return values
