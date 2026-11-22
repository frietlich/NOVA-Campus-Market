"""The only file that talks to the database.

Every other file calls a function from here. Nobody else writes SQL.
If you need something the app cannot do yet, add a function here first.
"""

import os
import re
import secrets
import hashlib
import hmac
import sqlite3
from datetime import datetime, timedelta, timezone

from . import categories

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("CAMPUS_DB", os.path.join(os.path.dirname(HERE), "campus.db"))
SCHEMA_PATH = os.path.join(HERE, "schema.sql")

TYPES = ("housing", "ticket", "item", "group")

# A Nova address is a five digit student number and the school domain. That
# is the only shape there is, so the check is the whole shape and not only
# the ending, and the field can say no before anything is sent.
EMAIL_DOMAIN = "@novasbe.pt"
EMAIL_DIGITS = 5
EMAIL_LENGTH = EMAIL_DIGITS + len(EMAIL_DOMAIN)
EMAIL_SHAPE = re.compile(r"[0-9]{%d}%s" % (EMAIL_DIGITS, re.escape(EMAIL_DOMAIN)))
EMAIL_HINT = "0" * EMAIL_DIGITS + EMAIL_DOMAIN


def _either_case(text):
    """A word written so an input pattern matches it whichever case it is in.

    An input element has no way of being told to ignore case, so each letter
    becomes the pair of itself, and novasbe comes out as [Nn][Oo][Vv] and so
    on. Built from the domain above so there is still only one of it.
    """
    return "".join("[%s%s]" % (c.upper(), c.lower()) if c.isalpha()
                   else re.escape(c) for c in text)


# The same shape, written the way the form field wants it.
EMAIL_PATTERN = r"[0-9]{%d}%s" % (EMAIL_DIGITS, _either_case(EMAIL_DOMAIN))

# How long a name in the app may be. Long enough for a full Portuguese name,
# because both parents' names run along in one and thirty characters cut a
# good many students off in the middle of their own. Nothing is lost by
# being generous here, since every place a name is shown truncates it.
NAME_MAX = 40

# A code is good for this long, and for this many wrong guesses. After that a
# new one has to be sent. Without the limit a script could simply try all one
# million codes and take over any account.
CODE_MINUTES = 10
CODE_TRIES = 5

# Columns added after the first version. setup() puts them into an older
# campus.db, so nobody has to wipe their database to get them.
LATER_COLUMNS = {
    "users": [
        ("code_sent", "TEXT"),
        ("code_purpose", "TEXT"),
        ("code_tries", "INTEGER NOT NULL DEFAULT 0"),
        # light, dark, or empty for whatever the phone is set to
        ("theme", "TEXT NOT NULL DEFAULT ''"),
    ],
    "listings": [
        ("condition", "TEXT"),
        ("hand_in", "TEXT"),
        ("group_size", "INTEGER"),
        ("available_from", "TEXT"),
        ("months_min", "INTEGER"),
        ("bills_included", "INTEGER"),
        ("bills_estimate", "REAL"),
        ("minutes_campus", "INTEGER"),
        ("flatmates", "INTEGER"),
        ("features", "TEXT"),
        # The deposit as the amount it really is. It used to be a number of
        # months that the page multiplied by the rent, which meant nobody
        # could say the one thing landlords actually say, a flat sum.
        ("deposit", "REAL"),
        ("external_url", "TEXT"),
    ],
    "conversations": [
        ("archived_owner", "TEXT"),
        ("archived_starter", "TEXT"),
    ],
    "messages": [
        ("kind", "TEXT NOT NULL DEFAULT 'text'"),
    ],
}


# ---------------------------------------------------------------- connection

def connect():
    """Open the database. Rows come back so you can say row["title"]."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup():
    """Create the tables if they are not there yet. Safe to call every start."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    conn = connect()
    conn.executescript(schema)
    conn.execute("""CREATE TABLE IF NOT EXISTS security_limits (
        key TEXT PRIMARY KEY, start INTEGER NOT NULL, count INTEGER NOT NULL
    )""")
    for table, columns in LATER_COLUMNS.items():
        have = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

    from .course_catalogue import import_courses
    import_courses(conn)
    conn.commit()
    conn.close()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# The hour the day turns over for everything that runs out on a date.
DAY_TURNS = 6


def active_day():
    """The date the app counts as today, with the day turning over at six.

    Midnight is the wrong moment to end a day in an app about going out. A
    party on the 23rd is still worth opening at two in the morning, when
    somebody outside is looking for a spare ticket and whoever put it up is
    asleep and could not close it by hand anyway. The same holds for a
    group whose last day to join is today: nobody hands anything in at one
    in the morning, but they might still be looking for a fourth.

    So between midnight and six this still says yesterday, and an entry for
    the 23rd closes on the 24th at six, not sixty seconds after midnight.
    Every date that runs out goes through here, the sweep that closes them,
    the lists that hide them, the button that puts one back up and the date
    box that will not take a day gone by, so none of them can disagree with
    another by a few hours.
    """
    when = datetime.now().astimezone()
    if when.hour < DAY_TURNS:
        when -= timedelta(days=1)
    return when.date().isoformat()


# --------------------------------------------------------------------- users

def is_nova_email(email):
    """True only for a Nova address. This is the whole door policy."""
    return isinstance(email, str) and bool(EMAIL_SHAPE.fullmatch(email.strip().lower()))


def get_user(user_id):
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def get_user_by_email(email):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()
    conn.close()
    return row


def all_users():
    conn = connect()
    rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    conn.close()
    return rows


