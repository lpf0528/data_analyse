"""
统一查询入口：在「直连 MySQL/StarRocks」与「经 Metabase API」之间切换。

页面与筛选器统一：
    from utils.query import get_conn
    conn = get_conn()
    df = conn.query(sql, params=sa_params, ttl=0)

侧边栏：查询方式 + tid/camp_id 营期上下文，由 render_sidebar_controls() 负责。
"""
from __future__ import annotations

from typing import Any, Literal, Protocol

import pandas as pd
import streamlit as st

from utils.metabase_client import MetabaseClient, client_from_secrets
from utils.metabase import format_display_sql


def show_sql_and_query(
    conn: Any,
    sql: str,
    params: dict | None = None,
    *,
    ttl: int = 0,
    expanded: bool = False,
    spinner_text: str = "查询中...",
    expander_label: str = "执行的 SQL",
) -> pd.DataFrame:
    """
    先渲染可展开的 SQL，再执行查询。

    无论成败 SQL 都会留在页面上；失败时 st.error 并 st.stop()。
    """
    params = params or {}
    with st.expander(expander_label, expanded=expanded):
        st.code(format_display_sql(sql, params), language="sql")
    try:
        with st.spinner(spinner_text):
            return conn.query(sql, params=params, ttl=ttl)
    except Exception as exc:
        # SQL 已在上方展示，便于对照排查（超时 / 语法 / 缺表等）
        st.error(f"查询失败：{exc}")
        st.stop()
        raise  # 供类型检查；st.stop() 不会返回


QueryBackend = Literal["mysql", "metabase"]

_SS_BACKEND = "query_backend"
_SS_MB_CLIENT = "_metabase_client"
_SS_CAMP_IDX = "camp_context_idx"

# 本地/调试可选的团队+营期；侧边栏列表，默认第一项
CAMP_OPTIONS: list[dict[str, int]] = [
    {"tid": 369, "camp_id": 107808},
]


class QueryConn(Protocol):
    """与 st.connection("mysql").query 对齐的最小协议。"""

    def query(
        self,
        sql: str,
        params: dict | None = None,
        *,
        ttl: int = 0,
    ) -> pd.DataFrame: ...


class MetabaseQueryConn:
    """包装 MetabaseClient，提供与 SQLConnection.query 相同的调用方式。"""

    def __init__(self, client: MetabaseClient):
        self._client = client

    def query(
        self,
        sql: str,
        params: dict | None = None,
        *,
        ttl: int = 0,
    ) -> pd.DataFrame:
        return self._client.query(sql, params=params, ttl=ttl)


def _default_backend() -> QueryBackend:
    """secrets 可设 query_backend；缺省 metabase（本地通常无直连库）。"""
    try:
        raw = st.secrets.get("query_backend", "metabase")
    except Exception:
        raw = "metabase"
    return "mysql" if str(raw).lower() == "mysql" else "metabase"


def get_query_backend() -> QueryBackend:
    if _SS_BACKEND not in st.session_state:
        st.session_state[_SS_BACKEND] = _default_backend()
    backend = st.session_state[_SS_BACKEND]
    return "metabase" if backend == "metabase" else "mysql"


def set_query_backend(backend: QueryBackend) -> None:
    st.session_state[_SS_BACKEND] = backend


def _camp_label(opt: dict[str, int]) -> str:
    return f"tid={opt['tid']} · camp_id={opt['camp_id']}"


def _sync_camp_context(idx: int) -> None:
    """把列表选中项写入 SESSION_KEYS 使用的 tid / camp_id。"""
    if not CAMP_OPTIONS:
        return
    idx = max(0, min(int(idx), len(CAMP_OPTIONS) - 1))
    chosen = CAMP_OPTIONS[idx]
    st.session_state.tid = chosen["tid"]
    st.session_state.camp_id = chosen["camp_id"]


def render_sidebar_controls() -> QueryBackend:
    """
    侧边栏：查询方式 + tid/camp_id 列表（默认第一项）。

    须在各页查询前调用（放在 app.py navigation 之前）。
    """
    if _SS_BACKEND not in st.session_state:
        st.session_state[_SS_BACKEND] = _default_backend()

    options: list[QueryBackend] = ["metabase", "mysql"]
    labels = {
        "metabase": "Metabase API",
        "mysql": "数据库（StarRocks）",
    }

    with st.sidebar:
        st.radio(
            "查询方式",
            options=options,
            format_func=lambda x: labels[x],
            key=_SS_BACKEND,
            help="本地连不上线上库时使用 Metabase；默认可在 secrets 设 query_backend。",
        )
        backend = get_query_backend()
        if backend == "metabase":
            st.caption("经 Metabase `/api/dataset` 查询")
        else:
            st.caption("经 `st.connection('mysql')` 直连")

        # tid/camp_id：只通过 key 管选中项，勿再传 index，避免双设告警
        camp_indices = list(range(len(CAMP_OPTIONS)))
        st.selectbox(
            "团队 / 营期",
            options=camp_indices,
            format_func=lambda i: _camp_label(CAMP_OPTIONS[i]),
            key=_SS_CAMP_IDX,
            help="写入 session 的 tid、camp_id，供各页 SESSION_KEYS 与筛选使用。",
        )
        _sync_camp_context(st.session_state.get(_SS_CAMP_IDX, 0))
        st.caption(
            f"当前 tid={st.session_state.tid} · camp_id={st.session_state.camp_id}"
        )

    return backend


def render_query_backend_selector() -> QueryBackend:
    """兼容旧名；等同 render_sidebar_controls()。"""
    return render_sidebar_controls()


def _get_metabase_client() -> MetabaseClient:
    client = st.session_state.get(_SS_MB_CLIENT)
    if client is None:
        client = client_from_secrets(st.secrets)
        st.session_state[_SS_MB_CLIENT] = client
    return client


REGISTERED_DATABASES: list[str] = ["warehouse", "lh_teaching"]


def get_registered_databases() -> list[str]:
    """返回当前支持/已配置的目标数据库列表。"""
    return list(REGISTERED_DATABASES)


def get_conn(db_name: str = "warehouse") -> Any:
    """
    按指定数据库名与后端配置返回可 `.query(...)` 的连接对象。

    - warehouse (或 doris) → 根据侧边栏配置走 MetabaseQueryConn 或 st.connection("mysql", type="sql")
    - lh_teaching (或其他定义在 secrets.connections 中的库) → st.connection(db_name, type="sql")
    """
    if db_name in ("warehouse", "doris", "", None):
        if get_query_backend() == "metabase":
            return MetabaseQueryConn(_get_metabase_client())
        return st.connection("mysql", type="sql")

    return st.connection(db_name, type="sql")

