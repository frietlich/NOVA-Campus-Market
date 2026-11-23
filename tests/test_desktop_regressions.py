"""Desktop/live-chat regressions, separate from security-only checks."""
from fastapi.testclient import TestClient
from app import db, main
from test_security import world, ORIGIN


def test_dock_back_and_send_keep_listing_page(world):
    users, clients = world
    listing = db.create_listing(users[0], "item", "Chair", price=1)
    chat = db.open_conversation(listing, users[1])
    page = clients[0].get(f"/market?chat={chat}").text
    assert 'href="/market" aria-label="Back to all chats"' in page
    response = clients[0].post(f"/chat/{chat}?beside=1", data={"body": "Hello", "back": f"/market?chat={chat}"},
                               headers=ORIGIN, follow_redirects=False)
    assert response.headers["location"] == f"/market?chat={chat}"
    assert clients[1].get(f"/chat/{chat}/messages").json()["messages"][-1]["body"] == "Hello"
    assert clients[2].get(f"/chat/{chat}/messages").status_code == 403
    assert TestClient(main.app).get(f"/chat/{chat}/messages").status_code == 403


def test_live_messages_keep_escaping_and_read_receipts(world):
    users, clients = world
    listing = db.create_listing(users[0], "item", "Private chat", price=1)
    chat = db.open_conversation(listing, users[1])
    db.send_message(chat, users[1], "<script>bad()</script>")
    data = clients[0].get(f"/chat/{chat}/messages").json()
    assert "<script>bad()</script>" not in data["html"]
    assert "&lt;script&gt;" in data["html"]
    assert not db.messages_of(chat)[0]["read_at"]
    assert clients[0].post(f"/chat/{chat}/read", data={"through": data["messages"][-1]["id"]},
                           headers=ORIGIN).status_code == 200
    assert db.messages_of(chat)[0]["read_at"]


def test_hidden_dock_and_message_fetch_do_not_mark_read(world):
    users, clients = world
    listing = db.create_listing(users[0], "item", "Chair", price=1)
    chat = db.open_conversation(listing, users[1])
    db.send_message(chat, users[1], "Unread until visible")
    assert clients[0].get(f"/market?chat={chat}").status_code == 200
    assert db.unread_total(users[0]) == 1
    data = clients[0].get(f"/chat/{chat}/messages").json()
    assert data["has_unread"]
    assert db.unread_total(users[0]) == 1
    latest_seen = data["messages"][-1]["id"]
    db.send_message(chat, users[1], "Arrived after the last render")
    assert clients[0].post(f"/chat/{chat}/read", data={"through": latest_seen},
                           headers=ORIGIN).status_code == 200
    messages = db.messages_of(chat)
    assert messages[0]["read_at"] and not messages[1]["read_at"]
    assert clients[2].post(f"/chat/{chat}/read", data={"through": latest_seen},
                           headers=ORIGIN).status_code == 403
    assert clients[0].post(f"/chat/{chat}/read", data={"through": "9" * 50},
                           headers=ORIGIN).status_code == 400
    assert clients[0].post(f"/chat/{chat}/read", data={"through": latest_seen}).status_code == 403


def test_live_chat_overview_updates_are_private_and_do_not_mark_read(world):
    users, clients = world
    listing = db.create_listing(users[0], "item", "Private overview", price=1)
    chat = db.open_conversation(listing, users[1])
    before = clients[0].get("/chats/updates", params={"page_url": "/market?q=desk"}).json()
    db.send_message(chat, users[1], "PRIVATE_OVERVIEW_MARKER <script>bad()</script>")
    response = clients[0].get("/chats/updates", params={"page_url": "/market?q=desk"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["version"] != before["version"] and data["unread"] == 1
    assert "PRIVATE_OVERVIEW_MARKER" in data["dock_html"]
    assert "<script>bad()</script>" not in data["dock_html"]
    assert "/market?q=desk&amp;chat=" in data["dock_html"]
    assert not db.messages_of(chat)[0]["read_at"]
    assert "PRIVATE_OVERVIEW_MARKER" not in clients[2].get("/chats/updates").text
    assert TestClient(main.app).get("/chats/updates").status_code == 403
    clients[0].post(f"/chat/{chat}/read", data={"through": db.messages_of(chat)[0]["id"]}, headers=ORIGIN)
    assert clients[0].get("/chats/updates").json()["unread"] == 0


def test_live_chat_overview_uses_local_links_only(world):
    users, clients = world
    listing = db.create_listing(users[0], "item", "Chair", price=1)
    db.open_conversation(listing, users[1])
    data = clients[0].get("/chats/updates", params={"page_url": "//attacker.invalid"}).json()
    assert "attacker.invalid" not in data["dock_html"]
    assert "/housing?chat=" in data["dock_html"]
