"""The welcome tour is shown once per account, not once per browser.

The browser used to decide this out of its own store, which meant a second
laptop welcomed a student who had been using the app for weeks, and a new
student on a shared machine never got the welcome at all. The answer lives
on the account now, and the page carries it in data-tour on the body.
"""
from fastapi.testclient import TestClient

from app import db
from app.main import app
from test_security import ORIGIN, world  # noqa: F401  (pytest fixture)


def tour_flag(client, address="/housing"):
    """What the page tells the script to do: "new" or "done"."""
    response = client.get(address)
    assert response.status_code == 200, response.text
    body = response.text.split("<body", 1)[1].split(">", 1)[0]
    assert 'data-tour="' in body, body
    return body.split('data-tour="', 1)[1].split('"', 1)[0]


def test_a_new_account_has_the_tour_coming(world):  # noqa: F811
    users, clients = world
    assert db.get_user(users[0])["tour_seen"] == 0
    assert tour_flag(clients[0]) == "new"


def test_an_account_that_has_had_it_never_gets_it_again(world):  # noqa: F811
    users, clients = world
    db.mark_tour_seen(users[0])
    assert tour_flag(clients[0]) == "done"
    # Not on any other screen either, and not after signing in somewhere new.
    for address in ("/tickets", "/market", "/groups", "/chats", "/profile"):
        assert tour_flag(clients[0], address) == "done"


def test_finishing_or_skipping_writes_it_on_the_account(world):  # noqa: F811
    users, clients = world
    assert clients[0].post("/tour/seen", headers=ORIGIN).status_code == 200
    assert db.get_user(users[0])["tour_seen"] == 1
    assert tour_flag(clients[0]) == "done"


def test_one_student_finishing_it_does_not_speak_for_another(world):  # noqa: F811
    users, clients = world
    clients[0].post("/tour/seen", headers=ORIGIN)
    assert db.get_user(users[1])["tour_seen"] == 0
    assert tour_flag(clients[1]) == "new"


def test_signed_out_there_is_nobody_to_welcome(world):  # noqa: F811
    # The tour needs an account to be remembered against, so the signed out
    # pages say done and the script never starts.
    out = TestClient(app)
    assert tour_flag(out, "/start") == "done"
    # And the page that records it does not fall over without one.
    assert out.post("/tour/seen", headers=ORIGIN).status_code == 200


def test_asking_for_the_tour_is_not_handed_on_to_the_links(world):  # noqa: F811
    # ?tour=1 plays the tour once. A sign-up lands on /housing?tour=1, and
    # the chat column used to copy it into every link and form, so after
    # Skip the next click in that column started the tour all over again.
    users, clients = world
    listing = db.create_listing(users[1], "item", "A desk", price=20)
    db.open_conversation(listing, users[0])
    for address in ("/housing?tour=1", "/market?tour=1&category=books",
                    "/chats?tour=1"):
        page = clients[0].get(address).text
        assert "tour=1" not in page, address
        assert 'name="tour"' not in page, address
