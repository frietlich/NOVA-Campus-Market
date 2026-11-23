"""The live count on the Housing filter button says what the list will show.

The button at the foot of the filter panel used to carry the number of the
list behind it, so after picking "to 750" and "Shared flat" it still said
"Show 9 places" and then opened six. It now asks /housing/count after every
change, and that number has to be the list's own, for every kind of filter.
"""
import re

import pytest

from app import db
from test_security import ORIGIN, world  # noqa: F401  (pytest fixture)


def places(client, query):
    """How many entries the Housing page lists for this query."""
    page = client.get("/housing?" + query).text.split('class="dock')[0]
    return len(set(re.findall(r'href="/listing/(\d+)', page)))


@pytest.fixture
def flats(world):  # noqa: F811
    users, clients = world
    spec = [
        # kind, price, area, free from, months, minutes, mates, bills, features
        ("shared_flat", 420, "lisboa", "2026-12-01", 4, 55, 4, 0, "wifi,desk"),
        ("studio", 690, "oeiras", "2027-01-01", 12, 28, 0, 1, "wifi,parking"),
        ("shared_flat", 480, "carcavelos", "2027-02-01", 5, 15, 2, 0, "desk,balcony"),
        ("whole_flat", 1540, "carcavelos", "2027-03-01", 12, 12, 0, 0, "parking"),
        ("shared_flat", 750, "parede", "2027-03-01", 6, 40, 3, 0, "balcony,pets"),
    ]
    for kind, price, area, free, months, minutes, mates, bills, feats in spec:
        listing = db.create_listing(owner_id=users[1], kind="housing", title=f"{kind} {price}",
                                    price=price)
        with db.connect() as conn:
            conn.execute(
                "UPDATE listings SET category=?, place=?, available_from=?, months_min=?,"
                " minutes_campus=?, flatmates=?, bills_included=?, features=? WHERE id=?",
                (kind, area, free, months, minutes, mates, bills, feats, listing))
        conn.close()
    return clients[0]


QUERIES = [
    "", "rent=450", "rent=750", "rent=1000", "rent=1000%2B", "rmin=450&rmax=700",
    "rent=450&rmax=700", "cat=shared_flat", "cat=studio", "area=carcavelos",
    "mins=30", "minsx=20", "stay=5", "stay=12", "mates=0", "mates=2", "mates=3",
    "movein=2027-01-15", "has=bills", "has=balcony", "has=balcony&has=pets",
    "cat=shared_flat&rent=750", "cat=shared_flat&rmax=600&mins=30&has=desk",
    "q=studio", "sort=low&rent=750", "rent=abc&area=mars",
]


@pytest.mark.parametrize("query", QUERIES)
def test_the_count_is_what_the_list_shows(flats, query):
    answer = flats.get("/housing/count?" + query)
    assert answer.status_code == 200
    assert answer.json()["count"] == places(flats, query)


def test_the_button_on_the_page_says_the_same_number(flats):
    page = flats.get("/housing?cat=shared_flat&rent=750").text
    button = page.split("data-live-count")[1].split("</button>")[0]
    assert "Show 3 places" in button


def test_one_place_is_singular(flats):
    assert flats.get("/housing/count?cat=studio").json()["label"] == "Show 1 place"


def test_signed_out_there_is_nothing_to_count(world):  # noqa: F811
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/housing/count").status_code == 401
