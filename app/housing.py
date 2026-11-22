"""Everything the Housing tab can be asked about.

Housing is the one tab where people arrive knowing what they want, so it is
also the one tab with a real filter panel. Every list in here is used three
times over, by the form that writes a place up, by the panel that searches
for one, and by the check that stops anything we do not know from being
stored. Change a list here and all three follow.
"""

# What kind of place it is. Private room is deliberately not in here. A
# private room is a room in a shared flat, so it would be the same thing
# twice. Whether your room is your own is a feature of the entry instead.
KINDS = [
    ("shared_flat", "Shared flat"),
    ("studio",      "Studio"),
    ("whole_flat",  "Whole flat"),
    ("other",       "Other"),
]
KIND_LABELS = dict(KINDS)

# Where it is. The campus is in Carcavelos, and the list runs roughly by how
# far out it gets from there.
AREAS = [
    ("carcavelos", "Carcavelos"),
    ("parede",     "Parede"),
    ("sao_pedro",  "São Pedro"),
    ("oeiras",     "Oeiras"),
    ("cascais",    "Cascais"),
    ("lisboa",     "Lisboa"),
    ("other",      "Other"),
]
AREA_LABELS = dict(AREAS)

# What the place comes with. Stored as a comma separated list of these keys
# in one column, because a tick box is not worth a table of its own in a
# project this size. The icon is the Tabler name the page draws.
FEATURES = [
    ("furnished",        "Furnished",        "sofa"),
    ("own_bathroom",     "Own bathroom",     "bath"),
    ("own_room",         "Own room",         "door"),
    ("desk",             "Desk",             "device-desktop"),
    ("wifi",             "Wifi included",    "wifi"),
    ("washing_machine",  "Washing machine",  "wash-machine"),
    ("dishwasher",       "Dishwasher",       "dishwasher"),
    ("balcony",          "Balcony",          "building-arch"),
    ("air_conditioning", "Air conditioning", "air-conditioning"),
    ("parking",          "Parking",          "car"),
    ("pets",             "Pets allowed",     "dog"),
    # Added later. Heating is the one nobody thinks to ask about until
    # January, and in a Lisbon flat it is often simply not there. The rest
    # are the things a student carries up the stairs or wishes they had.
    ("heating",          "Heating",          "flame"),
    ("oven",             "Oven",             "cooker"),
    ("dryer",            "Dryer",            "wind"),
    ("elevator",         "Elevator",         "elevator"),
    ("bike_storage",     "Bike storage",     "bike"),
    ("garden",           "Garden",           "plant"),
]
FEATURE_LABELS = {key: name for key, name, _ in FEATURES}
FEATURE_ICONS = {key: icon for key, _, icon in FEATURES}
FEATURE_KEYS = set(FEATURE_LABELS)

# Rent per month. Key, what the button says, floor, ceiling. The steps are
# high because a whole flat for four goes well past a thousand, and because
# a band nobody can reach is a band nobody presses.
# Five, so the row fits on one line of a phone. The step at 1250 went,
# because between a thousand and above there was nothing a student was
# choosing between.
RENT_BANDS = [
    ("",      "Any",      None, None),
    ("450",   "to 450",   None, 450),
    ("750",   "to 750",   None, 750),
    ("1000",  "to 1000",  None, 1000),
    ("1000+", "above",    1000, None),
]
RENT_LABELS = {key: name for key, name, _, _ in RENT_BANDS}
RENT_BY_KEY = {band[0]: band for band in RENT_BANDS}

# How long to the campus. It runs to a full hour because from Lisbon that is
# what it honestly takes.
# Ten minutes went, because the places that close are rare enough to find
# by eye. An hour and a half came in, because half of what gets offered is
# in Lisbon and from Lisbon to Carcavelos that is the honest number.
CAMPUS_BANDS = [
    ("",   "Any",       None),
    ("30", "30 min",    30),
    ("45", "45 min",    45),
    ("60", "1 hour",    60),
    ("90", "1.5 hours", 90),
]
CAMPUS_LABELS = {key: name for key, name, _ in CAMPUS_BANDS}
CAMPUS_BY_KEY = {band[0]: band for band in CAMPUS_BANDS}

# How long you want to stay. It filters on the minimum the place asks for,
# so wanting a semester hides everything that insists on a year. This is the
# one that catches people on exchange out.
STAY_BANDS = [
    ("",     "Any",        None),
    ("5",    "A semester", 5),
    ("12",   "A year",     12),
    ("24",   "Longer",     24),
]
STAY_LABELS = {key: name for key, name, _ in STAY_BANDS}
STAY_BY_KEY = {band[0]: band for band in STAY_BANDS}

# Who else lives there. Nobody counts flatmates one by one when they are
# looking, they decide between living alone, a small flat and a big one.
MATES_BANDS = [
    ("",  "Any",      None),
    ("0", "Alone",    0),
    ("2", "1 or 2",   2),
    ("3", "3 or more", None),
]
MATES_LABELS = {key: name for key, name, _ in MATES_BANDS}
MATES_BY_KEY = {band[0]: band for band in MATES_BANDS}

SORTS = [
    ("",     "Move in soonest"),
    ("low",  "Rent low to high"),
    ("high", "Rent high to low"),
]
SORT_KEYS = {key for key, _ in SORTS}
SORT_LABELS = dict(SORTS)


def clean_kind(key):
    key = (key or "").strip().lower()
    return key if key in KIND_LABELS else None


def clean_area(key):
    key = (key or "").strip().lower()
    return key if key in AREA_LABELS else None


def clean_features(values):
    """Take what the form ticked and give back a string we can store.

    The order is the order of the list above and not the order they arrived
    in, so two entries with the same ticks store the same string.
    """
    chosen = set()
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip().lower()
            if part in FEATURE_KEYS:
                chosen.add(part)
    return ",".join(key for key, _, _ in FEATURES if key in chosen)


def feature_list(stored):
    """The stored string back as a list of key and label and icon."""
    have = {p.strip() for p in (stored or "").split(",") if p.strip()}
    return [(key, name, icon) for key, name, icon in FEATURES if key in have]


def whole_number(text, limit):
    """A number somebody typed, or None. Anything silly is thrown away."""
    text = (text or "").strip()
    if not text.isdigit():
        return None
    value = int(text)
    return value if 0 < value <= limit else None
