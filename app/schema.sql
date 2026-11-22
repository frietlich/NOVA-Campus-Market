-- Campus Market, the whole database.
-- Seven tables. Nothing else is stored anywhere.

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT    NOT NULL UNIQUE,          -- always ends in @novasbe.pt
    name       TEXT    NOT NULL,                 -- shown as "Mariana S."
    programme  TEXT    NOT NULL DEFAULT '',      -- one of the names in programmes.py
    cems       INTEGER NOT NULL DEFAULT 0,       -- the CEMS double degree, on top
    photo      TEXT,                             -- a file in static/uploads, or NULL
    password   TEXT,                             -- the salted hash, never the
                                                 -- password itself
    verified   INTEGER NOT NULL DEFAULT 0,       -- 0 until the e-mail code was right
    code       TEXT,                             -- the 6 digits we last sent
    code_sent  TEXT,                             -- when that code went out
    code_tries INTEGER NOT NULL DEFAULT 0,       -- wrong guesses at that code
    created_at TEXT    NOT NULL
);

-- Every course at the school. A course is a thing, not a piece of text, so
-- two students can never write the same course two different ways.
CREATE TABLE IF NOT EXISTS courses (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    code      TEXT    NOT NULL UNIQUE,           -- FIN2101
    name      TEXT    NOT NULL,                  -- Corporate Finance
    programme TEXT    NOT NULL DEFAULT ''
);

-- Which courses a student is taking. This is what makes the Groups tab short.
CREATE TABLE IF NOT EXISTS enrolments (
    user_id   INTEGER NOT NULL REFERENCES users(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    PRIMARY KEY (user_id, course_id)
);

CREATE TABLE IF NOT EXISTS listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    type        TEXT    NOT NULL,                -- housing, ticket, item, group
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    price       REAL,                            -- NULL means no price
    info        TEXT    NOT NULL DEFAULT '',     -- the grey line under the title
    category    TEXT,                            -- tickets and market, categories.py
    condition   TEXT,                            -- market only, how worn it is
    event_date  TEXT,                            -- tickets only, YYYY-MM-DD
    event_time  TEXT,                            -- tickets only, HH:MM
    place       TEXT,                            -- tickets only, the venue name
    address     TEXT,                            -- tickets only, the street address
    quantity    INTEGER,                         -- how many are left. Tickets to
                                                 -- sell, or free spots in a group
    course_id   INTEGER REFERENCES courses(id),  -- groups only
    hand_in     TEXT,                            -- groups only, YYYY-MM-DD
    group_size  INTEGER,                         -- groups only, how many in all
    -- housing only, see housing.py. place holds the area and address the
    -- street, the same two columns a ticket uses for its venue.
    available_from TEXT,                         -- YYYY-MM-DD
    months_min     INTEGER,                      -- shortest stay they accept
    bills_included INTEGER,                      -- 1 when the rent is all in
    bills_estimate REAL,                         -- what bills cost on top
    minutes_campus INTEGER,                      -- door to campus, their guess
    flatmates      INTEGER,                      -- how many already live there
    features       TEXT,                        -- a comma separated list
    status      TEXT    NOT NULL DEFAULT 'open', -- open or closed
    views       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    filename   TEXT    NOT NULL,
    position   INTEGER NOT NULL DEFAULT 0
);

-- One conversation is one listing plus the one student who wrote about it.
-- The owner is not stored here, it comes from the listing.
CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    starter_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT    NOT NULL,
    -- Archiving is one person's decision, not the chat's, so each side has
    -- its own stamp. NULL means it is still in that person's list. The owner
    -- archives a whole entry at once, the student who wrote archives the one
    -- chat, and a new message clears the stamp again either way.
    archived_owner   TEXT,
    archived_starter TEXT,
    UNIQUE (listing_id, starter_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    sender_id       INTEGER NOT NULL REFERENCES users(id),
    body            TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    read_at         TEXT,
    -- text is somebody typing. closed is the app saying the entry is gone,
    -- written when the owner closes it. It is a real message because it has
    -- to do what a message does, sit in the thread at its own time, lift the
    -- chat up the list and count as unread for everyone but the sender. The
    -- sender of a closed row is the owner, which is what makes that last
    -- part true without a rule of its own.
    kind            TEXT    NOT NULL DEFAULT 'text'
);

-- One heart. A student saved an entry, which is the whole table. There is no
-- row for a heart that was taken away again, it is simply deleted.
CREATE TABLE IF NOT EXISTS saves (
    user_id    INTEGER NOT NULL REFERENCES users(id),
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    created_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, listing_id)
);

