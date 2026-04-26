from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EventData:
    name: str
    description: str
    location: Optional[str] = None
    price: Optional[str] = None
    date: Optional[str] = None
