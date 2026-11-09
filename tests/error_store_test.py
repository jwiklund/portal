import asyncio

from blacksheep import Request
from blacksheep.contents import Content
from sqlmodel import SQLModel, create_engine

from born_portal.errors import configure, record_error
from born_portal.errors.model import ErrorRecord
from born_portal.errors.store import ErrorStore


def make_store(tmp_path) -> tuple[ErrorStore, object]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return ErrorStore(engine), engine


def test_save_list_get_clear(tmp_path):
    store, _ = make_store(tmp_path)
    row_id = store.save(ErrorRecord(method="GET", path="/x", message="boom"))

    assert store.count() == 1
    rows = store.list_recent()
    assert [r.id for r in rows] == [row_id]

    loaded = store.get_by_id(row_id)
    assert loaded is not None
    assert loaded.message == "boom"

    assert store.clear() == 1
    assert store.count() == 0
    assert store.get_by_id(row_id) is None


def test_record_error_redacts_query_and_json_body(tmp_path):
    store, engine = make_store(tmp_path)
    configure(engine)

    request = Request(
        "POST",
        b"/spotify/callback?code=SECRET-CODE&state=SECRET-STATE&q=music",
        [(b"content-type", b"application/json")],
    )
    request.content = Content(
        b"application/json",
        b'{"code": "SECRET-CODE", "name": "keep", "access_token": "SECRET-TOKEN"}',
    )

    asyncio.run(record_error(request, ValueError("boom")))

    record = store.list_recent()[0]
    assert record.method == "POST"
    assert record.path == "/spotify/callback"
    assert record.exception_type == "ValueError"
    # Sensitive query values are masked, non-sensitive ones are kept.
    assert "code=%5Bredacted%5D" in record.query
    assert "state=%5Bredacted%5D" in record.query
    assert "q=music" in record.query
    # Sensitive JSON fields are masked, safe ones are kept.
    assert '"name": "keep"' in record.input
    assert "SECRET-CODE" not in record.query
    assert "SECRET-CODE" not in record.input
    assert "SECRET-TOKEN" not in record.input
    assert "ValueError: boom" in record.traceback


def test_record_error_without_request(tmp_path):
    store, engine = make_store(tmp_path)
    configure(engine)

    asyncio.run(record_error(None, RuntimeError("nope"), context={"file": "x.mkv"}))

    record = store.list_recent()[0]
    assert record.method == ""
    assert record.path == ""
    assert record.exception_type == "RuntimeError"
    assert record.context == '{"file": "x.mkv"}'
