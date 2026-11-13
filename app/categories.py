"""What kind of thing a ticket is for.

One list, used by the form, by the chips above the list and by the check that
nobody can send in something we do not know.
"""

TICKET = [
    ("party",   "Party"),
    ("concert", "Concert"),
    ("sports",  "Sports"),
    ("culture", "Culture"),
    ("travel",  "Travel"),
    ("other",   "Other"),
]

TICKET_KEYS = [key for key, _ in TICKET]
TICKET_LABELS = dict(TICKET)

DEFAULT = "other"


def is_valid(key):
    return key in TICKET_LABELS


def label(key):
    return TICKET_LABELS.get(key, "")


def clean(key):
    """Take what the form sent and give back something we can store."""
    key = (key or "").strip().lower()
    return key if is_valid(key) else DEFAULT
