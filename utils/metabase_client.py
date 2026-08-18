"""
Metabase 原生 SQL 查询客户端。

本地无法直连线上 StarRocks 时，通过 Metabase `/api/dataset` 执行 SQL，
并将返回的 rows/cols 转为 pandas.DataFrame，接口形态贴近 st.connection.query。
"""
from __future__ import annotations

import http.cookiejar
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://metabase.goweike.cn"
DEFAULT_DB_ID = 426
DEFAULT_COOKIES_FILE = Path("cookies.txt")


class MetabaseError(RuntimeError):
    """Metabase API 或查询失败。"""


def sql_literal(value: Any) -> str:
    """将 Python 值转为可内联的 SQL 字面量（供 Metabase 原生查询使用）。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    # 字符串：单引号转义；与 format_display_sql 的 repr 类似，但对 SQL 更稳妥
    return "'" + str(value).replace("'", "''") + "'"


def bind_sql_params(sql: str, params: dict | None) -> str:
    """将 :param 占位符替换为字面量，生成可直接提交给 Metabase 的 SQL。"""
    if not params:
        return sql
    bound = sql
    # 按键名长度降序，避免 :camp 先替换导致 :camp_id 残留
    for key in sorted(params, key=len, reverse=True):
        bound = bound.replace(f":{key}", sql_literal(params[key]))
    return bound


def metabase_data_to_dataframe(data: dict) -> pd.DataFrame:
    """
    将 Metabase dataset 的 data 字段转为 DataFrame。

    期望结构：
      {"rows": [[...], ...], "cols": [{"name": "col", ...}, ...], ...}
    """
    if not data:
        return pd.DataFrame()
    rows = data.get("rows") or []
    cols_meta = data.get("cols") or []
    columns = [c.get("name") or c.get("display_name") or f"col_{i}"
               for i, c in enumerate(cols_meta)]
    if columns:
        return pd.DataFrame(rows, columns=columns)
    return pd.DataFrame(rows)


class MetabaseClient:
    """会话复用的 Metabase 查询客户端。"""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        username: str,
        password: str,
        db_id: int = DEFAULT_DB_ID,
        cookies_file: str | Path = DEFAULT_COOKIES_FILE,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.db_id = db_id
        self.cookies_file = Path(cookies_file)
        self._session: requests.Session | None = None

    def _new_session(self) -> requests.Session:
        sess = requests.Session()
        sess.headers.update(
            {
                "Content-Type": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/107.0.0.0 Safari/537.36"
                ),
            }
        )
        return sess

    def _load_cached_cookies(self, sess: requests.Session) -> bool:
        if not self.cookies_file.exists():
            logger.info("未找到 %s，将重新登录", self.cookies_file)
            return False
        try:
            jar = http.cookiejar.LWPCookieJar()
            jar.load(str(self.cookies_file), ignore_discard=True, ignore_expires=True)
            cookies = requests.utils.dict_from_cookiejar(jar)
            sess.cookies = requests.utils.cookiejar_from_dict(cookies)
            logger.info(
                "已从 %s 加载缓存 cookie（共 %d 个）",
                self.cookies_file,
                len(cookies),
            )
            return bool(cookies)
        except FileNotFoundError:
            logger.info("未找到 %s，将重新登录", self.cookies_file)
            return False
        except Exception:
            logger.warning("加载 %s 失败，将重新登录", self.cookies_file, exc_info=True)
            return False

    def login(self, sess: requests.Session | None = None) -> requests.Session:
        """账号密码登录并持久化 cookie。"""
        sess = sess or self._new_session()
        # 用 LWPCookieJar 承接登录 cookie，便于 save 到本地文件
        sess.cookies = http.cookiejar.LWPCookieJar(filename=str(self.cookies_file))
        url = f"{self.base_url}/api/session"
        logger.info("向 Metabase 发起登录请求: %s (user=%s)", url, self.username)
        response = sess.post(
            url,
            json={
                "username": self.username,
                "password": self.password,
                "remember": True,
            },
        )
        logger.info("登录响应 status=%s", response.status_code)
        if response.status_code != 200:
            raise MetabaseError(
                f"Metabase 登录失败 status={response.status_code}: {response.text[:500]}"
            )
        sess.cookies.save(ignore_discard=True, ignore_expires=True)
        logger.info("登录成功，cookie 已写入 %s", self.cookies_file)
        self._session = sess
        return sess

    def get_session(self, *, force_login: bool = False) -> requests.Session:
        if force_login:
            return self.login()
        if self._session is not None:
            return self._session
        sess = self._new_session()
        if self._load_cached_cookies(sess):
            self._session = sess
            return sess
        return self.login(sess)

    def query_raw(self, sql: str, *, db_id: int | None = None) -> dict:
        """执行原生 SQL，返回 Metabase data 字段（含 rows/cols）。"""
        database = db_id if db_id is not None else self.db_id
        url = f"{self.base_url}/api/dataset"
        payload = {
            "database": database,
            "native": {
                "template-tags": {},
                "query": sql,
            },
            "type": "native",
            "parameters": [],
        }
        logger.info("发起 Metabase 查询 db_id=%s sql_len=%d", database, len(sql))
        logger.debug("查询 SQL:\n%s", sql)

        for attempt in range(2):
            sess = self.get_session(force_login=(attempt > 0))
            response = sess.post(url, json=payload)
            logger.info("查询响应 status=%s (attempt=%d)", response.status_code, attempt + 1)

            if response.status_code == 401:
                logger.warning("会话已失效 (401)，重新登录后重试")
                self._session = None
                continue

            try:
                res = response.json()
            except json.JSONDecodeError as exc:
                raise MetabaseError(
                    f"响应非 JSON status={response.status_code}: {response.text[:500]}"
                ) from exc

            if res.get("error_type") or res.get("error"):
                error_type = res.get("error_type", "")
                error = res.get("error", "")
                raise MetabaseError(f"Metabase 查询错误 {error_type}: {error}")

            data = res.get("data")
            if data is None:
                raise MetabaseError(f"查询响应无 data 字段 keys={list(res.keys())}")

            rows = data.get("rows") if isinstance(data, dict) else None
            logger.info("查询成功，返回行数=%s", len(rows) if rows is not None else "unknown")
            return data

        raise MetabaseError("Metabase 认证失败：重试后仍为 401")

    def query(
        self,
        sql: str,
        params: dict | None = None,
        *,
        db_id: int | None = None,
        ttl: int = 0,  # noqa: ARG002 — 与 st.connection.query 签名对齐；暂不缓存
    ) -> pd.DataFrame:
        """绑定参数后查询，返回 DataFrame。"""
        bound_sql = bind_sql_params(sql, params)
        data = self.query_raw(bound_sql, db_id=db_id)
        return metabase_data_to_dataframe(data)


def _load_metabase_section_from_toml() -> dict:
    """无 Streamlit 时也可读 `.streamlit/secrets.toml` 的 [metabase]。"""
    import tomllib

    path = Path(".streamlit/secrets.toml")
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
        return dict(data.get("metabase") or {})
    except Exception:
        logger.warning("读取 %s 中 [metabase] 失败", path, exc_info=True)
        return {}


def resolve_metabase_config(secrets: Any | None = None) -> dict:
    """
    合并配置优先级：显式 secrets → secrets.toml → 环境变量。

    secrets.toml 示例：
      [metabase]
      base_url = "https://metabase.goweike.cn"
      username = "..."
      password = "..."
      db_id = 246
      cookies_file = "cookies.txt"
    """
    import os

    mb: dict = {}
    if secrets is not None:
        try:
            mb = dict(secrets.get("metabase", {}) or {})
        except Exception:
            mb = {}
    if not mb.get("username") or not mb.get("password"):
        file_mb = _load_metabase_section_from_toml()
        mb = {**file_mb, **{k: v for k, v in mb.items() if v}}

    username = mb.get("username") or os.environ.get("METABASE_USERNAME")
    password = mb.get("password") or os.environ.get("METABASE_PASSWORD")
    base_url = (
        mb.get("base_url")
        or os.environ.get("METABASE_BASE_URL")
        or DEFAULT_BASE_URL
    )
    db_id = mb.get("db_id") or os.environ.get("METABASE_DB_ID") or DEFAULT_DB_ID
    cookies_file = (
        mb.get("cookies_file")
        or os.environ.get("METABASE_COOKIES_FILE")
        or DEFAULT_COOKIES_FILE
    )
    return {
        "base_url": base_url,
        "username": username,
        "password": password,
        "db_id": int(db_id),
        "cookies_file": cookies_file,
    }


def client_from_secrets(secrets: Any | None = None) -> MetabaseClient:
    """从 Streamlit secrets / secrets.toml / 环境变量构建客户端。"""
    cfg = resolve_metabase_config(secrets)
    if not cfg.get("username") or not cfg.get("password"):
        raise MetabaseError(
            "未配置 Metabase 账号：请在 .streamlit/secrets.toml 的 [metabase] 中设置 "
            "username / password，或设置环境变量 METABASE_USERNAME / METABASE_PASSWORD"
        )
    return MetabaseClient(
        base_url=str(cfg["base_url"]),
        username=str(cfg["username"]),
        password=str(cfg["password"]),
        db_id=int(cfg["db_id"]),
        cookies_file=cfg["cookies_file"],
    )
