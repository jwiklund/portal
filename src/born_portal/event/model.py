from sqlmodel import Field, SQLModel


class EventData(SQLModel, table=True):
    __tablename__ = "events"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    url: str = Field(unique=True, index=True)
    name: str = ""
    description: str = ""
    location: str | None = None
    price: str | None = None
    date: str | None = None
    ticket: bool = False