def create_user(email, name, programme="", password=None, cems=False):
    """password is already hashed by passwords.py. Nothing else goes in here."""
    conn = connect()
    cur = conn.execute(
        "INSERT INTO users (email, name, programme, cems, password, verified,"
        " created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
        (email.strip().lower(), name, programme, 1 if cems else 0, password, now()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_profile(user_id, name, programme, cems=False, photo=None):
    """Save what the edit page sends. photo of None leaves the picture alone.

    Changing programme also lets go of the courses that belonged to the old
    one. A course is a course of a programme, so carrying them over would
    leave somebody enrolled in things their new programme does not teach,
    and the Groups tab would quietly filter by them.
    """
    conn = connect()
    before = conn.execute("SELECT programme FROM users WHERE id = ?",
                          (user_id,)).fetchone()
    moved = before is not None and before["programme"] != programme
    if photo is None:
        conn.execute(
            "UPDATE users SET name = ?, programme = ?, cems = ? WHERE id = ?",
            (name.strip(), programme, 1 if cems else 0, user_id),
        )
    else:
        conn.execute(
            "UPDATE users SET name = ?, programme = ?, cems = ?, photo = ?"
            " WHERE id = ?",
            (name.strip(), programme, 1 if cems else 0, photo, user_id),
        )
    if moved:
        conn.execute(
            "DELETE FROM enrolments WHERE user_id = ? AND course_id NOT IN"
            " (SELECT course_id FROM course_offerings WHERE programme = ?)",
            (user_id, programme),
        )
    conn.commit()
    conn.close()


def set_theme(user_id, theme):
    """Light, dark, or empty to follow the phone. Anything else is ignored."""
    if theme not in ("", "light", "dark"):
        return False
    conn = connect()
    conn.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user_id))
    conn.commit()
    conn.close()
    return True


def set_password(user_id, hashed):
    """Store a new password. It arrives hashed, never as what was typed."""
    conn = connect()
    conn.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, user_id))
    conn.commit()
    conn.close()


def code_digest(user_id, code, purpose):
    secret = os.environ.get("CAMPUS_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("Configure CAMPUS_SECRET before generating codes.")
    return hmac.new(secret.encode(), f"{user_id}:{purpose}:{code}".encode(),
                    hashlib.sha256).hexdigest()


def new_code(user_id, purpose="join"):
    if purpose not in ("join", "login", "reset"):
        raise ValueError("Unknown verification purpose.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not user or not is_nova_email(user["email"]):
                raise ValueError("A valid Nova account is required.")
            if user["code_sent"]:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(user["code_sent"])).total_seconds()
                if age < 60:
                    raise ValueError("Wait one minute before requesting a new code.")
            conn.execute(
                "UPDATE users SET code=?,code_sent=?,code_tries=0,code_purpose=? WHERE id=?",
                (code_digest(user_id, code, purpose), now(), purpose, user_id))
        return code
    finally:
        conn.close()


def code_age(user_id):
    user = get_user(user_id)
    if user is None or not user["code_sent"]:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(user["code_sent"])).total_seconds()


def cancel_code(user_id, code, purpose):
    conn = connect()
    with conn:
        conn.execute("UPDATE users SET code=NULL WHERE id=? AND code=?",
                     (user_id, code_digest(user_id, code, purpose)))
    conn.close()


def check_code(user_id, code, purpose="join"):
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not user or not user["code"] or user["code_purpose"] != purpose:
                return "none"
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(user["code_sent"])).total_seconds()
            if age >= CODE_MINUTES * 60:
                return "expired"
            if user["code_tries"] >= CODE_TRIES:
                return "locked"
            if not hmac.compare_digest(code_digest(user_id, str(code).strip(), purpose), user["code"]):
                conn.execute("UPDATE users SET code_tries=code_tries+1 WHERE id=?", (user_id,))
                return "locked" if user["code_tries"] + 1 >= CODE_TRIES else "wrong"
            conn.execute(
                "UPDATE users SET verified=1,code=NULL,code_purpose=NULL,code_tries=0 WHERE id=?",
                (user_id,))
            return "ok"
    finally:
        conn.close()


# ------------------------------------------------------------------ listings

def _listing_sql(where, order="l.created_at DESC", extra_join=""):
    return (
        "SELECT l.*, u.name AS owner_name, u.programme AS owner_programme,"
        "       u.cems AS owner_cems, u.photo AS owner_photo,"
        "       c.name AS course_name, COALESCE(c.official_code,c.code) AS course_code,"
        "       (SELECT filename FROM photos p WHERE p.listing_id = l.id"
        "        ORDER BY p.position, p.id LIMIT 1) AS photo"
        "  FROM listings l JOIN users u ON u.id = l.owner_id"
        "  LEFT JOIN courses c ON c.id = l.course_id"
        f" {extra_join}"
        f" WHERE {where} ORDER BY {order}"
    )


ORDER_FOR = {
    "ticket": "l.event_date, l.event_time, l.price, l.id",
    # Groups is read course by course, so the course comes first and the
    # nearest hand in date leads inside it.
    "group": "c.name, l.hand_in IS NULL, l.hand_in, l.id",
    # Housing is read by when you could move in.
    "housing": "l.available_from IS NULL, l.available_from, l.id",
}

# What the Sort button on Housing can be set to. Empty is the order above.
HOUSING_SORTS = {
    "low":  "l.price ASC, l.available_from, l.id",
    "high": "l.price DESC, l.available_from, l.id",
}

# What the Sort button on Market can be set to. SQLite puts an empty price
# first when it sorts upwards, which is exactly right, because no price means
# free and free is the lowest price there is.
SORTS = {
    "new":  "l.created_at DESC",
    "low":  "l.price ASC, l.created_at DESC",
    "high": "l.price DESC, l.created_at DESC",
}


MONTHS = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05",
          "jun": "06", "jul": "07", "aug": "08", "sep": "09", "oct": "10",
          "nov": "11", "dec": "12"}


