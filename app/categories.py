"""The fixed lists an entry can be put into.

Two different things live here. A category says what an entry is, and there is
one list per tab that has categories. A condition says how worn a thing for
sale is. Both are used in the same three places, the form that writes them,
the chips or pills that show them, and the check that stops anything we do not
know from being stored.
"""

TICKET = [
    ("party",   "Party"),
    ("concert", "Concert"),
    ("sports",  "Sports"),
    ("culture", "Culture"),
    ("travel",  "Travel"),
    ("other",   "Other"),
]

# What students actually sell each other, which is fairly predictable because
# every semester people arrive and leave again. Furniture takes the kitchen
# things and the lamps with it, Sports takes the surfboards and the bikes.
ITEM = [
    ("books",       "Books"),
    ("electronics", "Electronics"),
    ("furniture",   "Furniture"),
    ("sports",      "Sports"),
    ("clothes",     "Clothes"),
    ("other",       "Other"),
]

FOR_KIND = {"ticket": TICKET, "item": ITEM}

# The two lists share sports and other, and they mean the same word in both,
# so one flat lookup is enough to turn a stored key back into a label.
LABELS = dict(TICKET + ITEM)

DEFAULT = "other"

# How worn a thing for sale is. After the price this is the first thing anybody
# wants to know, so it is a field of its own and not part of the grey line.
CONDITION = [
    ("new",       "New"),
    ("like_new",  "Like new"),
    ("used",      "Used"),
    ("well_used", "Well used"),
]

CONDITION_LABELS = dict(CONDITION)


def of_kind(kind):
    """The categories of one tab, or an empty list for a tab without any."""
    return FOR_KIND.get(kind, [])


def is_valid(key, kind=None):
    """Is this a category we know?

    Give a kind as well and it has to be one of that tab's own, so a Market
    category can never arrive on a ticket.
    """
    if kind is None:
        return key in LABELS
    return key in dict(FOR_KIND.get(kind, []))


def label(key):
    return LABELS.get(key, "")


def clean(key, kind):
    """Take what the form sent and give back something we can store."""
    key = (key or "").strip().lower()
    return key if is_valid(key, kind) else DEFAULT


def condition_label(key):
    return CONDITION_LABELS.get(key, "")


def clean_condition(key):
    """Nothing chosen stays nothing, because a condition is not compulsory."""
    key = (key or "").strip().lower()
    return key if key in CONDITION_LABELS else None
