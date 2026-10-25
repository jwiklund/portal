import asyncio

from blacksheep.testing import TestClient

from born_portal.main import app


def test_security_headers_on_public_page():
    async def run():
        if not app.started:
            await app.start()
        client = TestClient(app)
        return await client.get("/login")

    response = asyncio.run(run())

    headers = {k.decode().lower(): v.decode() for k, v in response.headers}
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in headers["content-security-policy"]
    # Safari/Chrome apply form-action to redirects, so the Spotify authorize
    # redirect after the create-playlist form POST must be explicitly allowed.
    assert "https://accounts.spotify.com" in headers["content-security-policy"]
