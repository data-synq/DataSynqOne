from pydantic import BaseModel


class TagRef(BaseModel):
    id: int
    name: str
    color: str


class DocSummary(BaseModel):
    id: int
    title: str
    created: str
    correspondent_name: str | None
    document_type_name: str | None
    tags: list[TagRef]
    status: str
    due_date: str | None
    content: str | None = None


class Deadline(BaseModel):
    document_id: int
    title: str
    correspondent_name: str | None
    due_date: str
    days_until: int


class ChartData(BaseModel):
    labels: list[str]
    data: list[int]


class DashboardOverview(BaseModel):
    kpis: dict[str, int]
    by_status: dict[str, list[DocSummary]]
    deadlines: list[Deadline]
    recent: list[DocSummary]
    charts: dict[str, ChartData]
    generated_at: str