def date_hint(search):
    """A piece of an ISO date built from what somebody typed, or None.

    Dates are kept as 2026-12-05 and nobody types that. They type Dec, or
    5 Dec, or 05.12, so this turns those into -12- and -12-05, which a plain
    text search can then look for in a date column. Anything it cannot read
    gives back None and the search carries on without it.
    """
    text = (search or "").strip().lower()
    if not text:
        return None
    # Already written the way it is stored, so hand it straight on.
    if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?|\d{2}-\d{2}", text):
        return text
    month = day = None
    for piece in re.split(r"[^a-z0-9]+", text):
        if not piece:
            continue
        if piece[:3] in MONTHS:
            month = MONTHS[piece[:3]]
        elif piece.isdigit() and len(piece) <= 2:
            number = int(piece)
            if 1 <= number <= 31:
                day = f"{number:02d}"
            if month is None and 1 <= number <= 12 and day != f"{number:02d}":
                month = f"{number:02d}"
        elif piece.isdigit() and len(piece) == 4:
            return None  # a year on its own is no help, the data is one year
    # 05.12 and 5/12 are day then month here, the way they are written around
    # the school, so the second number wins as the month.
    parts = [p for p in re.split(r"[^0-9]+", text) if p.isdigit() and len(p) <= 2]
    if month is None and len(parts) == 2:
        day, month = f"{int(parts[0]):02d}", f"{int(parts[1]):02d}"
    if month is None:
        return None
    return f"-{month}-{day}" if day else f"-{month}-"


def search_clause(search):
    """What somebody typed in the search box, as SQL and its arguments.

    Every word has to turn up somewhere, each in a column of its own if it
    likes. Searching the whole box as one piece of text meant air ipad found
    nothing at all, because no single column holds those two words in that
    order.

    The venue is one of them, because it is printed on every ticket card
    and a word you can read on the screen has to be a word you can look
    for. Part of it is enough, the same as everywhere else, so Coliseu
    finds the Coliseu dos Recreios.

    The grey line is not among the columns. It is gone from the form and
    from the card, and searching something nobody can read any more only
    turns up entries for a reason you cannot see.

    Two of the columns do not hold the word that is on the screen. A card
    says Electronics and Like new, the database says books and like_new, so
    the labels are read here and turned into the keys to look for. Without
    that, searching for a word printed on the card finds nothing, which is
    the most confusing kind of nothing there is.

    A date is matched against the whole box instead, never word by word,
    because 5 Dec is one fact written as two words and the 5 on its own
    means nothing. An entry answers if every word was found, or if what was
    typed reads as a date and the entry falls on it.
    """
    words = [w for w in (search or "").strip().lower().split() if w]
    if not words:
        return "", []

    groups, args = [], []
    for word in words:
        parts = ["l.title LIKE ?", "l.description LIKE ?", "l.place LIKE ?",
                 "c.name LIKE ?", "c.code LIKE ?"]
        args += [f"%{word}%"] * 5
        for column, labels in (("l.category", categories.LABELS),
                               ("l.condition", categories.CONDITION_LABELS)):
            keys = [key for key, name in labels.items() if word in name.lower()]
            if keys:
                parts.append(f"{column} IN ({','.join('?' * len(keys))})")
                args += keys
        groups.append("(" + " OR ".join(parts) + ")")

    clause = " AND ".join(groups)
    hint = date_hint(search)
    if hint:
        clause = f"({clause}) OR l.hand_in LIKE ? OR l.event_date LIKE ?"
        args += [f"%{hint}%"] * 2
    return f"({clause})", args


def listings_of_type(kind, search="", only_for=None, category=None, sort=None,
                     min_price=None, max_price=None, free_only=False,
                     condition=None, free_from=None, area=None,
                     max_minutes=None, max_months=None, bills_included=False,
                     features=None, price_inclusive=False,
                     max_mates=None, min_mates=None):
    """Open listings in one tab.

    Search looks in the title, the grey line and the course name. Give
    only_for a user id and you get back just the entries whose course that
    student is taking. That is what keeps the Groups tab short.

    The price arguments are a band, not two boxes a student typed into. An
    entry with no price is free, so it counts as being under every ceiling.
    """
    where = "l.type = ? AND l.status = 'open'"
    args = [kind]

    # An event that has been and gone takes itself out of the tab the day
    # after. Nothing is deleted and nothing is closed, the entry is simply
    # not among the ones on offer any more, the same way a ticket for
    # yesterday already drops out of a student's saved list. The day of the
    # event itself still counts, because people sell up to the door.
    if kind == "ticket":
        where += " AND (l.event_date IS NULL OR l.event_date >= ?)"
        args.append(active_day())

    if category:
        where += " AND l.category = ?"
        args.append(category)

    if condition:
        where += " AND l.condition = ?"
        args.append(condition)

    # ------------------------------------------------------------- housing
    # A place that has been free since January is still free in February, so
    # the date means free by then and not free exactly then.
    if free_from:
        where += " AND (l.available_from IS NULL OR l.available_from <= ?)"
        args.append(free_from)

    if area:
        where += " AND l.place = ?"
        args.append(area)

    # No number means we cannot promise it is near, so it stays out.
    if max_minutes is not None:
        where += " AND l.minutes_campus IS NOT NULL AND l.minutes_campus <= ?"
        args.append(max_minutes)

    # Wanting a semester has to hide everything that insists on a year.
    if max_months is not None:
        where += " AND (l.months_min IS NULL OR l.months_min <= ?)"
        args.append(max_months)

    if bills_included:
        where += " AND l.bills_included = 1"

    # features is one column holding a comma separated list, so each tick is
    # a search for that key with a comma on either side of it. An entry with
    # no features at all gives NULL here, which matches nothing, and that is
    # exactly right.
    for key in features or []:
        where += " AND (',' || l.features || ',') LIKE ?"
        args.append(f"%,{key},%")

    # Who else lives there. A place that never said is left out of both,
    # because neither answer would be true of it.
    if max_mates is not None:
        where += " AND l.flatmates IS NOT NULL AND l.flatmates <= ?"
        args.append(max_mates)

    if min_mates is not None:
        where += " AND l.flatmates IS NOT NULL AND l.flatmates >= ?"
        args.append(min_mates)

    if free_only:
        where += " AND (l.price IS NULL OR l.price = 0)"

    if max_price is not None:
        # Market says under 450 and means it, Housing says to 450 and counts
        # a place at exactly 450 as a hit. Same column, two readings.
        where += (" AND (l.price IS NULL OR l.price <= ?)" if price_inclusive
                  else " AND (l.price IS NULL OR l.price < ?)")
        args.append(max_price)

    if min_price is not None:
        where += " AND l.price IS NOT NULL AND l.price >= ?"
        args.append(min_price)

    if only_for is not None:
        where += (" AND l.course_id IN (SELECT course_id FROM enrolments"
                  " WHERE user_id = ?)")
        args.append(only_for)

    clause, found = search_clause(search)
    if clause:
        where += " AND " + clause
        args += found

    conn = connect()
    if kind == "housing":
        order = HOUSING_SORTS.get(sort) or ORDER_FOR["housing"]
    else:
        order = SORTS.get(sort) or ORDER_FOR.get(kind) or "l.created_at DESC"
    rows = conn.execute(_listing_sql(where, order), tuple(args)).fetchall()
    conn.close()
    return rows


