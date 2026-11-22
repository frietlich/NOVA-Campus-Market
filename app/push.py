"""Push notifications, on the phone's lock screen like any other app.

Web Push, the standard every browser speaks, so there is no app store and no
paid service in between. The browser hands us an address for one device, we
send to that address, and the phone shows it.

Who gets what:

    messages   a new message in one of your chats             on by default
    ticket     a new ticket for a saved search or a watched event
    housing    a new place for a saved search
    item       a new thing in Market for a saved search

A saved search is the bell on a tab: it keeps every filter that was set, and
a student can save as many as they like. A watched event is the bell on one
ticket. Each of the four areas can be switched off at /profile/notifications,
which silences it without throwing the searches away.

It needs a key pair of our own (VAPID), which proves to Apple and Google that
the notification comes from us. Make one with

    python -m app.push keys

and put the three lines it prints into .env. Without them the whole thing is
switched off and nothing on the page mentions it.

On an iPhone it only works once the site is added to the home screen and is
served over https. In Chrome, Edge and Firefox on a laptop it also works on
http://127.0.0.1 while building.
"""

import base64
import json
import os
import sys
from datetime import datetime

from . import db

AREAS = [
    ("messages", "New messages",      "When somebody writes to you."),
    ("ticket",   "Tickets",           "Saved searches and saved events."),
    ("housing",  "Housing",           "Saved searches."),
    ("item",     "Market",            "Saved searches."),
    # Groups are the one tab with no bell to save a search on, so the only
    # thing that rings here is a course somebody is watching.
    ("group",    "Groups",            "Saved courses."),
]
AREA_LABELS = {key: name for key, name, _ in AREAS}

WHAT = {"ticket": "New ticket", "housing": "New place", "item": "New in Market",
        "group": "New group"}


# --------------------------------------------------------------------- keys

def public_key():
    return os.environ.get("VAPID_PUBLIC_KEY", "").strip()


def _private_key():
    return os.environ.get("VAPID_PRIVATE_KEY", "").strip()


def _subject():
    """Who the push services can write to. Our own sender address."""
    subject = os.environ.get("VAPID_SUBJECT", "").strip()
    if not subject:
        sender = (os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER") or "").strip()
        subject = f"mailto:{sender}" if sender else ""
    return subject


def is_set_up():
    return bool(public_key() and _private_key() and _subject())


def make_keys():
    """A fresh key pair as the two strings browsers and .env expect."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    def b64(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return b64(public), b64(private)


# ------------------------------------------------------------------ sending

def _webpush(device, payload):
    """One notification to one device. False when the device is gone for good."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(
            subscription_info={"endpoint": device["endpoint"],
                               "keys": {"p256dh": device["p256dh"], "auth": device["auth"]}},
            data=json.dumps(payload),
            vapid_private_key=_private_key(),
            vapid_claims={"sub": _subject()},
            ttl=60 * 60 * 24,
            timeout=10,
        )
    except WebPushException as error:
        status = getattr(error.response, "status_code", None)
        # 404 and 410 mean the browser threw the subscription away, for
        # example because notifications were turned off in its settings.
        print(f"  push to user {device['user_id']} failed: {status} {error}", flush=True)
        return status not in (404, 410)
    except Exception as error:
        print(f"  push to user {device['user_id']} failed: {error}", flush=True)
        return True
    return True


def send(user_id, title, body, url, test=False):
    """Send to every device of one student. Gives back how many it reached.

    Nothing goes out while the student's main switch is off, except the test
    they asked for themselves.
    """
    if not is_set_up():
        return 0
    if not test and not db.prefs_of(user_id)["all"]["on"]:
        return 0
    payload = {"title": title[:80], "body": body[:160], "url": url}
    reached = 0
    for device in db.devices_of(user_id):
        if _webpush(device, payload):
            reached += 1
        else:
            db.drop_device(device["endpoint"])
    return reached


# ------------------------------------------------------------ who gets what

def _money(value):
    if value is None:
        return ""
    return f"€{value:g}"


def _line(listing):
    """The second line of a notification: what you want to know at a glance.

    A notification is two lines on a lock screen, so the second one has to
    be the three things that decide whether you open it. It used to be
    price, raw date and place for everything, which left a group with an
    empty line, because a group has neither a price nor a place, and gave
    housing the key the filter uses rather than the name of the town.
    """
    kind = listing["type"]
    if kind == "group":
        spots = listing["quantity"] or 1
        bits = [listing["course_name"] if "course_name" in listing.keys() else "",
                f"{spots} spot{'' if spots == 1 else 's'} left"]
    elif kind == "housing":
        from . import housing as places
        bits = [_money(listing["price"]),
                places.AREA_LABELS.get(listing["place"] or "", listing["place"] or "")]
    elif kind == "ticket":
        bits = [_money(listing["price"]), _day(listing["event_date"]), listing["place"] or ""]
    else:
        bits = [_money(listing["price"]), listing["place"] or ""]
    return " · ".join(b for b in bits if b)


def _day(iso_date):
    """21 Nov, the way a person says a date."""
    if not iso_date:
        return ""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%-d %b")
    except ValueError:
        return iso_date


def new_message(conv, sender_id, body):
    """Tell the other person in a chat that there is something new."""
    receiver = conv["owner_id"] if sender_id == conv["starter_id"] else conv["starter_id"]
    if receiver == sender_id or not db.prefs_of(receiver)["messages"]["on"]:
        return 0
    sender = db.get_user(sender_id)
    name = sender["name"] if sender else "Somebody"
    return send(receiver, f"{name} · {conv['title']}", body, f"/chat/{conv['id']}")


def new_listing(listing, event_key=None, search_finds=None):
    """Tell everyone who wants to hear about this new entry. Once each.

    First whoever watches this very thing. For a ticket that is the event,
    and event_key says which event it is. For a group it is the course, so
    somebody looking for a team in Investments hears about every group that
    goes up for it, whatever the owner called the entry. Then whoever saved
    a search on this tab that finds the entry; search_finds(kind, params,
    listing_id) runs that search the way the tab does. Nobody hears about
    their own entry, nobody twice, and nobody who switched the area off.
    """
    kind = listing["type"]
    if kind not in WHAT:
        return 0
    body = _line(listing)
    url = f"/listing/{listing['id']}"
    told = {listing["owner_id"]}
    reached = 0

    def wants(user_id):
        return user_id not in told and db.prefs_of(user_id)[kind]["on"]

    if kind == "ticket" and event_key and listing["event_date"]:
        for user_id in db.event_watchers(event_key(listing)):
            if wants(user_id):
                told.add(user_id)
                reached += send(user_id, f"Another ticket: {listing['title']}", body, url)
    if kind == "group" and listing["course_id"]:
        for user_id in db.course_watchers(listing["course_id"]):
            if wants(user_id):
                told.add(user_id)
                reached += send(user_id, f"Another spot: {listing['title']}", body, url)
    if search_finds:
        for watcher in db.search_watchers(kind):
            user_id = watcher["user_id"]
            if wants(user_id) and search_finds(kind, watcher["params"], listing["id"]):
                told.add(user_id)
                reached += send(user_id, f"{WHAT[kind]}: {listing['title']}", body, url)
    return reached


if __name__ == "__main__":
    if sys.argv[1:] == ["keys"]:
        public, private = make_keys()
        print("# Push notifications. Put these lines into .env, never into git.")
        print(f"VAPID_PUBLIC_KEY={public}")
        print(f"VAPID_PRIVATE_KEY={private}")
        print("VAPID_SUBJECT=mailto:the-address-the-app-sends-from@gmail.com")
    else:
        print("usage: python -m app.push keys")
