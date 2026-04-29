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