def get_listing(listing_id):
    conn = connect()
    row = conn.execute(_listing_sql("l.id = ?"), (listing_id,)).fetchone()
    conn.close()
    return row


def listings_of_user(user_id):
    conn = connect()
    rows = conn.execute(
        _listing_sql("l.owner_id = ?",
                     order="CASE WHEN l.status = 'open' THEN 0 ELSE 1 END,"
                           " l.created_at DESC"),
        (user_id,)
    ).fetchall()
    conn.close()
    return rows


def create_listing(owner_id, kind, title, description="", price=None, info="",
                   category=None, condition=None, event_date=None,
                   event_time=None, place=None, address=None, quantity=None,
                   course_id=None, hand_in=None, group_size=None,
                   available_from=None, months_min=None, bills_included=None,
                   bills_estimate=None, deposit=None,
                   minutes_campus=None, flatmates=None, features=None,
                   external_url=None):
    if kind not in TYPES:
        raise ValueError(f"unknown type {kind}")
    conn = connect()
    cur = conn.execute(
        "INSERT INTO listings (owner_id, type, title, description, price, info,"
        " category, condition, event_date, event_time, place, address, quantity,"
        " course_id, hand_in, group_size, available_from, months_min,"
        " bills_included, bills_estimate, deposit, minutes_campus,"
        " flatmates, features, external_url, status, views, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
        " ?, ?, ?, ?, ?, 'open', 0, ?)",
        (owner_id, kind, title, description, price, info, category, condition,
         event_date, event_time, place, address, quantity, course_id, hand_in,
         group_size, available_from, months_min, bills_included, bills_estimate,
         deposit, minutes_campus, flatmates, features, external_url,
         now()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


# What a form may change about an entry. Who owns it, which tab it is in,
# how often it was looked at and when it went up are not in here, so no
# request can touch them however it is put together.
EDITABLE = ("title", "description", "price", "info", "category", "condition",
            "event_date", "event_time", "place", "address", "quantity",
            "course_id", "hand_in", "group_size", "available_from",
            "months_min", "bills_included", "bills_estimate",
            "deposit", "minutes_campus", "flatmates", "features",
            "external_url")


def update_listing(listing_id, owner_id, **fields):
    """Change an entry. Only the owner, and only the columns named above.

    Every column the form knows is written, including the ones left empty,
    so clearing a field really clears it instead of quietly keeping what was
    there before.
    """
    names = [n for n in EDITABLE if n in fields]
    if not names:
        return False
    sets = ", ".join(f"{n} = ?" for n in names)
    args = [fields[n] for n in names] + [listing_id, owner_id]
    conn = connect()
    cur = conn.execute(
        f"UPDATE listings SET {sets} WHERE id = ? AND owner_id = ?", args)
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


CLOSED_LINE = "This entry was closed"


def close_listing(listing_id, owner_id):
    """Only the owner can close. Returns True if something actually changed.

    Closing also says so in every chat about the entry, because the other
    student is still waiting for an answer and nothing else would ever tell
    them. The notice is a message from the owner, so it lifts the chat up
    everybody else's list and counts as unread for them and not for the
    owner, which is exactly who already knows.
    """
    conn = connect()
    cur = conn.execute(
        "UPDATE listings SET status = 'closed' WHERE id = ? AND owner_id = ?",
        (listing_id, owner_id),
    )
    changed = cur.rowcount > 0
    if changed:
        conn.execute(
            "INSERT INTO messages (conversation_id, sender_id, body,"
            "                      created_at, kind)"
            " SELECT c.id, ?, ?, ?, 'closed' FROM conversations c"
            "  WHERE c.listing_id = ?",
            (owner_id, CLOSED_LINE, now(), listing_id),
        )
        conn.execute(
            "UPDATE conversations SET archived_owner = NULL,"
            "                         archived_starter = NULL"
            " WHERE listing_id = ?",
            (listing_id,),
        )
    conn.commit()
    conn.close()
    return changed


# The day the sweep below last ran. A module level name, so a restart only
# ever means one sweep too many, never one too few.
_swept_on = None


def close_past_dates(force=False):
    """Close every entry whose day has been, the morning after it.

    A ticket goes by the day of the event, a group by the last day somebody
    could still join. Both are a date after which the entry cannot do what
    it was put up for.

    An entry nobody ever closes keeps its chats sitting in other people's
    inboxes for good, and those chats cannot be put away while the entry is
    open. The owner may have stopped using the app the day the party ended.
    So the calendar closes it instead, and everybody who wrote gets the
    same notice they would have got from the owner by hand.

    It goes through close_listing one entry at a time on purpose. Closing
    is more than a column, it writes the notice into every chat, and doing
    that twice in two places is how the two slowly stop agreeing.

    It runs once a day. The first page anybody opens after midnight pays
    for one query over an indexed column, and usually finds nothing.
    """
    global _swept_on
    today = active_day()
    if _swept_on == today and not force:
        return 0
    _swept_on = today
    conn = connect()
    over = conn.execute(
        "SELECT id, owner_id FROM listings"
        " WHERE status = 'open' AND ("
        "      (type = 'ticket' AND event_date IS NOT NULL AND event_date < ?)"
        "   OR (type = 'group'  AND hand_in    IS NOT NULL AND hand_in    < ?))",
        (today, today),
    ).fetchall()
    conn.close()
    for row in over:
        close_listing(row["id"], row["owner_id"])
    return len(over)


def reopen_listing(listing_id, owner_id):
    """Put an entry back up, and take the notice out of every chat again.

    Mostly this undoes a mistake. Leaving the line in would have the app
    telling nine people something that is no longer true, and a thread is
    not a record of what the owner pressed, it is the conversation.
    """
    conn = connect()
    cur = conn.execute(
        "UPDATE listings SET status = 'open' WHERE id = ? AND owner_id = ?"
        # A party that has been and a group nobody can join any more cannot
        # go back up as they are. Either would close itself again in the
        # morning, so the button says what does help instead, change the
        # date.
        "   AND (type <> 'ticket' OR event_date IS NULL OR event_date >= ?)"
        "   AND (type <> 'group'  OR hand_in    IS NULL OR hand_in    >= ?)",
        (listing_id, owner_id, active_day(), active_day()),
    )
    changed = cur.rowcount > 0
    if changed:
        conn.execute(
            "DELETE FROM messages WHERE kind = 'closed' AND conversation_id IN"
            " (SELECT id FROM conversations WHERE listing_id = ?)",
            (listing_id,),
        )
    conn.commit()
    conn.close()
    return changed


def count_view(listing_id, user_id):
    """Count that this student looked at this entry, once and once only.

    The row in views is what holds the promise. A second look by the same
    person is ignored by the primary key, so the total can be raised by one
    more student and never by one more reload.
    """
    conn = connect()
    cur = conn.execute(
        "INSERT OR IGNORE INTO views (user_id, listing_id, created_at)"
        " VALUES (?, ?, ?)",
        (user_id, listing_id, now()),
    )
    if cur.rowcount:
        conn.execute("UPDATE listings SET views = views + 1 WHERE id = ?",
                     (listing_id,))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------- saves

def toggle_save(user_id, listing_id):
    """Put a heart on an entry, or take it off again.

    One call does both, because the button is one button. It gives back
    whether the heart is on now, which is what the page has to show.
    """
    conn = connect()
    there = conn.execute("SELECT 1 FROM listings WHERE id = ?",
                         (listing_id,)).fetchone()
    if there is None:
        conn.close()
        return False

    cur = conn.execute("DELETE FROM saves WHERE user_id = ? AND listing_id = ?",
                       (user_id, listing_id))
    saved = cur.rowcount == 0
    if saved:
        conn.execute("INSERT INTO saves (user_id, listing_id, created_at)"
                     " VALUES (?, ?, ?)", (user_id, listing_id, now()))
    conn.commit()
    conn.close()
    return saved


def is_saved(user_id, listing_id):
    conn = connect()
    row = conn.execute("SELECT 1 FROM saves WHERE user_id = ? AND listing_id = ?",
                       (user_id, listing_id)).fetchone()
    conn.close()
    return row is not None


def save_count(listing_id):
    """How many students saved it. The number only, never who."""
    conn = connect()
    n = conn.execute("SELECT COUNT(*) FROM saves WHERE listing_id = ?",
                     (listing_id,)).fetchone()[0]
    conn.close()
    return n


def saved_listings(user_id):
    """Everything this student put a heart on, newest heart first.

    A saved ticket for a day that is over drops out on its own. Nobody wants
    to be reminded of a party that already happened.
    """
    today = active_day()
    conn = connect()
    rows = conn.execute(
        _listing_sql("s.user_id = ? AND (l.type != 'ticket' OR l.event_date >= ?)",
                     # Closed ones sink to the foot of the list. They stay,
                     # because that an entry is gone is the thing you came
                     # back to find out, but the live ones lead.
                     order="CASE WHEN l.status = 'open' THEN 0 ELSE 1 END,"
                           " s.created_at DESC",
                     extra_join="JOIN saves s ON s.listing_id = l.id"),
        (user_id, today),
    ).fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------------- courses

def all_courses():
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM courses ORDER BY programme, name"
    ).fetchall()
    conn.close()
    return rows


def courses_for_programme(programme):
    """Only official courses offered to this programme, with classification."""
    conn = connect()
    rows = conn.execute(
        "SELECT c.id, c.name, COALESCE(c.official_code,c.code) AS code, "
        "o.type AS course_type, o.programme FROM courses c "
        "JOIN course_offerings o ON o.course_id=c.id WHERE o.programme=? "
        "ORDER BY CASE o.type WHEN 'MANDATORY' THEN 0 "
        "WHEN 'EXCLUSIVE_ELECTIVE' THEN 1 WHEN 'ELECTIVE' THEN 2 ELSE 3 END, c.name",
        (programme,),
    ).fetchall()
    conn.close()
    return rows


def all_catalogue_options():
    """One item per course, with per-programme types for the join-page filter."""
    conn = connect()
    rows = conn.execute(
        'SELECT c.id,c.name,COALESCE(c.official_code,c.code) AS code, '
        'o.programme,o.type FROM courses c '
        'JOIN course_offerings o ON o.course_id=c.id ORDER BY c.name'
    ).fetchall()
    conn.close()
    courses = {}
    for r in rows:
        courses.setdefault(r['id'], {'id':r['id'], 'name':r['name'],
                                      'code':r['code'], 'programmes':{}})
        courses[r['id']]['programmes'][r['programme']] = r['type']
    return list(courses.values())


def valid_course_ids(programme):
    return {c['id'] for c in courses_for_programme(programme)}


def get_course(course_id):
    conn = connect()
    row = conn.execute("SELECT id, COALESCE(official_code,code) AS code, name, programme FROM courses WHERE id = ?", (course_id,)).fetchone()
    conn.close()
    return row


def courses_of(user_id):
    """The courses one student is taking."""
    conn = connect()
    rows = conn.execute(
        "SELECT c.id, COALESCE(c.official_code,c.code) AS code, c.name, c.programme FROM courses c"
        "  JOIN enrolments e ON e.course_id = c.id"
        " WHERE e.user_id = ? ORDER BY c.name",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def set_enrolments(user_id, course_ids):
    """Replace the whole list in one go. The picker page sends all of it."""
    conn = connect()
    conn.execute("DELETE FROM enrolments WHERE user_id = ?", (user_id,))
    for course_id in set(int(c) for c in course_ids):
        conn.execute(
            "INSERT OR IGNORE INTO enrolments (user_id, course_id) VALUES (?, ?)",
            (user_id, course_id),
        )
    conn.commit()
    conn.close()


def enrol(user_id, course_id):
    conn = connect()
    conn.execute(
        "INSERT OR IGNORE INTO enrolments (user_id, course_id) VALUES (?, ?)",
        (user_id, course_id),
    )
    conn.commit()
    conn.close()


# -------------------------------------------------------------------- photos

def add_photo(listing_id, filename, position=0):
    conn = connect()
    conn.execute(
        "INSERT INTO photos (listing_id, filename, position) VALUES (?, ?, ?)",
        (listing_id, filename, position),
    )
    conn.commit()
    conn.close()


def photos_of(listing_id):
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM photos WHERE listing_id = ? ORDER BY position, id",
        (listing_id,),
    ).fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------- conversations

def interest_in(listing_id):
    """Everyone who has written about this listing, first one first.

    Opening a chat without sending anything does not count: you are in the
    queue from your first message on. The order is the time of that first
    message, so it never changes afterwards. Only the owner sees the names,
    everyone else only learns how many came before them.
    """
    conn = connect()
    rows = conn.execute(
        "SELECT c.id AS conversation_id, c.starter_id, u.name, u.photo,"
        "       MIN(m.created_at) AS first_at"
        "  FROM conversations c"
        "  JOIN messages m ON m.conversation_id = c.id AND m.sender_id = c.starter_id"
        "  JOIN users u ON u.id = c.starter_id"
        " WHERE c.listing_id = ?"
        " GROUP BY c.id"
        " ORDER BY first_at, c.id",
        (listing_id,),
    ).fetchall()
    conn.close()
    return rows


def place_in_queue(queue, user_id):
    """1 for the first student who wrote, 2 for the second, None if not in it."""
    for n, row in enumerate(queue, start=1):
        if row["starter_id"] == user_id:
            return n
    return None


def open_conversation(listing_id, starter_id):
    """Find the conversation between this student and this listing, or start one.

    Several students can write about the same listing. Each pair gets its own
    conversation and nobody sees anyone else's.
    """
    conn = connect()
    row = conn.execute(
        "SELECT * FROM conversations WHERE listing_id = ? AND starter_id = ?",
        (listing_id, starter_id),
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO conversations (listing_id, starter_id, created_at)"
            " VALUES (?, ?, ?)",
            (listing_id, starter_id, now()),
        )
        conn.commit()
        conv_id = cur.lastrowid
    else:
        conv_id = row["id"]
    conn.close()
    return conv_id


def get_conversation(conv_id):
    conn = connect()
    row = conn.execute(
        "SELECT c.*, l.title, l.price, l.type, l.owner_id, l.status"
        "  FROM conversations c JOIN listings l ON l.id = c.listing_id"
        " WHERE c.id = ?",
        (conv_id,),
    ).fetchone()
    conn.close()
    return row


def can_see_conversation(conv, user_id):
    """Only the two people in it. This is what keeps chats private."""
    return conv is not None and user_id in (conv["starter_id"], conv["owner_id"])


def archive_chat(conv_id, user_id, on=True):
    """Put one chat away, or bring it back. Your own side of it only.

    The other person's list is none of your business, so each side has its
    own stamp and this only ever writes the one that belongs to you.
    """
    conn = connect()
    row = conn.execute(
        "SELECT c.starter_id, l.owner_id FROM conversations c"
        "  JOIN listings l ON l.id = c.listing_id WHERE c.id = ?",
        (conv_id,),
    ).fetchone()
    if row is None or user_id not in (row["starter_id"], row["owner_id"]):
        conn.close()
        return False
    side = "archived_owner" if user_id == row["owner_id"] else "archived_starter"
    conn.execute(
        "UPDATE conversations SET %s = ? WHERE id = ?" % side,
        (now() if on else None, conv_id),
    )
    conn.commit()
    conn.close()
    return True


def archive_entry(listing_id, owner_id, on=True):
    """Every chat about one of your own entries, or none of them.

    On your own side an entry is one thing with several people in it, so it
    goes away in one piece. Half an entry in the list and half in the
    archive would be a worse state than either.
    """
    conn = connect()
    cur = conn.execute(
        "UPDATE conversations SET archived_owner = ?"
        " WHERE listing_id = ? AND EXISTS ("
        "     SELECT 1 FROM listings l WHERE l.id = conversations.listing_id"
        "       AND l.owner_id = ?)",
        (now() if on else None, listing_id, owner_id),
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def conversations_of(user_id):
    """Every conversation this student is in, newest message first."""
    conn = connect()
    rows = conn.execute(
        "SELECT c.id, c.listing_id, c.starter_id, l.title, l.type AS kind, l.owner_id,"
        # What the chats tab needs to put conversations in order and in
        # blocks. The three event fields answer whether two tickets are the
        # same party, the course answers the same for a group spot, and
        # created_at keeps your own entries in a fixed order.
        "       l.price, l.status, l.created_at AS listing_at,"
        "       l.event_date, l.event_time, l.place, l.course_id,"
        "       (SELECT name FROM courses k WHERE k.id = l.course_id) AS course_name,"
        "       (SELECT COALESCE(official_code, code) FROM courses k"
        "         WHERE k.id = l.course_id) AS course_code,"
        "       CASE WHEN l.owner_id = ? THEN c.starter_id ELSE l.owner_id END AS other_id,"
        "       (SELECT name FROM users u WHERE u.id ="
        "           CASE WHEN l.owner_id = ? THEN c.starter_id ELSE l.owner_id END"
        "       ) AS other_name,"
        "       (SELECT photo FROM users u WHERE u.id ="
        "           CASE WHEN l.owner_id = ? THEN c.starter_id ELSE l.owner_id END"
        "       ) AS other_photo,"
        "       (SELECT body FROM messages m WHERE m.conversation_id = c.id"
        "        ORDER BY m.id DESC LIMIT 1) AS last_body,"
        "       (SELECT created_at FROM messages m WHERE m.conversation_id = c.id"
        "        ORDER BY m.id DESC LIMIT 1) AS last_at,"
        "       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id"
        "        AND m.sender_id <> ? AND m.read_at IS NULL) AS unread,"
        # Archived is asked of your own side only. The same chat can be put
        # away by one of you and still be open in the other one's list.
        "       CASE WHEN l.owner_id = ? THEN c.archived_owner"
        "            ELSE c.archived_starter END AS archived"
        "  FROM conversations c JOIN listings l ON l.id = c.listing_id"
        " WHERE c.starter_id = ? OR l.owner_id = ?"
        " ORDER BY last_at DESC, c.id DESC",
        (user_id, user_id, user_id, user_id, user_id, user_id, user_id),
    ).fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------------ messages

def messages_of(conv_id):
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    ).fetchall()
    conn.close()
    return rows


def send_message(conv_id, sender_id, body):
    """Write a line, and bring the chat back out of the archive.

    Archiving says this is over. A message says it is not, so it wins. The
    one chat comes back for the student who wrote about the entry, and the
    whole entry comes back for its owner, because that side is archived all
    or nothing.
    """
    body = body.strip()
    if not body or len(body) > 500 or not can_see_conversation(get_conversation(conv_id), sender_id):
        return None
    conn = connect()
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, sender_id, body, created_at)"
        " VALUES (?, ?, ?, ?)",
        (conv_id, sender_id, body, now()),
    )
    conn.execute(
        "UPDATE conversations SET archived_starter = NULL WHERE id = ?",
        (conv_id,),
    )
    conn.execute(
        "UPDATE conversations SET archived_owner = NULL WHERE listing_id ="
        " (SELECT listing_id FROM conversations WHERE id = ?)",
        (conv_id,),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def mark_read(conv_id, reader_id):
    conn = connect()
    conn.execute(
        "UPDATE messages SET read_at = ?"
        " WHERE conversation_id = ? AND sender_id <> ? AND read_at IS NULL",
        (now(), conv_id, reader_id),
    )
    conn.commit()
    conn.close()


def unread_total(user_id):
    conn = connect()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM messages m"
        "  JOIN conversations c ON c.id = m.conversation_id"
        "  JOIN listings l ON l.id = c.listing_id"
        " WHERE m.sender_id <> ? AND m.read_at IS NULL"
        "   AND (c.starter_id = ? OR l.owner_id = ?)"
        "   AND (CASE WHEN l.owner_id = ? THEN c.archived_owner"
        "             ELSE c.archived_starter END) IS NULL",
        (user_id, user_id, user_id, user_id),
    ).fetchone()
    conn.close()
    return row["n"]


