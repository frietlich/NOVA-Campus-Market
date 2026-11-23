"""Search and the filter buttons on the tabs, from the address down to SQL.

Most of these go through the real /market and /tickets pages, so a filter
that the database answers right but the page drops would still fail.
"""
import re
from datetime import date, timedelta

import pytest

from app import db
from test_security import world  # noqa: F401  (pytest fixture)


def shown(client, address):
    """The titles a tab shows, in the order it shows them."""
    response = client.get(address)
    assert response.status_code == 200, response.text
    ids = re.findall(r'href="/listing/(\d+)"', response.text)
    seen = list(dict.fromkeys(int(i) for i in ids))
    return [db.get_listing(i)["title"] for i in seen]


@pytest.fixture
def market(world):  # noqa: F811
    users, clients = world
    seller = users[0]
    for title, price, cat, cond in [
        ("iPad Air",        290, "electronics", "like_new"),
        ("Monitor",          95, "electronics", "used"),
        ("Desk lamp",        10, "furniture",   "used"),
        ("Bookshelf",         9, "furniture",   "used"),
        ("Free sofa",      None, "furniture",   "well_used"),
        ("Old entry",        50, None,          None),   # from before categories
    ]:
        db.create_listing(seller, "item", title, price=price,
                          category=cat, condition=cond)
    return clients[1]


def test_a_category_shows_only_its_entries(market):
    assert sorted(shown(market, "/market?cat=electronics")) == ["Monitor", "iPad Air"]


def test_an_entry_without_a_category_appears_unfiltered_but_never_under_one(market):
    assert "Old entry" in shown(market, "/market")
    for cat in ("electronics", "furniture", "other"):
        assert "Old entry" not in shown(market, f"/market?cat={cat}")


def test_category_and_condition_must_both_hold(market):
    assert shown(market, "/market?cat=electronics&cond=used") == ["Monitor"]
    assert shown(market, "/market?cat=electronics&cond=new") == []


@pytest.mark.parametrize("band, expected", [
    # Under means under: an entry at exactly 10 is not under 10.
    ("10",   {"Bookshelf", "Free sofa"}),
    # No price is free, and free is under every ceiling.
    ("50",   {"Bookshelf", "Desk lamp", "Free sofa"}),
    ("free", {"Free sofa"}),
    # 50 and up starts at 50 and never includes the free ones.
    # Sent by the form as 50%2B, because a bare + in an address is a space.
    ("50%2B", {"Old entry", "Monitor", "iPad Air"}),
])
def test_price_bands_and_their_edges(market, band, expected):
    assert set(shown(market, f"/market?price={band}")) == expected


def test_cheapest_first_puts_free_at_the_top(market):
    order = shown(market, "/market?sort=low")
    assert order[0] == "Free sofa"
    assert order[1:] == ["Bookshelf", "Desk lamp", "Old entry", "Monitor", "iPad Air"]
    assert shown(market, "/market?sort=high")[0] == "iPad Air"


@pytest.mark.parametrize("address", [
    "/market?cat=weapons", "/market?price=-5", "/market?sort=;drop",
    "/market?cond=mint", "/market?price=50+",
])
def test_an_unknown_value_in_the_address_is_ignored_not_an_error(market, address):
    # A hand typed or outdated link falls back to the unfiltered part, never a 500.
    assert len(shown(market, address)) >= 5


def test_every_word_has_to_match_but_not_in_one_column(world):  # noqa: F811
    users, clients = world
    db.create_listing(users[0], "item", "iPad", description="Air, 64 GB",
                      price=200, category="electronics")
    db.create_listing(users[0], "item", "Air fryer", price=30, category="other")
    assert shown(clients[1], "/market?q=air+ipad") == ["iPad"]
    assert shown(clients[1], "/market?q=IPAD") == ["iPad"]


def test_the_label_printed_on_a_card_is_searchable(world):  # noqa: F811
    # The card says "Electronics" and "Like new", the database says
    # electronics and like_new, and both have to be findable by what is shown.
    users, clients = world
    db.create_listing(users[0], "item", "Headphones", price=60,
                      category="electronics", condition="like_new")
    assert shown(clients[1], "/market?q=like+new") == ["Headphones"]
    assert shown(clients[1], "/market?q=Electronics") == ["Headphones"]


def test_closed_entries_leave_the_tab(world):  # noqa: F811
    users, clients = world
    gone = db.create_listing(users[0], "item", "Sold bike", price=80)
    db.create_listing(users[0], "item", "Bike for sale", price=90)
    assert db.close_listing(gone, users[0])
    assert shown(clients[1], "/market?q=bike") == ["Bike for sale"]


def test_only_the_owner_can_close_an_entry(world):  # noqa: F811
    users, _ = world
    entry = db.create_listing(users[0], "item", "Chair", price=5)
    assert not db.close_listing(entry, users[1])
    assert db.get_listing(entry)["status"] == "open"


# ------------------------------------------------------------------ tickets

def test_a_ticket_stays_listed_on_the_day_and_leaves_the_day_after(world):  # noqa: F811
    users, clients = world
    today = date.fromisoformat(db.active_day())
    for title, day in [("Yesterday", -1), ("Tonight", 0), ("Next week", 7)]:
        db.create_listing(users[0], "ticket", title, price=10, category="party",
                          event_date=(today + timedelta(days=day)).isoformat(),
                          place="Lux")
    assert set(shown(clients[1], "/tickets")) == {"Tonight", "Next week"}


@pytest.mark.parametrize("typed, hint", [
    ("5 Dec",      "-12-05"),
    ("december 5", "-12-05"),
    ("05.12",      "-12-05"),
    ("5/12",       "-12-05"),
    ("Dec",        "-12-"),
    ("2026-12-05", "2026-12-05"),
    ("2026",       None),     # a year alone is no date to search by
    ("40 Dec",     "-12-"),   # no 40th day, so only the month is kept
    ("ipad",       None),
    ("",           None),
])
def test_dates_typed_the_way_people_type_them(typed, hint):
    assert db.date_hint(typed) == hint


def test_a_typed_date_finds_the_ticket_on_that_day(world):  # noqa: F811
    users, clients = world
    year = date.fromisoformat(db.active_day()).year + 1
    db.create_listing(users[0], "ticket", "Winter party", price=10, category="party",
                      event_date=f"{year}-12-05", place="Lux")
    db.create_listing(users[0], "ticket", "Other party", price=10, category="party",
                      event_date=f"{year}-12-06", place="Lux")
    assert shown(clients[1], "/tickets?q=5+Dec") == ["Winter party"]
