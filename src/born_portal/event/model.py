from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EventData:
    id: Optional[int] = None
    url: str = ""
    name: str = ""
    description: str = ""
    location: Optional[str] = None
    price: Optional[str] = None
    date: Optional[str] = None
    ticket: bool = False
