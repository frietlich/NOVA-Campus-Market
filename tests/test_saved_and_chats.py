"""The heart on an entry, and putting chats away. Each side only ever sees its own."""
from datetime import date, timedelta

from app import db
from test_security import world  # noqa: F401  (pytest fixture)


def test_the_heart_toggles_and_the_count_never_says_who(world):  # noqa: F811
    users, _ = world
    alice, bob, clara = users
    entry = db.create_listing(alice, "item", "Lamp", price=5)
    assert db.toggle_save(bob, entry) is True
    assert db.toggle_save(clara, entry) is True
    assert db.save_count(entry) == 2
    assert db.toggle_save(bob, entry) is False
    assert not db.is_saved(bob, entry) and db.is_saved(clara, entry)
    assert db.save_count(entry) == 1


def test_a_heart_on_something_that_does_not_exist_is_refused(world):  # noqa: F811
    users, _ = world
    assert db.toggle_save(users[0], 999_999) is False
    assert db.saved_listings(users[0]) == []


def test_saved_list_keeps_closed_entries_at_the_bottom_and_drops_past_tickets(world):  # noqa: F811
    users, _ = world
    alice, bob, _ = users
    today = date.fromisoformat(db.active_day())
    closed = db.create_listing(alice, "item", "Sold already", price=5)
    live = db.create_listing(alice, "item", "Still for sale", price=5)
    past = db.create_listing(alice, "ticket", "Last week", price=5, category="party",
                             event_date=(today - timedelta(days=7)).isoformat(), place="Lux")
    for entry in (closed, live, past):
        db.toggle_save(bob, entry)
    db.close_listing(closed, alice)
    assert [row["title"] for row in db.saved_listings(bob)] == ["Still for sale", "Sold already"]


def test_archiving_a_chat_hides_it_for_one_side_only(world):  # noqa: F811
    users, _ = world
    alice, bob, clara = users
    entry = db.create_listing(alice, "item", "Desk", price=20)
    conv = db.open_conversation(entry, bob)
    db.send_message(conv, bob, "Still there?")

    def archived(user):
        return {row["id"]: row["archived"] for row in db.conversations_of(user)}[conv]

    assert db.archive_chat(conv, bob) is True
    assert archived(bob) is not None
    assert archived(alice) is None

    # Somebody outside the chat cannot touch it.
    assert db.archive_chat(conv, clara) is False
    assert db.archive_chat(conv, bob, on=False) is True
    assert archived(bob) is None
