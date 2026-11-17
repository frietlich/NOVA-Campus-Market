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
    deposit_months INTEGER,                      -- deposit, in months of rent
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
    UNIQUE (listing_id, starter_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    sender_id       INTEGER NOT NULL REFERENCES users(id),
    body            TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    read_at         TEXT
);

-- One heart. A student saved an entry, which is the whole table. There is no
-- row for a heart that was taken away again, it is simply deleted.
CREATE TABLE IF NOT EXISTS saves (
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
