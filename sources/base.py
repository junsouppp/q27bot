from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Posting:
    firm: str
    external_id: str
    title: str
    location: str
    url: str
    source: str  # "greenhouse" | "lever" | "ashby" | "simplify" | "northwestern"
    posted_at: Optional[str] = None

    def key(self) -> str:
        return f"{self.firm}::{self.external_id}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Posting":
        return cls(
            firm=d["firm"],
            external_id=d["external_id"],
            title=d["title"],
            location=d.get("location", ""),
            url=d["url"],
            source=d["source"],
            posted_at=d.get("posted_at"),
        )
