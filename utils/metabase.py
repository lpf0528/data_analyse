"""
Utilities for parsing and executing Metabase-style SQL templates.

Template syntax:
  {{param}}         — required parameter
  [[ ... {{param}} ... ]]  — optional block, included only when param has a value
"""
import re


def extract_params(template: str) -> set[str]:
    """Return all {{param}} names found in a Metabase SQL template."""
    return set(re.findall(r"\{\{(\w+)\}\}", template))


def build_sql(template: str, values: dict) -> tuple[str, dict]:
    """
    Convert a Metabase SQL template into a SQLAlchemy SQL string + params dict.

    - [[ ... ]] blocks are dropped when their {{param}} has no value.
    - List values are inlined (safe for integer IDs from DB lookups).
    - Scalar values become :param placeholders added to sa_params.
    """
    sql = template

    def _handle_optional(match: re.Match) -> str:
        block = match.group(1)
        for param in re.findall(r"\{\{(\w+)\}\}", block):
            val = values.get(param)
            # None covers: selectbox with no selection, missing param
            if val is None or val == "" or val == []:
                return ""
        return block

    sql = re.sub(r"\[\[(.*?)\]\]", _handle_optional, sql, flags=re.DOTALL)

    sa_params: dict = {}
    for param, val in values.items():
        placeholder = f"{{{{{param}}}}}"
        if placeholder not in sql:
            continue
        if isinstance(val, list):
            sql = sql.replace(placeholder, ", ".join(str(v) for v in val))
        else:
            sql = sql.replace(placeholder, f":{param}")
            if val not in (None, ""):
                sa_params[param] = val

    return sql.strip(), sa_params


def format_display_sql(sql: str, sa_params: dict) -> str:
    """Substitute named params back into SQL for on-screen display."""
    display = sql
    # Replace longest keys first to avoid partial substitutions (e.g. :camp before :camp_id)
    for key in sorted(sa_params, key=len, reverse=True):
        display = display.replace(f":{key}", repr(sa_params[key]))
    return display
