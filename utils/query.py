"""
统一查询入口：在「直连 MySQL/StarRocks」与「经 Metabase API」之间切换。

页面与筛选器统一：
    from utils.query import get_conn
    conn = get_conn()
    df = conn.query(sql, params=sa_params, ttl=0)

侧边栏切换由 render_query_backend_selector() 负责，写入 session_state。
"""
from __future__ import annotations

from typing import Any, Literal, Protocol

import pandas as pd
import streamlit as st

from utils.metabase_client import MetabaseClient, client_from_secrets

QueryBackend = Literal["mysql", "metabase"]

_SS_BACKEND = "query_backend"
_SS_MB_CLIENT = "_metabase_client"


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
    """secrets 可设 query_backend = "metabase"；缺省 mysql。"""
    try:
        raw = st.secrets.get("query_backend", "mysql")
    except Exception:
        raw = "mysql"
    return "metabase" if str(raw).lower() == "metabase" else "mysql"


def get_query_backend() -> QueryBackend:
    if _SS_BACKEND not in st.session_state:
        st.session_state[_SS_BACKEND] = _default_backend()
    backend = st.session_state[_SS_BACKEND]
    return "metabase" if backend == "metabase" else "mysql"


def set_query_backend(backend: QueryBackend) -> None:
    st.session_state[_SS_BACKEND] = backend


def render_query_backend_selector() -> QueryBackend:
    """
    侧边栏切换数据源。本地无库时可切到 Metabase。

    须在各页查询前调用（建议放在 app.py navigation 之前）。
    """
    current = get_query_backend()
    options: list[QueryBackend] = ["mysql", "metabase"]
    labels = {
        "mysql": "数据库（StarRocks）",
        "metabase": "Metabase API",
    }
    # 只通过 key 管值，避免 default + session_state 双设告警
    if _SS_BACKEND not in st.session_state:
        st.session_state[_SS_BACKEND] = current

    with st.sidebar:
        st.radio(
            "查询方式",
            options=options,
            format_func=lambda x: labels[x],
            key=_SS_BACKEND,
            help="本地连不上线上库时，可切换为经 Metabase 执行 SQL。",
        )
        backend = get_query_backend()
        if backend == "metabase":
            st.caption("经 Metabase `/api/dataset` 查询")
        else:
            st.caption("经 `st.connection('mysql')` 直连")
    return backend


def _get_metabase_client() -> MetabaseClient:
    client = st.session_state.get(_SS_MB_CLIENT)
    if client is None:
        client = client_from_secrets(st.secrets)
        st.session_state[_SS_MB_CLIENT] = client
    return client


def get_conn() -> Any:
    """
    按当前后端返回可 `.query(...)` 的连接对象。

    - mysql → st.connection("mysql", type="sql")
    - metabase → MetabaseQueryConn
    """
    if get_query_backend() == "metabase":
        return MetabaseQueryConn(_get_metabase_client())
    return st.connection("mysql", type="sql")
