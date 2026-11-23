"""The wide layout: which screens carry what, and who may see a thread.

The layout itself is stylesheet work and a browser's job to judge. What is
worth holding here is the part the server decides: the bar at the foot of a
phone belongs to five screens and no others, the chat column is not drawn
where it would be the same list twice, and above all it never opens a
conversation this student is not in.
"""
import pytest
from fastapi.testclient import TestClient

from app import db, passwords
from app.main import app

ORIGIN = {"origin": "http://testserver"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.sqlite3"))
    db.setup()
    users = [db.create_user(f"{20000 + n}@novasbe.pt", name, "finance",
                            passwords.hash_password("TestPassword1!"))
             for n, name in enumerate(("owner", "asker", "stranger"))]
    conn = db.connect()
    with conn:
        conn.execute("UPDATE users SET verified=1")
    conn.close()
    clients = []
    for member in users:
        client = TestClient(app)
        assert client.post("/dev", data={"user_id": member}, headers=ORIGIN,
                           follow_redirects=False).status_code == 303
        clients.append(client)
    listing = db.create_listing(users[0], "item", "A desk", price=20)
    conv = db.open_conversation(listing, users[1])
    db.send_message(conv, users[1], "Is it still there?")
    return {"users": users, "clients": clients, "listing": listing, "conv": conv}


FOOT = ["/market", "/chats", "/profile"]
NO_FOOT = ["/new?kind=item", "/courses", "/profile/notifications", "/profile/edit"]


@pytest.mark.parametrize("path", FOOT)
def test_these_screens_keep_the_bar_at_the_foot(world, path):
    page = world["clients"][0].get(path).text
    assert 'class="tabbar tabbar--foot"' in page, path


@pytest.mark.parametrize("path", NO_FOOT)
def test_and_these_do_not(world, path):
    """A form or a settings screen is somewhere you came to and leave by its
    own arrow. A bar under it offers a second way out that drops the form."""
    page = world["clients"][0].get(path).text
    assert 'class="tabbar"' in page, path
    assert "tabbar--foot" not in page, path


def test_an_entry_and_a_form_still_reach_the_tabs(world):
    """They had no nav at all before. On a wide screen they have the rail."""
    for path in (f"/listing/{world['listing']}", "/new?kind=item"):
        assert 'class="tabbar"' in world["clients"][0].get(path).text, path


def test_the_chat_column_is_not_drawn_where_it_would_repeat_itself(world):
    client = world["clients"][1]
    assert 'class="dock"' in client.get("/market").text
    assert 'class="dock"' not in client.get("/chats").text
    assert 'class="dock"' not in client.get(f"/chat/{world['conv']}").text


def test_signed_out_has_no_rail_and_no_column(world):
    out = TestClient(app).get("/start").text
    assert "shell--out" in out
    assert 'class="tabbar"' not in out
    assert 'class="dock"' not in out


def test_the_column_opens_a_thread_you_are_in(world):
    page = world["clients"][1].get(f"/market?chat={world['conv']}").text
    assert "Is it still there?" in page
    assert 'class="dock-thread"' in page


def test_the_column_never_opens_somebody_elses(world):
    """The id is in the address, so anyone can type any number into it."""
    page = world["clients"][2].get(f"/market?chat={world['conv']}").text
    assert "Is it still there?" not in page
    assert 'class="dock-thread"' not in page
    for rubbish in ("999999", "abc", "-1", ""):
        answer = world["clients"][2].get(f"/market?chat={rubbish}")
        assert answer.status_code == 200
        assert 'class="dock-thread"' not in answer.text


def test_writing_from_an_entry_opens_the_column_when_it_is_there(world):
    """The form says whether the column is on screen; the server follows."""
    client, listing = world["clients"][1], world["listing"]
    beside = client.post(f"/listing/{listing}/chat", data={"beside": "1"},
                         headers=ORIGIN, follow_redirects=False)
    assert beside.headers["location"] == f"/listing/{listing}?chat={world['conv']}"

    alone = client.post(f"/listing/{listing}/chat", data={"beside": ""},
                        headers=ORIGIN, follow_redirects=False)
    assert alone.headers["location"] == f"/chat/{world['conv']}?back=/listing/{listing}"


def test_sending_from_the_column_comes_back_to_the_same_page(world):
    client, conv = world["clients"][1], world["conv"]
    answer = client.post(f"/chat/{conv}", headers=ORIGIN, follow_redirects=False,
                         data={"body": "Still interested", "back": f"/listing/{world['listing']}"})
    assert answer.headers["location"].startswith(f"/chat/{conv}?back=")
    assert "Still interested" in client.get(f"/market?chat={conv}").text
