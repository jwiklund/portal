import asyncio

from blacksheep import Application
from blacksheep.testing import TestClient
from sqlmodel import SQLModel, create_engine

from born_portal.errors import USER_ERROR_MESSAGE, register_routes
from born_portal.errors.store import ErrorStore


def test_unhandled_exception_is_recorded_and_shown(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)

    app = Application()

    @app.router.get("/boom")
    async def boom(request):
        raise ValueError("kaboom")

    register_routes(app, engine)

    async def run():
        if not app.started:
            await app.start()
        client = TestClient(app)
        missing = await client.get("/does-not-exist")
        response = await client.get("/boom")
        return missing, response, await response.text()

    missing, response, body = asyncio.run(run())

    # A missing route must not be logged as an application error.
    assert missing.status == 404
    # The user sees a generic message, never the traceback.
    assert response.status == 500
    assert USER_ERROR_MESSAGE in body
    assert "kaboom" not in body

    records = ErrorStore(engine).list_recent()
    assert len(records) == 1
    record = records[0]
    assert record.path == "/boom"
    assert record.exception_type == "ValueError"
    assert "kaboom" in record.message
