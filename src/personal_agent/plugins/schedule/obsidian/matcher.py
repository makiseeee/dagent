import re
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    text = text.lower().strip()

    replacements = {
        "figure": "fig",
        "，": ",",
        "。": ".",
        "：": ":",
        "（": "(",
        "）": ")",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "vla": "vla",
        "agent": "agent",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # 去掉常见口语词
    for word in ["记得", "一下", "的时候", "有空", "尝试"]:
        text = text.replace(word, "")

    # 去掉标点和空白
    text = re.sub(r"[\s,，。.!！?？:：;；\-—_、/\\()\[\]（）【】\"']", "", text)

    return text


def text_similarity(a: str, b: str) -> float:
    na = normalize_text(a)
    nb = normalize_text(b)

    if not na or not nb:
        return 0.0

    if na in nb or nb in na:
        return 1.0

    return SequenceMatcher(None, na, nb).ratio()


def is_same_or_rewrite(source: str, target: str, threshold: float = 0.72) -> bool:
    return text_similarity(source, target) >= threshold