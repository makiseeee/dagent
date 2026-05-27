from pydantic import BaseModel


class ScheduleItem(BaseModel):
    date: str
    content: str
    raw_line: str
    source_file: str
    line_number: int

    time: str | None = None
    created_time: str | None = None

    effective_date: str | None = None
    date_source: str = "note_default"
    explicit_date_text: str | None = None

    done: bool | None = None

    # 原始形态：memo / task / event
    item_type: str = "memo"

    # agent 整理时建议转成什么：task / event / reminder / backlog / note
    suggested_type: str | None = None

    # 是否像一个可执行事项
    actionable: bool = False

    tags: list[str] = []
    organized: bool = False
    section: str | None = None