def take_security_attempt(key, limit=10, window=600):
    """Shared throttle. Stored in SQLite so restarting does not clear it."""
    import time
    current = int(time.time())
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM security_limits WHERE key=?", (key,)).fetchone()
            if not row or current - row["start"] >= window:
                conn.execute(
                    "INSERT OR REPLACE INTO security_limits VALUES (?,?,1)", (key, current))
                conn.execute("DELETE FROM security_limits WHERE start<?", (current-86400,))
                return True
            if row["count"] >= limit:
                return False
            conn.execute("UPDATE security_limits SET count=count+1 WHERE key=?", (key,))
            return True
    finally:
        conn.close()


# ------------------------------------------------------------- screenshots

def take_ai_read(user_id, limit, pictures=1):
    """Count screenshots read today. False when they would go over the limit.

    Counted before the read, so a student who keeps retrying a failing
    screenshot still stops at the limit.
    """
    if not isinstance(pictures, int) or pictures < 1:
        return False
    day = datetime.now(timezone.utc).date().isoformat()
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT count FROM ai_reads WHERE user_id = ? AND day = ?",
                (user_id, day)).fetchone()
            if (row["count"] if row else 0) + pictures > limit:
                return False
            conn.execute(
                "INSERT INTO ai_reads (user_id, day, count) VALUES (?, ?, ?)"
                " ON CONFLICT(user_id, day) DO UPDATE SET count = count + ?",
                (user_id, day, pictures, pictures))
            return True
    finally:
        conn.close()


