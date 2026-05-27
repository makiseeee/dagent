from datetime import date, datetime, timedelta
import re


ZH_WEEKDAY = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


def parse_base_date(base_date: str) -> date:
    return datetime.strptime(base_date, "%Y-%m-%d").date()


def next_or_same_weekday(base: date, target_weekday: int) -> date:
    delta = target_weekday - base.weekday()
    if delta < 0:
        delta += 7
    return base + timedelta(days=delta)


def next_weekday(base: date, target_weekday: int) -> date:
    start_next_week = base + timedelta(days=(7 - base.weekday()))
    return start_next_week + timedelta(days=target_weekday)


def resolve_explicit_date(content: str, base_date: str) -> tuple[str | None, str | None]:
    """
    Return (resolved_date, matched_text).

    If no explicit date is found, return (None, None).
    """
    base = parse_base_date(base_date)

    normalized = content.replace("\u3000", " ")

    if "今天" in normalized or "今日" in normalized:
        return base.isoformat(), "今天"

    if "明天" in normalized or "明日" in normalized:
        return (base + timedelta(days=1)).isoformat(), "明天"

    if "后天" in normalized:
        return (base + timedelta(days=2)).isoformat(), "后天"

    # 下周一 / 下周二 ...
    m = re.search(r"下\s*周\s*([一二三四五六日天])", normalized)
    if m:
        target = ZH_WEEKDAY[m.group(1)]
        return next_weekday(base, target).isoformat(), m.group(0)

    # 这周五 / 本周五
    m = re.search(r"(?:这|本)\s*周\s*([一二三四五六日天])", normalized)
    if m:
        target = ZH_WEEKDAY[m.group(1)]
        return next_or_same_weekday(base, target).isoformat(), m.group(0)

    # 周一 / 周二 / 星期三 / 礼拜五
    m = re.search(r"(?:周|星期|礼拜)\s*([一二三四五六日天])", normalized)
    if m:
        target = ZH_WEEKDAY[m.group(1)]
        return next_or_same_weekday(base, target).isoformat(), m.group(0)

    # 5月27号 / 5 月 27 号 / 5月27日
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[号日]", normalized)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        resolved = date(base.year, month, day)

        # 如果这个月日已经明显过去，认为是明年。
        if resolved < base:
            resolved = date(base.year + 1, month, day)

        return resolved.isoformat(), m.group(0)

    # 27号 / 27 号 / 27日 / 27 日
    m = re.search(r"(?<!\d)(\d{1,2})\s*[号日]", normalized)
    if m:
        day = int(m.group(1))
        resolved = date(base.year, base.month, day)

        # 如果这个日期已经过去，就认为是下个月。
        if resolved < base:
            if base.month == 12:
                resolved = date(base.year + 1, 1, day)
            else:
                resolved = date(base.year, base.month + 1, day)

        return resolved.isoformat(), m.group(0)

    return None, None