"""页面文案模板填充：与 Metabase ``{{param}}`` 分离，使用 str.format 占位符。"""


def fill_template(template: str, **ctx) -> str:
    """用 ctx 填充 ``{name}`` 占位符；缺键时抛 KeyError，便于开发期发现问题。"""
    return template.format(**ctx)


def join_labels(labels: list[str] | None, *, empty: str = "全部") -> str:
    """将多选 label 列表拼成可读短句；空列表表示未筛选。"""
    if not labels:
        return empty
    return "、".join(labels)