# ------------------------------------------------------------ notifications

# "all" is the main switch above the four. Off silences everything at once
# and keeps the four as they were, so switching it back on restores them.
NOTIFY_AREAS = ("all", "messages", "ticket", "housing", "item", "group")


def save_device(user_id, endpoint, p256dh, auth):
    """Remember one device for push. The same device again just moves owner."""
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO push_devices (endpoint, user_id, p256dh, auth, created_at)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT(endpoint) DO UPDATE SET"
            " user_id = excluded.user_id, p256dh = excluded.p256dh,"
            " auth = excluded.auth",
            (endpoint, user_id, p256dh, auth, now()))
    conn.close()


def drop_device(endpoint, user_id=None):
    """Forget a device, because it said goodbye or the push service did."""
    conn = connect()
    with conn:
        if user_id is None:
            conn.execute("DELETE FROM push_devices WHERE endpoint = ?", (endpoint,))
        else:
            conn.execute("DELETE FROM push_devices WHERE endpoint = ? AND user_id = ?",
                         (endpoint, user_id))
    conn.close()


def devices_of(user_id):
    conn = connect()
    rows = conn.execute("SELECT * FROM push_devices WHERE user_id = ?",
                        (user_id,)).fetchall()
    conn.close()
    return rows


def prefs_of(user_id):
    """{area: {"on": bool, ...}} for all four areas. All on until switched off.

    For the three tabs this is the main switch. What actually rings is a
    saved search or a watched event; switching the area off silences all of
    them at once without throwing them away.
    """
    prefs = {area: {"on": True, "q": "", "cat": ""} for area in NOTIFY_AREAS}
    conn = connect()
    for row in conn.execute("SELECT * FROM notify_prefs WHERE user_id = ?", (user_id,)):
        if row["area"] in prefs:
            prefs[row["area"]] = {"on": bool(row["is_on"]), "q": row["q"], "cat": row["cat"]}
    conn.close()
    return prefs


