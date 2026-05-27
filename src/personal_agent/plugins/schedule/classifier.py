import re


ACTION_PATTERNS = [
    r"记得",
    r"提醒",
    r"交",
    r"上交",
    r"提交",
    r"问",
    r"联系",
    r"发",
    r"改",
    r"修改",
    r"做",
    r"完成",
    r"整理",
    r"复习",
    r"调研",
    r"部署",
    r"搭建",
    r"尝试",
    r"开始",
    r"继续",
    r"看一下",
    r"处理",
    r"报销",
    r"论文",
    r"作业",
]

def is_actionable_content(content: str) -> bool:
    text = content.strip()

    if not text:
        return False

    return any(re.search(pattern, text) for pattern in ACTION_PATTERNS)


def suggest_target_type(
    *,
    content: str,
    item_type: str,
    time: str | None,
    explicit_date_text: str | None,
) -> tuple[str | None, bool]:
    """
    Return (suggested_type, actionable).

    item_type 是原始形态，不一定等于最终要写入日程的类型。
    """

    if item_type == "event":
        return "event", True

    if item_type == "task":
        return "task", True

    if time is not None:
        return "event", True

    if explicit_date_text is not None:
        return "task", True

    if is_actionable_content(content):
        return "task", True

    return "note", False