"""The only file that talks to the database.

Every other file calls a function from here. Nobody else writes SQL.
If you need something the app cannot do yet, add a function here first.
"""

import os
import secrets
import sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("CAMPUS_DB", os.path.join(os.path.dirname(HERE), "campus.db"))
SCHEMA_PATH = os.path.join(HERE, "schema.sql")

TYPES = ("housing", "ticket", "item", "group")
EMAIL_DOMAIN = "@novasbe.pt"

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
    return bool(email) and email.strip().lower().endswith(EMAIL_DOMAIN)


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

def _listing_sql(where, order="l.created_at DESC"):
    return (
        "SELECT l.*, u.name AS owner_name, u.programme AS owner_programme,"
        "       u.cems AS owner_cems, u.photo AS owner_photo,"
        "       c.name AS course_name, COALESCE(c.official_code,c.code) AS course_code,"
        "       (SELECT filename FROM photos p WHERE p.listing_id = l.id"
        "        ORDER BY p.position, p.id LIMIT 1) AS photo"
        "  FROM listings l JOIN users u ON u.id = l.owner_id"
        "  LEFT JOIN courses c ON c.id = l.course_id"
        f" WHERE {where} ORDER BY {order}"
    )


ORDER_FOR = {
    "ticket": "l.event_date, l.event_time, l.price, l.id",
}


def listings_of_type(kind, search="", only_for=None, category=None):
    """Open listings in one tab.

    Search looks in the title, the grey line and the course name. Give
    only_for a user id and you get back just the entries whose course that
    student is taking. That is what keeps the Groups tab short.
    """
    where = "l.type = ? AND l.status = 'open'"
    args = [kind]

    if category:
        where += " AND COALESCE(l.category, 'other') = ?"
        args.append(category)

    if only_for is not None:
        where += (" AND l.course_id IN (SELECT course_id FROM enrolments"
                  " WHERE user_id = ?)")
        args.append(only_for)

    if search.strip():
        where += (" AND (l.title LIKE ? OR l.info LIKE ? OR l.description LIKE ?"
                  " OR c.name LIKE ? OR c.code LIKE ?)")
        args += [f"%{search.strip()}%"] * 5

    conn = connect()
    order = ORDER_FOR.get(kind, "l.created_at DESC")
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
                   category=None, event_date=None, event_time=None, place=None,
                   address=None, quantity=None, course_id=None):
    if kind not in TYPES:
        raise ValueError(f"unknown type {kind}")
    conn = connect()
    cur = conn.execute(
        "INSERT INTO listings (owner_id, type, title, description, price, info,"
        " category, event_date, event_time, place, address, quantity, course_id,"
        " status, views, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 0, ?)",
        (owner_id, kind, title, description, price, info, category, event_date,
         event_time, place, address, quantity, course_id, now()),
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
