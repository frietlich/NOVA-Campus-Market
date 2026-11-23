"""Signing up and logging in, through the real pages.

The happy path of signing up and the code itself are in test_security.py.
These are the ways it can go wrong, and what must not happen when it does.
"""
import pytest
from fastapi.testclient import TestClient

from app import db, mailer, passwords, programmes
from app.main import app
from test_security import ORIGIN, world  # noqa: F401  (pytest fixture)

GOOD = {
    "name": "New Student",
    "programme": programmes.BACHELOR[0],
    "email": "54321@novasbe.pt",
    "password": "TestPassword1!",
    "password2": "TestPassword1!",
}


@pytest.fixture
def outbox(world, monkeypatch):  # noqa: F811
    """Codes that would have been e-mailed, instead of sending them."""
    sent = []
    monkeypatch.setattr(mailer, "is_set_up", lambda: True)
    monkeypatch.setattr(mailer, "send_code",
                        lambda to, code, why: sent.append((to, code, why)) or True)
    return sent


def join(**changes):
    client = TestClient(app)
    response = client.post("/join", data={**GOOD, **changes}, headers=ORIGIN,
                           follow_redirects=False)
    return client, response


@pytest.mark.parametrize("changes, message", [
    ({"name": "   "},                         "your name"),
    ({"name": "x" * (db.NAME_MAX + 1)},        f"at most {db.NAME_MAX}"),
    ({"email": "someone@gmail.com"},           "Nova address"),
    ({"email": "1234@novasbe.pt"},             "Nova address"),   # one digit short
    ({"password2": "TestPassword1?"},          "not the same"),
    ({"password": "short", "password2": "short"}, "at least 8"),
    ({"programme": "Bachelor in Astrology"},   "from the list"),
    ({"programme": programmes.CEMS},           "only comes with a master"),
    ({"programme": programmes.CEMS,
      "cems_programme": programmes.BACHELOR[0]}, "from the list"),
])
def test_a_refused_signup_says_why_keeps_the_form_and_creates_nobody(outbox, changes, message):
    before = len(db.all_users())
    _, response = join(**changes)
    assert response.status_code == 200
    assert message in response.text
    assert len(db.all_users()) == before
    assert outbox == []
    # What was typed is still there, so nobody has to start again.
    if "email" not in changes:
        assert GOOD["email"] in response.text


def test_an_address_with_a_finished_account_cannot_sign_up_again(outbox):
    _, first = join()
    user = db.get_user_by_email(GOOD["email"])
    db.check_code(user["id"], outbox[0][1])           # confirm it
    _, second = join(name="Impostor", email=GOOD["email"].upper())
    assert "already has an account" in second.text
    assert db.get_user(user["id"])["name"] == GOOD["name"]


def test_an_unfinished_signup_is_taken_over_not_duplicated(outbox):
    join()
    join(name="Second Try", password="OtherPassword2?", password2="OtherPassword2?")
    users = [u for u in db.all_users() if u["email"] == GOOD["email"]]
    assert len(users) == 1
    user = db.get_user(users[0]["id"])
    assert user["name"] == "Second Try"
    assert passwords.verify_password(user["password"], "OtherPassword2?")
    assert not passwords.verify_password(user["password"], GOOD["password"])
    # Within a minute no second e-mail goes out, and the first code still works.
    assert len(outbox) == 1
    assert db.check_code(user["id"], outbox[0][1]) == "ok"


# ------------------------------------------------------------------- login

def login(client, email, password):
    return client.post("/login", data={"email": email, "password": password},
                       headers=ORIGIN, follow_redirects=False)


def test_login_ignores_case_and_spaces_in_the_address(world):  # noqa: F811
    users, _ = world
    email = db.get_user(users[0])["email"]
    client = TestClient(app)
    response = login(client, f"  {email.upper()} ", "TestPassword1!")
    assert response.status_code == 303
    assert client.get("/housing", follow_redirects=False).status_code == 200


def test_a_wrong_password_and_an_unknown_address_get_the_same_answer(world):  # noqa: F811
    users, _ = world
    email = db.get_user(users[0])["email"]
    wrong = login(TestClient(app), email, "WrongPassword1!")
    unknown = login(TestClient(app), "99999@novasbe.pt", "WrongPassword1!")
    assert wrong.status_code == unknown.status_code == 200
    assert "do not go together" in wrong.text
    assert "do not go together" in unknown.text


def test_an_unconfirmed_account_is_sent_to_the_code_not_let_in(outbox):
    join()
    client = TestClient(app)
    response = login(client, GOOD["email"], GOOD["password"])
    assert response.status_code == 303
    assert response.headers["location"].startswith("/verify")
    assert client.get("/housing", follow_redirects=False).status_code == 303
    assert outbox[-1][2] == "join"


def test_logging_out_ends_the_session(world):  # noqa: F811
    _, clients = world
    assert clients[0].get("/housing", follow_redirects=False).status_code == 200
    clients[0].post("/logout", headers=ORIGIN)
    assert clients[0].get("/housing", follow_redirects=False).status_code == 303