def set_pref(user_id, area, on, q=None, cat=None):
    """Turn one area on or off. q and cat of None keep what was there."""
    if area not in NOTIFY_AREAS:
        raise ValueError(f"unknown area {area}")
    old = prefs_of(user_id)[area]
    q = old["q"] if q is None else q.strip()[:80]
    cat = old["cat"] if cat is None else cat.strip()[:30]
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO notify_prefs (user_id, area, is_on, q, cat) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id, area) DO UPDATE SET is_on = excluded.is_on,"
            " q = excluded.q, cat = excluded.cat",
            (user_id, area, 1 if on else 0, q, cat))
    conn.close()


def watch_search(user_id, kind, params, label):
    """Save one search. params is the JSON string, label the readable one."""
    conn = connect()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO watched_searches (user_id, kind, params, label,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, kind, params, label[:120], now()))
    conn.close()


def unwatch_search(user_id, kind=None, params=None, watch_id=None):
    """Forget one saved search, by the search itself or by its row."""
    conn = connect()
    with conn:
        if watch_id is not None:
            conn.execute("DELETE FROM watched_searches WHERE id = ? AND user_id = ?",
                         (watch_id, user_id))
        else:
            conn.execute("DELETE FROM watched_searches WHERE user_id = ? AND kind = ?"
                         " AND params = ?", (user_id, kind, params))
    conn.close()


