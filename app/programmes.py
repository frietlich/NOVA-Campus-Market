"""The programmes the school offers.

One list, used by the profile form, by the checks and by the display. If a new
programme is added, it is added here and nowhere else.
"""

BACHELOR = [
    "Bachelor in Economics",
    "Bachelor in Management",
    "Bachelor in Ocean Studies",
]

# Alphabetical, so the two International ones sit together at the top instead
# of in the middle of the list.
MASTER = [
    "International Master in Finance",
    "International Master in Management",
    "Master in Business Analytics",
    "Master in Economics",
    "Master in Finance",
    "Master in Impact Entrepreneurship and Innovation",
    "Master in International Development and Public Policy",
    "Master in Management",
]

# Not a programme of its own. An exchange student is here for a term and an
# alumnus has finished, so neither sits in a Nova programme right now.
OTHER = [
    "Exchange",
    "Alumni",
]

# CEMS is a double degree. You always do it on top of a master, never instead
# of one, so it is stored as a yes or no next to the real programme and never
# as the programme itself.
CEMS = "CEMS Master in Management"

ALL = BACHELOR + MASTER + OTHER

# What the form shows, in three groups.
GROUPS = [
    ("Bachelor", BACHELOR),
    ("Master", MASTER + [CEMS]),
    ("Other", OTHER),
]


def is_valid(name):
    return name in ALL


def short(name):
    """A tight version for the one line under a name on a card.

    Master in Business Analytics becomes Business Analytics.
    """
    if not name:
        return ""
    for prefix in ("International Master in ", "Master in ", "Bachelor in "):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def label(name, cems=False):
    """The full line for a profile. Master in Management · CEMS."""
    if not name:
        return ""
    return f"{name} · CEMS" if cems else name
