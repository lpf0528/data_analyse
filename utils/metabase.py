"""
Metabase 风格 SQL 模板的解析与执行工具。

模板语法：
  {{param}}               — 命名参数，有值时替换为 :param 占位符
  [[ ... {{param}} ... ]] — 可选块，param 无值时整块丢弃
"""
import re


def extract_params(template: str) -> set[str]:
    """提取模板中所有 {{param}} 参数名，返回参数名集合。"""
    return set(re.findall(r"\{\{(\w+)\}\}", template))


def build_sql(template: str, values: dict) -> tuple[str, dict]:
    """
    将 Metabase SQL 模板转换为 SQLAlchemy 可执行的 SQL 字符串和参数字典。

    处理规则：
    - [[ ... ]] 可选块：块内任意 {{param}} 无值时，整块丢弃
    - 列表值（IN 子句）：直接内联为逗号分隔的整数字符串（来自 DB 查询，安全）
    - 标量值：替换为 :param 占位符，值写入 sa_params
    """
    sql = template

    def _handle_optional(match: re.Match) -> str:
        """若可选块内有参数无值，返回空字符串以丢弃该块。"""
        block = match.group(1)
        for param in re.findall(r"\{\{(\w+)\}\}", block):
            val = values.get(param)
            # None 涵盖：selectbox 未选、参数缺失
            if val is None or val == "" or val == []:
                return ""
        return block

    # 处理所有 [[ ]] 可选块
    sql = re.sub(r"\[\[(.*?)\]\]", _handle_optional, sql, flags=re.DOTALL)

    sa_params: dict = {}
    for param, val in values.items():
        placeholder = f"{{{{{param}}}}}"
        if placeholder not in sql:
            continue
        if isinstance(val, list):
            # 列表值内联为整数字符串，用于 IN (...) 子句
            sql = sql.replace(placeholder, ", ".join(str(v) for v in val))
        else:
            # 标量值转为具名占位符，防止 SQL 注入
            sql = sql.replace(placeholder, f":{param}")
            if val not in (None, ""):
                sa_params[param] = val

    return sql.strip(), sa_params


def format_display_sql(sql: str, sa_params: dict) -> str:
    """将 :param 占位符替换回实际值，生成可读的展示用 SQL。"""
    display = sql
    # 按键名长度降序替换，避免 :camp 被先替换导致 :camp_id 残留
    for key in sorted(sa_params, key=len, reverse=True):
        display = display.replace(f":{key}", repr(sa_params[key]))
    return display


def render_sql(sql: str, params: dict) -> tuple[str, list[str]]:
    """
    根据 params 字典/OrderedDict 渲染带 %(param)s 占位符的 SQL 模板。

    支持:
    - list/tuple -> (item1, item2)
    - datetime/date -> 'YYYY-MM-DD HH:MM:SS' 或 'YYYY-MM-DD'
    - str -> 'escaped_string' (转义单引号)
    - None -> NULL
    - int/float/bool -> 字面量字符串

    返回:
        (rendered_sql, missing_params): 渲染后的 SQL 字符串及未提供值的参数列表。
    """
    import datetime
    from typing import Any

    def fmt(v: Any) -> str:
        if isinstance(v, (list, tuple)):
            if not v:
                return "(NULL)"
            return "(" + ",".join(fmt(i) for i in v) + ")"
        if isinstance(v, datetime.datetime):
            return f"'{v:%Y-%m-%d %H:%M:%S}'"
        if isinstance(v, datetime.date):
            return f"'{v:%Y-%m-%d}'"
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
        if v is None:
            return "NULL"
        return str(v)

    # 查找所有 %(param_name)s 占位符
    placeholders = re.findall(r"%\((\w+)\)s", sql)
    missing_params = [p for p in placeholders if p not in params or params[p] is None]

    def _replace(m: re.Match) -> str:
        key = m.group(1)
        if key not in params or params[key] is None:
            return m.group(0)
        return fmt(params[key])

    rendered = re.sub(r"%\((\w+)\)s", _replace, sql)
    return rendered, sorted(list(set(missing_params)))


def parse_params(param_str: str) -> dict:
    """解析用户输入的参数文本，支持 Python 字典 / OrderedDict 语法及 JSON 语法。"""
    import datetime
    import json
    from collections import OrderedDict

    param_str = param_str.strip()
    if not param_str:
        return {}

    eval_globals = {
        "datetime": datetime,
        "date": datetime.date,
        "OrderedDict": OrderedDict,
        "dict": dict,
        "list": list,
        "tuple": tuple,
        "True": True,
        "False": False,
        "None": None,
        "true": True,
        "false": False,
        "null": None,
    }

    # 1. 尝试 Python safe eval
    try:
        res = eval(param_str, eval_globals, {})
        if isinstance(res, (dict, OrderedDict)):
            return dict(res)
    except Exception:
        pass

    # 2. 尝试 JSON
    try:
        res = json.loads(param_str)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    raise ValueError(
        "无法解析参数。请输入合法的 Python 字典（如 `OrderedDict([('tid', 279), ...])`）或 JSON 格式。"
    )

