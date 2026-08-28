from dataclasses import dataclass


@dataclass(frozen=True)
class EventData:
    id: int | None = None
    url: str = ""
    name: str = ""
    description: str = ""
    location: str | None = None
    price: str | None = None
    date: str | None = None
    ticket: bool = False
