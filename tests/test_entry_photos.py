"""Changing the photos on an entry you already put up.

The row on the edit form is: the photos the entry has, then the ones you
have just picked, then Add at the end. Pressing an × takes a photo out of
the row there and then. All of that is drawn by the script, and what it
comes down to on the wire is this: one save may add several photos and drop
several others at the same time, and seven is still the ceiling across both.
"""
import io

import pytest
from PIL import Image

from app import db
from test_security import HOUSING, ORIGIN, world  # noqa: F401  (pytest fixture)


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf, "JPEG")
    return buf.getvalue()


def shots(names):
    return [("photos", (f"{n}.jpg", jpeg(), "image/jpeg")) for n in names]


@pytest.fixture
def entry(world):  # noqa: F811
    """An entry of alice's with three photos on it."""
    users, clients = world
    answer = clients[0].post("/new", headers=ORIGIN, follow_redirects=False,
                             data=dict(HOUSING, bills_included="1"),
                             files=shots(["a", "b", "c"]))
    assert answer.status_code == 303, answer.text
    listing = int(answer.headers["location"].split("/listing/")[1].split("?")[0])
    return clients[0], listing, [str(p["id"]) for p in db.photos_of(listing)]


def test_several_photos_go_on_in_one_save(entry):
    # The form field only ever holds the last pick, so the script collects
    # them and writes them all back. Here is what has to arrive.
    client, listing, ids = entry
    client.post("/new", headers=ORIGIN,
                data=dict(HOUSING, bills_included="1", edit_id=str(listing)),
                files=shots(["d", "e", "f"]))
    assert len(db.photos_of(listing)) == 6


def test_adding_and_removing_in_the_same_save(entry):
    client, listing, ids = entry
    client.post("/new", headers=ORIGIN,
                data=dict(HOUSING, bills_included="1", edit_id=str(listing),
                          remove_photo=[ids[0], ids[1]]),
                files=shots(["d", "e"]))
    left = [str(p["id"]) for p in db.photos_of(listing)]
    assert ids[2] in left
    assert ids[0] not in left and ids[1] not in left
    assert len(left) == 3


def test_the_ceiling_counts_what_goes_as_well_as_what_comes(entry):
    # Three on it, five more would be eight. Dropping two first makes room,
    # and the same save is then allowed.
    client, listing, ids = entry
    refused = client.post("/new", headers=ORIGIN,
                          data=dict(HOUSING, bills_included="1", edit_id=str(listing)),
                          files=shots(["d", "e", "f", "g", "h"]))
    assert "at most 7 photos" in refused.text
    assert len(db.photos_of(listing)) == 3

    client.post("/new", headers=ORIGIN,
                data=dict(HOUSING, bills_included="1", edit_id=str(listing),
                          remove_photo=[ids[0], ids[1]]),
                files=shots(["d", "e", "f", "g", "h"]))
    assert len(db.photos_of(listing)) == 6


def test_the_file_of_a_removed_photo_goes_too(entry):
    import os
    from app import main
    client, listing, ids = entry
    gone = next(p for p in db.photos_of(listing) if str(p["id"]) == ids[0])
    path = os.path.join(main.UPLOADS, gone["filename"])
    assert os.path.exists(path)
    client.post("/new", headers=ORIGIN,
                data=dict(HOUSING, bills_included="1", edit_id=str(listing),
                          remove_photo=[ids[0]]))
    assert not os.path.exists(path)


def test_the_edit_form_offers_the_x_for_every_photo_it_has(entry):
    client, listing, ids = entry
    page = client.get(f"/listing/{listing}/edit").text
    for one in ids:
        assert f'value="{one}"' in page
    assert page.count("Remove this photo") >= len(ids)
    # Add is the last tile in the row, so a new photo lands in front of it.
    assert page.index("pic-add") > page.rindex("pic--have")
