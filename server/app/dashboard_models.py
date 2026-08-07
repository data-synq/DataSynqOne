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
    # Aus der Tag-Taxonomie, nicht aus Paperless' document_type — der bleibt
    # im Bestand fast überall leer. Der Slug wird in der Oberfläche beschriftet.
    category: str | None
    object_name: str | None
    tags: list[TagRef]
    status: str
    due_date: str | None
    content: str | None = None


class Deadline(BaseModel):
    document_id: int
    title: str
    correspondent_name: str | None
    object_name: str | None
    due_date: str
    days_until: int


class ChartData(BaseModel):
    labels: list[str]
    data: list[int]


class DashboardOverview(BaseModel):
    kpis: dict[str, int]
    # Eine nach Dringlichkeit sortierte Liste, kein Board mit drei Spalten:
    # das Dashboard fragt "womit fange ich an", nicht "wie viel liegt wo".
    queue: list[DocSummary]
    objects: list[str]
    deadlines: list[Deadline]
    recent: list[DocSummary]
    charts: dict[str, ChartData]
    generated_at: str
