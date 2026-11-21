"""Push notifications, on the phone's lock screen like any other app.

Web Push, the standard every browser speaks, so there is no app store and no
paid service in between. The browser hands us an address for one device, we
send to that address, and the phone shows it.

Who gets what:

    messages   a new message in one of your chats             on by default
    ticket     a new ticket, matching what you searched for   off until you ask
    housing    a new place, the same                          off until you ask
    item       a new thing in Market, the same                off until you ask

Each of the four can be turned off on its own at /profile/notifications.

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

from . import db

AREAS = [
    ("messages", "New messages",      "When somebody writes to you in a chat."),
    ("ticket",   "New tickets",       "When a ticket goes up that matches your search."),
    ("housing",  "New housing",       "When a place goes up that matches your search."),
    ("item",     "New in Market",     "When something goes up that matches your search."),
]
AREA_LABELS = {key: name for key, name, _ in AREAS}

WHAT = {"ticket": "New ticket", "housing": "New place", "item": "New in Market"}


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
        return status not in (404, 410)
    except Exception:
        return True
    return True


def send(user_id, title, body, url):
    """Send to every device of one student. Gives back how many it reached."""
    if not is_set_up():
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

def matches(listing, q, cat):
    """True when a new entry fits what somebody was searching for.

    Every word they searched for has to be in it somewhere, the same as the
    search box on the tab. An empty search means everything.
    """
    if cat and (listing["category"] or "") != cat:
        return False
    text = " ".join(str(listing[k] or "") for k in
                    ("title", "description", "place", "address", "info")).lower()
    return all(word in text for word in (q or "").lower().split())


def _money(value):
    if value is None:
        return ""
    return f"€{value:g}"


def new_message(conv, sender_id, body):
    """Tell the other person in a chat that there is something new."""
    receiver = conv["owner_id"] if sender_id == conv["starter_id"] else conv["starter_id"]
    if receiver == sender_id or not db.prefs_of(receiver)["messages"]["on"]:
        return 0
    sender = db.get_user(sender_id)
    name = sender["name"] if sender else "Somebody"
    return send(receiver, f"{name} · {conv['title']}", body, f"/chat/{conv['id']}")


def new_listing(listing):
    """Tell everyone watching this tab whose search the new entry fits."""
    kind = listing["type"]
    if kind not in WHAT:
        return 0
    bits = [_money(listing["price"])]
    if kind == "ticket":
        bits.append(listing["event_date"] or "")
    bits.append(listing["place"] or "")
    body = " · ".join(b for b in bits if b)
    reached = 0
    for watcher in db.watchers_of(kind):
        if watcher["user_id"] == listing["owner_id"]:
            continue
        if matches(listing, watcher["q"], watcher["cat"]):
            reached += send(watcher["user_id"], f"{WHAT[kind]}: {listing['title']}",
                            body, f"/listing/{listing['id']}")
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
