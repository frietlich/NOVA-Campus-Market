"""Category choices shared by posting forms and listing filters."""

TICKET = [
    ("party",   "Party"),
    ("concert", "Concert"),
    ("sports",  "Sports"),
    ("culture", "Culture"),
    ("travel",  "Travel"),
    ("other",   "Other"),
]

OPTIONS = {
    "ticket": TICKET,
    "housing": [("room", "Room"), ("studio", "Studio"), ("flat", "Entire flat"), ("other", "Other")],
    "item": [("furniture", "Furniture"), ("electronics", "Electronics"), ("books", "Books"),
             ("transport", "Transport"), ("clothing", "Clothing"), ("other", "Other")],
}

TICKET_KEYS = [key for key, _ in TICKET]
TICKET_LABELS = dict(TICKET)

DEFAULT = "other"


def is_valid(key, kind="ticket"):
    return key in dict(OPTIONS.get(kind, ()))


def label(key):
    return TICKET_LABELS.get(key, "")


def clean(key, kind="ticket"):
    """Take what the form sent and give back something we can store."""
    key = (key or "").strip().lower()
    return key if is_valid(key, kind) else DEFAULT