def is_watching_search(user_id, kind, params):
    conn = connect()
    row = conn.execute("SELECT 1 FROM watched_searches WHERE user_id = ? AND kind = ?"
                       " AND params = ?", (user_id, kind, params)).fetchone()
    conn.close()
    return row is not None


def searches_watched(user_id):
    """Every search a student saved, Tickets first, then Housing, then Market."""
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM watched_searches WHERE user_id = ? ORDER BY"
        " CASE kind WHEN 'ticket' THEN 0 WHEN 'housing' THEN 1 ELSE 2 END, created_at",
        (user_id,)).fetchall()
    conn.close()
    return rows


def search_watchers(kind):
    """Every saved search on one tab, with whose it is."""
    conn = connect()
    rows = conn.execute("SELECT user_id, params FROM watched_searches WHERE kind = ?",
                        (kind,)).fetchall()
    conn.close()
    return rows


def watch_event(user_id, key, title, place):
    """Start watching one event. key is (date, time, place boiled down)."""
    event_date, event_time, place_key = key
    conn = connect()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO event_watches (user_id, event_date, event_time,"
            " place_key, title, place, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, event_date, event_time, place_key, title[:60], (place or "")[:60], now()))
    conn.close()


def unwatch_event(user_id, key=None, watch_id=None):
    """Stop watching, either by the event itself or by the row in the settings."""
    conn = connect()
    with conn:
        if watch_id is not None:
            conn.execute("DELETE FROM event_watches WHERE id = ? AND user_id = ?",
                         (watch_id, user_id))
        else:
            conn.execute(
                "DELETE FROM event_watches WHERE user_id = ? AND event_date = ?"
                " AND event_time = ? AND place_key = ?", (user_id, *key))
    conn.close()


def is_watching_event(user_id, key):
    conn = connect()
    row = conn.execute(
        "SELECT 1 FROM event_watches WHERE user_id = ? AND event_date = ?"
        " AND event_time = ? AND place_key = ?", (user_id, *key)).fetchone()
    conn.close()
    return row is not None


def events_watched(user_id):
    """The events a student watches that have not happened yet, soonest first.

    Past ones are thrown away on the way, nobody needs to hear about them.
    """
    today = active_day()
    conn = connect()
    with conn:
        conn.execute("DELETE FROM event_watches WHERE user_id = ? AND event_date < ?",
                     (user_id, today))
        rows = conn.execute(
            "SELECT * FROM event_watches WHERE user_id = ?"
            " ORDER BY event_date, event_time, title", (user_id,)).fetchall()
    conn.close()
    return rows


def event_watchers(key):
    """Everyone watching this one event."""
    conn = connect()
    rows = conn.execute(
        "SELECT user_id FROM event_watches WHERE event_date = ? AND event_time = ?"
        " AND place_key = ?", key).fetchall()
    conn.close()
    return [row["user_id"] for row in rows]


def watch_course(user_id, course_id):
    """Start watching one course: tell me about every group for it."""
    conn = connect()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO course_watches (user_id, course_id, created_at)"
            " VALUES (?, ?, ?)", (user_id, course_id, now()))
    conn.close()


def unwatch_course(user_id, course_id=None, watch_id=None):
    """Stop watching, either by the course itself or by the row in the settings."""
    conn = connect()
    with conn:
        if watch_id is not None:
            conn.execute("DELETE FROM course_watches WHERE id = ? AND user_id = ?",
                         (watch_id, user_id))
        else:
            conn.execute("DELETE FROM course_watches WHERE user_id = ? AND course_id = ?",
                         (user_id, course_id))
    conn.close()


def is_watching_course(user_id, course_id):
    conn = connect()
    row = conn.execute(
        "SELECT 1 FROM course_watches WHERE user_id = ? AND course_id = ?",
        (user_id, course_id)).fetchone()
    conn.close()
    return row is not None


def courses_watched(user_id):
    """The courses a student watches, by name, with the code to show under it."""
    conn = connect()
    rows = conn.execute(
        "SELECT w.id, w.course_id, c.name, c.code FROM course_watches w"
        " JOIN courses c ON c.id = w.course_id"
        " WHERE w.user_id = ? ORDER BY c.name", (user_id,)).fetchall()
    conn.close()
    return rows


def course_watchers(course_id):
    """Everyone watching this one course."""
    conn = connect()
    rows = conn.execute("SELECT user_id FROM course_watches WHERE course_id = ?",
                        (course_id,)).fetchall()
    conn.close()
    return [row["user_id"] for row in rows]
