"""The only file that talks to the database.

Every other file calls a function from here. Nobody else writes SQL.
If you need something the app cannot do yet, add a function here first.
"""

import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone

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
CODE_MINUTES = 15
CODE_TRIES = 5

# Columns added after the first version. setup() puts them into an older
# campus.db, so nobody has to wipe their database to get them.
LATER_COLUMNS = {
    "users": [
        ("code_sent", "TEXT"),
        ("code_tries", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "listings": [
        ("condition", "TEXT"),
        ("hand_in", "TEXT"),
        ("group_size", "INTEGER"),
        ("available_from", "TEXT"),
        ("months_min", "INTEGER"),
        ("bills_included", "INTEGER"),
        ("bills_estimate", "REAL"),
        ("deposit_months", "INTEGER"),
        ("minutes_campus", "INTEGER"),
        ("flatmates", "INTEGER"),
        ("features", "TEXT"),
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


# --------------------------------------------------------------------- users

def is_nova_email(email):
    """True only for a Nova address. This is the whole door policy."""
    return bool(email) and bool(EMAIL_SHAPE.fullmatch(email.strip().lower()))


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
    """Save what the edit page sends. photo of None leaves the picture alone."""
    conn = connect()
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
    conn.commit()
    conn.close()


def set_password(user_id, hashed):
    """Store a new password. It arrives hashed, never as what was typed."""
    conn = connect()
    conn.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, user_id))
    conn.commit()
    conn.close()


def new_code(user_id):
    """Make a fresh 6 digit code, store it, give it back so we can send it.

    secrets and not random, because random is predictable by design and a
    code is exactly the kind of thing nobody must be able to predict.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"
    conn = connect()
    conn.execute(
        "UPDATE users SET code = ?, code_sent = ?, code_tries = 0 WHERE id = ?",
        (code, now(), user_id),
    )
    conn.commit()
    conn.close()
    return code


def code_age(user_id):
    """Seconds since the last code went out, or None when there is none."""
    user = get_user(user_id)
    if user is None or not user["code"] or not user["code_sent"]:
        return None
    sent = datetime.fromisoformat(user["code_sent"])
    return (datetime.now(timezone.utc) - sent).total_seconds()


def check_code(user_id, code):
    """Check a code. Gives back one word:

    "ok"        right, and the user is now verified
    "wrong"     not the code, try again
    "expired"   older than CODE_MINUTES, a new one is needed
    "locked"    too many wrong guesses, a new one is needed
    "none"      there is no code to check against
    """
    user = get_user(user_id)
    if user is None or not user["code"]:
        return "none"
    age = code_age(user_id)
    if age is None or age > CODE_MINUTES * 60:
        return "expired"
    if user["code_tries"] >= CODE_TRIES:
        return "locked"

    conn = connect()
    if not secrets.compare_digest(str(code).strip(), user["code"]):
        conn.execute(
            "UPDATE users SET code_tries = code_tries + 1 WHERE id = ?", (user_id,)
        )
        conn.commit()
        conn.close()
        return "locked" if user["code_tries"] + 1 >= CODE_TRIES else "wrong"

    conn.execute(
        "UPDATE users SET verified = 1, code = NULL, code_sent = NULL,"
        " code_tries = 0 WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()
    return "ok"


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


def listings_of_type(kind, search="", only_for=None, category=None, sort=None,
                     min_price=None, max_price=None, free_only=False,
                     condition=None, free_from=None, area=None,
                     max_minutes=None, max_months=None, bills_included=False,
                     features=None, price_inclusive=False):
    """Open listings in one tab.

    Search looks in the title, the grey line and the course name. Give
    only_for a user id and you get back just the entries whose course that
    student is taking. That is what keeps the Groups tab short.

    The price arguments are a band, not two boxes a student typed into. An
    entry with no price is free, so it counts as being under every ceiling.
    """
    where = "l.type = ? AND l.status = 'open'"
    args = [kind]

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

    if search.strip():
        # The dates are in here too, so Dec or 5 Dec finds the group that has
        # to be together by then without the page needing a date picker.
        parts = ("l.title LIKE ? OR l.info LIKE ? OR l.description LIKE ?"
                 " OR c.name LIKE ? OR c.code LIKE ?")
        args += [f"%{search.strip()}%"] * 5
        hint = date_hint(search)
        if hint:
            parts += " OR l.hand_in LIKE ? OR l.event_date LIKE ?"
            args += [f"%{hint}%"] * 2
        where += f" AND ({parts})"

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
                   bills_estimate=None, deposit_months=None,
                   minutes_campus=None, flatmates=None, features=None):
    if kind not in TYPES:
        raise ValueError(f"unknown type {kind}")
    conn = connect()
    cur = conn.execute(
        "INSERT INTO listings (owner_id, type, title, description, price, info,"
        " category, condition, event_date, event_time, place, address, quantity,"
        " course_id, hand_in, group_size, available_from, months_min,"
        " bills_included, bills_estimate, deposit_months, minutes_campus,"
        " flatmates, features, status, views, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
        " ?, ?, ?, ?, 'open', 0, ?)",
        (owner_id, kind, title, description, price, info, category, condition,
         event_date, event_time, place, address, quantity, course_id, hand_in,
         group_size, available_from, months_min, bills_included, bills_estimate,
         deposit_months, minutes_campus, flatmates, features, now()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def close_listing(listing_id, owner_id):
    """Only the owner can close. Returns True if something actually changed."""
    conn = connect()
    cur = conn.execute(
        "UPDATE listings SET status = 'closed' WHERE id = ? AND owner_id = ?",
        (listing_id, owner_id),
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def reopen_listing(listing_id, owner_id):
    conn = connect()
    cur = conn.execute(
        "UPDATE listings SET status = 'open' WHERE id = ? AND owner_id = ?",
        (listing_id, owner_id),
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def count_view(listing_id):
    conn = connect()
    conn.execute("UPDATE listings SET views = views + 1 WHERE id = ?", (listing_id,))
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
    today = datetime.now().strftime("%Y-%m-%d")
    conn = connect()
    rows = conn.execute(
        _listing_sql("s.user_id = ? AND (l.type != 'ticket' OR l.event_date >= ?)",
                     order="s.created_at DESC",
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
        "SELECT c.*, l.title, l.price, l.type, l.owner_id"
        "  FROM conversations c JOIN listings l ON l.id = c.listing_id"
        " WHERE c.id = ?",
        (conv_id,),
    ).fetchone()
    conn.close()
    return row


def can_see_conversation(conv, user_id):
    """Only the two people in it. This is what keeps chats private."""
    return conv is not None and user_id in (conv["starter_id"], conv["owner_id"])


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
        "        AND m.sender_id <> ? AND m.read_at IS NULL) AS unread"
        "  FROM conversations c JOIN listings l ON l.id = c.listing_id"
        " WHERE c.starter_id = ? OR l.owner_id = ?"
        " ORDER BY last_at DESC, c.id DESC",
        (user_id, user_id, user_id, user_id, user_id, user_id),
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
    body = body.strip()
    if not body:
        return None
    conn = connect()
    cur = conn.execute(
        "INSERT INTO messages (conversation_id, sender_id, body, created_at)"
        " VALUES (?, ?, ?, ?)",
        (conv_id, sender_id, body, now()),
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
        "   AND (c.starter_id = ? OR l.owner_id = ?)",
        (user_id, user_id, user_id),
    ).fetchone()
    conn.close()
    return row["n"]


# ------------------------------------------------------------- screenshots

def take_ai_read(user_id, limit, pictures=1):
    """Count screenshots read today. False when they would go over the limit.

    Counted before the read, so a student who keeps retrying a failing
    screenshot still stops at the limit.
    """
    day = datetime.now(timezone.utc).date().isoformat()
    conn = connect()
    try:
        with conn:
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

NOTIFY_AREAS = ("messages", "ticket", "housing", "item")


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
    """{area: {"on": bool, "q": str, "cat": str}} for all four areas."""
    prefs = {area: {"on": area == "messages", "q": "", "cat": ""}
             for area in NOTIFY_AREAS}
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


def watchers_of(kind):
    """Everyone who turned on notifications for new entries of this kind."""
    conn = connect()
    rows = conn.execute(
        "SELECT user_id, q, cat FROM notify_prefs WHERE area = ? AND is_on = 1",
        (kind,)).fetchall()
    conn.close()
    return rows