-- One student looked at one entry. The row is what makes the number on an
-- entry mean something, because without it a count went up every time the
-- same person pressed reload. listings.views is kept as the running total
-- so every list can still show it without counting rows.
CREATE TABLE IF NOT EXISTS views (
    user_id    INTEGER NOT NULL REFERENCES users(id),
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    created_at TEXT    NOT NULL,
    PRIMARY KEY (user_id, listing_id)
);

CREATE INDEX IF NOT EXISTS idx_listings_type   ON listings (type, status);
CREATE INDEX IF NOT EXISTS idx_messages_conv   ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_conv_listing    ON conversations (listing_id);
CREATE INDEX IF NOT EXISTS idx_listings_course ON listings (course_id);
CREATE INDEX IF NOT EXISTS idx_enrolments_user ON enrolments (user_id);
CREATE INDEX IF NOT EXISTS idx_saves_listing   ON saves (listing_id);

-- Official academic-year catalogue: a course can have a different type for
-- each programme. This table avoids duplicating the course itself.
CREATE TABLE IF NOT EXISTS course_offerings (
    course_id INTEGER NOT NULL REFERENCES courses(id),
    programme TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('MANDATORY','ELECTIVE','EXCLUSIVE_ELECTIVE','OUT_PROGRAM')),
    PRIMARY KEY (course_id, programme)
);
CREATE INDEX IF NOT EXISTS idx_course_offerings_programme ON course_offerings (programme, type);

-- How often a student had a screenshot read by Claude today. Every read
-- costs money, so there is a daily limit per student.
CREATE TABLE IF NOT EXISTS ai_reads (
    user_id INTEGER NOT NULL REFERENCES users(id),
    day     TEXT    NOT NULL,                    -- 2026-11-21
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

-- One phone or browser that agreed to get notifications. A student can have
-- several. The three values come from the browser and are what the push
-- service needs to reach exactly that device.
CREATE TABLE IF NOT EXISTS push_devices (
    endpoint   TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    p256dh     TEXT    NOT NULL,
    auth       TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_push_devices_user ON push_devices (user_id);

-- What a student wants to hear about, one row per area: messages, ticket,
-- housing or item. No row means the default: messages on, the rest off.
-- For the three tabs, q and cat narrow it down to what they were searching
-- for when they turned it on, so "party" only rings for parties.
CREATE TABLE IF NOT EXISTS notify_prefs (
    user_id INTEGER NOT NULL REFERENCES users(id),
    area    TEXT    NOT NULL,
    is_on   INTEGER NOT NULL,
    q       TEXT    NOT NULL DEFAULT '',
    cat     TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, area)
);

-- One event a student wants to hear about: tell me when somebody else puts up
-- a ticket for it. An event is the same day, time and place, whatever the
-- sellers called their ticket, so place_key is the place boiled down the same
-- way the Tickets tab does it. title and place are only for the list in the
-- settings. A student can watch as many events as they like.
CREATE TABLE IF NOT EXISTS event_watches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    event_date TEXT    NOT NULL,
    event_time TEXT    NOT NULL DEFAULT '',
    place_key  TEXT    NOT NULL DEFAULT '',
    title      TEXT    NOT NULL,
    place      TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    UNIQUE (user_id, event_date, event_time, place_key)
);
CREATE INDEX IF NOT EXISTS idx_event_watches_event ON event_watches (event_date, event_time, place_key);

-- One course a student wants to hear about: tell me when somebody else puts
-- up a group for it. The same thing as a watched event one table up, only
-- what makes two of them the same is the course rather than a day, a time
-- and a place.
CREATE TABLE IF NOT EXISTS course_watches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    created_at TEXT    NOT NULL,
    UNIQUE (user_id, course_id)
);
CREATE INDEX IF NOT EXISTS idx_course_watches_course ON course_watches (course_id);

-- One search a student wants to hear about, with every filter it had: tell
-- me when something new goes up that this search would find. params is the
-- search as it stood in the address of the tab, so a new entry is checked
-- with exactly the search the tab itself runs. label is the readable version
-- for the list in the settings. As many per tab as they like.
CREATE TABLE IF NOT EXISTS watched_searches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    kind       TEXT    NOT NULL,                 -- ticket, housing or item
    params     TEXT    NOT NULL,                 -- JSON, keys sorted
    label      TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    UNIQUE (user_id, kind, params)
);
CREATE INDEX IF NOT EXISTS idx_watched_searches_kind ON watched_searches (kind);
