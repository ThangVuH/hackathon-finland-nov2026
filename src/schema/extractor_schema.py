from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class TextElement:
    content: str
    bbox: list[float]
    confidence: float | None = None
    source: str = "native"


@dataclass
class GeometryElement:
    type: str
    coordinates: Any
    properties: dict = field(default_factory=dict)


@dataclass
class Page:
    page_number: int
    width: float
    height: float
    texts: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    geometry: list = field(default_factory=list)
    coordinate_system: str = "top_left"
    unit: str = "unknown"


@dataclass
class Document:
    document_id: str
    source_file: str
    format: str
    pages: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)