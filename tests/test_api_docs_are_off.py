"""The three pages FastAPI builds from the routes are not served.

/docs, /redoc and /openapi.json come for free with FastAPI and are open to
anybody, signed in or not. The last one is the whole app written out: every
address, every form field, every parameter and its type. That is a gift to
somebody looking for a way in, and nothing here reads them, so they are off.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

BUILT_IN = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]


@pytest.mark.parametrize("address", BUILT_IN)
def test_the_built_in_api_pages_are_not_there(address):
    client = TestClient(app)
    assert client.get(address).status_code == 404


def test_the_app_itself_does_not_offer_a_schema():
    # Not only unrouted: the schema is never built, so nothing can hand it
    # out by another name either.
    assert app.openapi_url is None
    assert app.docs_url is None and app.redoc_url is None
    assert not any(getattr(route, "path", "") in BUILT_IN for route in app.routes)


def test_the_front_door_still_opens():
    # The same switch can turn off more than intended, so the ordinary page
    # a signed out student lands on is checked here too.
    client = TestClient(app)
    assert client.get("/start").status_code == 200
