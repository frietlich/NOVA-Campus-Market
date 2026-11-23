"""Regression checks for the main-app audit; no real mail or API calls."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app import db, main
from test_security import world, ORIGIN


def test_simultaneous_chat_creation_does_not_lock_database(world):
    users, _ = world
    listing = db.create_listing(users[0], "item", "Concurrent chat", price=1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: db.open_conversation(listing, users[1]), range(24)))
    assert len(set(ids)) == 1
    assert db.create_listing(users[0], "item", "Next write", price=2)


@pytest.mark.parametrize("prefix", ["/static/uploads/", "/static//uploads/", "/static/%2e/uploads/", "/static/UPLOADS/", "/static/uploads%5c"])
def test_upload_auth_cannot_be_bypassed_by_path_normalization(world, prefix):
    # StaticFiles serves the real static directory, independent of upload fixtures.
    path = Path(main.HERE) / "static" / "uploads" / ("qa-" + uuid4().hex + ".png")
    path.parent.mkdir(exist_ok=True)
    Image.new("RGB", (2, 2)).save(path)
    try:
        assert TestClient(main.app).get(prefix + path.name).status_code == 403
        if "UPLOADS" not in prefix and "%5c" not in prefix:
            response = world[1][0].get(prefix + path.name)
            assert response.status_code == 200
            # Out of every shared cache on the way, which is what this test
            # is about, but not out of the reader's own browser: no-store
            # fetched every thumbnail again on every list.
            assert response.headers["cache-control"] == "private, max-age=86400"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.parametrize("value", ["²", "9" * 50, "9" * 5000, "abc"])
def test_malformed_ids_never_crash(world, value):
    client = world[1][0]
    assert client.get("/market", params={"chat": value}).status_code == 200
    assert client.post("/courses", data={"course_id": value}, headers=ORIGIN,
                       follow_redirects=False).status_code == 303




def test_old_sessions_rejected_after_password_change(world):
    users, clients = world
    db.set_password(users[0], "replacement-hash")
    assert clients[0].get("/profile", follow_redirects=False).status_code == 303


def test_closing_twice_only_sends_one_notice(world):
    users, _ = world
    listing = db.create_listing(users[0], "item", "Desk", price=1)
    chat = db.open_conversation(listing, users[1])
    assert db.close_listing(listing, users[0])
    assert not db.close_listing(listing, users[0])
    assert len(db.messages_of(chat)) == 1


def test_reset_after_join_explains_cooldown(world, monkeypatch):
    user = db.get_user(world[0][0])
    db.new_code(user["id"], "join")
    sent = []
    monkeypatch.setattr(main.mailer, "is_set_up", lambda: True)
    monkeypatch.setattr(main.mailer, "send_code", lambda *args: sent.append(args) or True)
    assert "Wait one minute" in main.send_code(db.get_user(user["id"]), "reset")
    assert not sent
    assert db.get_user(user["id"])["code_purpose"] == "join"


@pytest.mark.parametrize("back", ["//example.invalid", "/\\example.invalid/", "/\nexample.invalid"])
def test_backlinks_cannot_leave_site(back):
    assert main.ours(back) == ""


def test_ticket_error_retains_external_link_and_invalid_time_is_rejected(world):
    users, clients = world
    fields = {"kind": "ticket", "title": "Concert", "description": "Spare ticket",
              "price": "10", "event_date": "2099-12-01", "event_time": "25:99",
              "place": "Venue", "address": "Rua Nova 12, Lisbon", "quantity": "1",
              "category": "concert", "external_url": "https://dice.fm/event/test"}
    before = len(db.listings_of_user(users[0]))
    response = clients[0].post("/new", data=fields, headers=ORIGIN)
    assert response.status_code == 200
    assert len(db.listings_of_user(users[0])) == before
    assert 'value="https://dice.fm/event/test"' in response.text


def test_password_change_keeps_current_browser_and_revokes_other_browser(world):
    users, clients = world
    other = TestClient(main.app)
    other.post("/dev", data={"user_id": users[0]}, headers=ORIGIN)
    response = clients[0].post("/profile/password", headers=ORIGIN,
        data={"current": "TestPassword1!", "password": "NewPassword2!", "password2": "NewPassword2!"},
        follow_redirects=False)
    assert response.status_code == 303
    assert clients[0].get("/profile").status_code == 200
    assert other.get("/profile", follow_redirects=False).status_code == 303


def test_password_reset_revokes_existing_sessions(world, monkeypatch):
    users, clients = world
    sent = []
    monkeypatch.setattr(main.mailer, "is_set_up", lambda: True)
    monkeypatch.setattr(main.mailer, "send_code", lambda email, code, why: sent.append(code) or True)
    resetter = TestClient(main.app)
    assert resetter.post("/forgot", data={"email": db.get_user(users[0])["email"]}, headers=ORIGIN,
                         follow_redirects=False).status_code == 303
    fields = {f"d{i+1}": digit for i, digit in enumerate(sent[0])}
    fields.update(password="ResetPassword3!", password2="ResetPassword3!")
    assert resetter.post("/forgot/reset", data=fields, headers=ORIGIN,
                         follow_redirects=False).status_code == 303
    assert resetter.get("/profile").status_code == 200
    assert clients[0].get("/profile", follow_redirects=False).status_code == 303




def test_database_path_is_loaded_from_dotenv_before_db_import(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    package = tmp_path / "app"
    package.mkdir()
    for name in ("__init__.py", "db.py", "categories.py", "mailer.py"):
        source = Path(db.HERE) / name
        if source.exists():
            shutil.copyfile(source, package / name)
    expected = str(tmp_path / "from-env.sqlite3")
    (tmp_path / ".env").write_text("CAMPUS_DB=" + expected, encoding="utf-8")
    env = dict(os.environ)
    env.pop("CAMPUS_DB", None)
    result = subprocess.run([sys.executable, "-c", "from app import db; print(db.DB_PATH)"],
                            cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("beside", [False, True])
@pytest.mark.parametrize("body", ["x" * 501, "   "])
def test_rejected_chat_message_keeps_text_and_explains_error(world, beside, body):
    users, clients = world
    listing = db.create_listing(users[0], "item", "Chair", price=1)
    chat = db.open_conversation(listing, users[1])
    suffix = "?beside=1" if beside else ""
    response = clients[0].post(f"/chat/{chat}{suffix}",
        data={"body": body, "back": f"/market?chat={chat}"}, headers=ORIGIN)
    assert response.status_code == 200
    assert "Your text has been kept" in response.text
    assert f'value="{body}"' in response.text
    assert not db.messages_of(chat)


def test_chat_accepts_500_characters(world):
    users, clients = world
    listing = db.create_listing(users[0], "item", "Chair", price=1)
    chat = db.open_conversation(listing, users[1])
    response = clients[0].post(f"/chat/{chat}", data={"body": "x" * 500},
                               headers=ORIGIN, follow_redirects=False)
    assert response.status_code == 303
    assert db.messages_of(chat)[0]["body"] == "x" * 500




def test_forgot_does_not_disclose_account_in_response_or_session(world, monkeypatch):
    import base64
    import json
    from itsdangerous import TimestampSigner
    deliveries = []
    monkeypatch.setattr(main.mailer, "is_set_up", lambda: True)
    monkeypatch.setattr(main.mailer, "send_code", lambda email, *args: deliveries.append(email) or True)
    known = db.get_user(world[0][0])["email"]
    pages = []
    for email in (known, "99999@novasbe.pt"):
        client = TestClient(main.app)
        response = client.post("/forgot", data={"email": email}, headers=ORIGIN, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/forgot/reset"
        session = json.loads(base64.b64decode(TimestampSigner(main.SECRET).unsign(client.cookies.get("session"))))
        assert session == {"reset_email": email}
        pages.append(client.get("/forgot/reset").text.replace(email, "EMAIL"))
        response = client.post("/forgot/reset/resend", headers=ORIGIN, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/forgot/reset?sent=1"
        response = client.post("/forgot/reset", data={"d1": "x", "password": "NewPassword2!", "password2": "NewPassword2!"}, headers=ORIGIN)
        assert "That code is invalid or expired" in response.text
    assert pages[0] == pages[1]
    assert deliveries == [known]


def test_forgot_delivery_failure_stays_generic(world, monkeypatch):
    monkeypatch.setattr(main.mailer, "is_set_up", lambda: True)
    monkeypatch.setattr(main.mailer, "send_code", lambda *args: False)
    client = TestClient(main.app)
    response = client.post("/forgot", data={"email": db.get_user(world[0][0])["email"]},
                           headers=ORIGIN, follow_redirects=False)
    assert response.status_code == 303
    assert "If" in client.get(response.headers["location"]).text


def test_a_photo_is_private_but_not_forbidden_to_the_browser(world):
    """The two halves of the header, each for its own reason.

    private keeps a student's photo out of any cache between us and them.
    Leaving no-store off lets their own browser keep it, which is the
    difference between a list of thumbnails that appears and one that
    loads again every time.
    """
    path = Path(main.HERE) / "static" / "uploads" / ("qa-" + uuid4().hex + ".png")
    path.parent.mkdir(exist_ok=True)
    Image.new("RGB", (2, 2)).save(path)
    try:
        header = world[1][0].get("/static/uploads/" + path.name).headers["cache-control"]
        assert "private" in header
        assert "no-store" not in header
    finally:
        path.unlink(missing_ok=True)


def test_a_page_is_still_never_kept(world):
    """Pages carry live state and must not come back out of any store."""
    for path in ("/housing", "/profile", "/chats"):
        assert world[1][0].get(path).headers["cache-control"] == "no-store"
