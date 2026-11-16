"""Fill the database with fake students and fake entries.

Run it with   python -m app.seed   from the project folder.
It wipes what is there and writes the demo content again, so you can always
get back to a clean state. Every person and every entry in here is invented.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from . import db, passwords

ME = "58412@novasbe.pt"             # the student you are logged in as

# Everyone in the demo has this one, so you can try the real login with any
# of them. Fake students, fake password, it never leaves this file.
DEMO_PASSWORD = "Nova2026!"

# E-mail, name, programme, and whether they also do the CEMS double degree.
STUDENTS = [
    (ME,                      "Marco C.",    "Master in Finance",             0),
    ("61037@novasbe.pt",      "Mariana S.",  "Master in Finance",             0),
    ("59226@novasbe.pt",      "Tiago R.",    "Master in Management",          0),
    ("60884@novasbe.pt",      "Clara V.",    "Master in Finance",             0),
    ("57193@novasbe.pt",      "Sofia M.",    "Master in Business Analytics",  0),
    ("48305@novasbe.pt",      "André C.",    "Alumni",                        0),
    ("61572@novasbe.pt",      "Lena K.",     "Master in Finance",             0),
    ("59940@novasbe.pt",      "Inês B.",     "Master in Management",          1),
    ("60118@novasbe.pt",      "João P.",     "Master in Finance",             0),
    ("62287@novasbe.pt",      "Noah B.",     "Exchange",                      0),
]

# Demo records use the official catalogue. The keys below translate old demo
# references so pre-existing example conversations and group entries still work.
DEMO_COURSE_IDS = {
    'FIN2101': '2253', 'FIN2102': '2229', 'FIN2103': '2218',
    'FIN2104': '2270', 'FIN2105': '2248', 'FIN2106': '2225',
    'FIN2109': '2222', 'FIN2110': '2204', 'FIN2111': '2269',
    'MGT3201': '2584', 'MGT3204': '2431', 'MGT3207': '2473',
    'MGT3202': '2336', 'MGT3205': '2459', 'MGT3208': '2332',
    'BAN4301': '2767', 'BAN4302': '2609', 'BAN4307': '2659',
    'BAN4305': '2477', 'ECO5407': '2185', 'ECO5403': '2176',
    'GEN1501': '2375', 'GEN1502': '2652', 'GEN1503': '2477',
    'GEN1504': '2477', 'GEN1505': '2638', 'GEN1506': '2698',
}
ENROLMENTS = {
    "Marco C.":   ['FIN2111','FIN2104','BAN4305','FIN2101','FIN2102'],
    "Mariana S.": ['FIN2111','FIN2103','FIN2109','GEN1501'],
    "Tiago R.":  ['MGT3201','MGT3204','MGT3207','GEN1502'],
    "Clara V.":  ['BAN4305','FIN2102','FIN2106','GEN1503'],
    "Sofia M.":  ['BAN4301','BAN4302','BAN4307','FIN2104'],
    "André C.":  ['GEN1505','MGT3208'],
    "Lena K.":   ['FIN2101','FIN2105','FIN2111','GEN1504'],
    "Inês B.":   ['MGT3201','MGT3202','MGT3205','FIN2111'],
    "João P.":   ['FIN2104','FIN2110','ECO5407','FIN2101'],
    "Noah B.":  ['MGT3204','ECO5403','GEN1504','GEN1506'],
}

HOUSING = [
    ("Mariana S.", "Room in a 3-bed flat",      480,  "Carcavelos · from 1 Feb · own bathroom",
     "Bright room in a flat I share with two other Nova students. Five minutes to the train, "
     "fifteen to campus on foot. Comes furnished, with a desk and a double bed. Looking for "
     "someone tidy who stays until at least June."),
    ("Tiago R.",   "Studio sublet, Feb to June", 720, "Praia · bills included · 4 months",
     "My own studio, free while I am on exchange. Everything stays in it, you only bring "
     "clothes. Bills and internet are in the price."),
    ("Lena K.",    "Shared room, 8 min to campus", 390, "Parede · from 15 Jan · 2 flatmates",
     "Shared room in a quiet flat. Two flatmates, both Nova. Washing machine, small balcony, "
     "and the bus stops in front of the door."),
    ("Sofia M.",   "Lease takeover, flat for four", 1540, "Carcavelos · from 1 Mar · whole flat",
     "We are all finishing in February, so the whole flat is free from March. Four bedrooms, "
     "two bathrooms, furnished. The landlord is easy to deal with."),
    ("André C.",   "Room with balcony, long stay", 560, "São Pedro · from 1 Feb · 12 months",
     "Large room with its own balcony facing the sea. Twelve month contract only. Deposit of "
     "one month, paid back when you leave."),
    ("Clara V.",   "Single room, short term",    430,  "Oeiras · Jan to Mar · furnished",
     "Single room for the winter term only. Furnished, bills split four ways. Good if you are "
     "here for one semester."),
]

# Owner, category, date, time, venue, title, price each, how many,
# description. The street address of every venue is in ADDRESSES below. Saturday the 21st is on purpose crowded, six students selling
# for the same night at the same place, so you can see that the short view
# still shows the other three events of that day.
TICKETS = [
    ("Tiago R.",     "party",     "2026-11-20", "19:00", "Rooftop Bairro Alto",
     "Sunset rooftop party", 15, 2,
     "Leaving at midnight. Two tickets left for the rooftop party. Transfer "
     "by app, I send them the same day."),
    ("Lena K.",      "travel",    "2026-11-20", "07:30", "Sete Rios",
     "Bus to Porto, one seat", 12, 1,
     "Window seat, can be renamed. I booked the early bus and cannot go. The "
     "company lets you rename the ticket for free until the day before."),
    ("Clara V.",     "party",     "2026-11-21", "23:00", "Urban Beach",
     "Student night, Urban Beach", 12, 1,
     "Entry before 1am. One spare ticket. Entry only before one in the "
     "morning, after that the ticket is dead."),
    ("Mariana S.",   "party",     "2026-11-21", "23:00", "Urban Beach",
     "Two for student night", 12, 2,
     "Entry before 1am. Two tickets, we are not going any more. Same price I "
     "paid."),
    ("João P.",      "party",     "2026-11-21", "23:00", "Urban Beach",
     "Urban Beach, one left", 10, 1,
     "Entry before 1am. Selling below face value, I just want it gone."),
    ("Noah B.",      "party",     "2026-11-21", "23:00", "Urban Beach",
     "Student night tickets", 14, 2,
     "Entry before 1am. Two tickets. I can meet on campus during the day to "
     "hand them over."),
    ("Sofia M.",     "party",     "2026-11-21", "23:00", "Urban Beach",
     "One ticket, Saturday", 12, 1,
     "Entry before 1am. One ticket for Saturday. Transfer by app."),
    ("Lena K.",      "party",     "2026-11-21", "23:00", "Urban Beach",
     "Three for Urban Beach", 11, 3,
     "Entry before 1am. Three together, our group dropped out. Happy to "
     "split them up."),
    ("Lena K.",      "sports",    "2026-11-21", "09:00", "Jamor",
     "Padel tournament, day pass", None, 3,
     "Saturday morning. Three day passes going free, we signed up and cannot "
     "make it. First to write gets them."),
    ("André C.",     "concert",   "2026-11-21", "21:00", "Coliseu dos Recreios",
     "Jazz at the Coliseu", 28, 2,
     "Seats together, first balcony. Two seats next to each other. Printed "
     "tickets, I hand them over on campus."),
    ("Inês B.",      "culture",   "2026-11-21", "18:00", "Museu Berardo",
     "Museum night, two entries", 6, 2,
     "Entry until 22:00. Two entries for the late opening. They are not "
     "named, anyone can use them."),
    ("Sofia M.",     "culture",   "2026-11-27", "20:00", "Hotel Cascais Miragem",
     "Finance Ball, seated table", 45, 1,
     "One seat at our table of eight. Dinner included, drinks are not."),
    ("Noah B.",      "travel",    "2026-11-28", "06:15", "Lisbon Airport",
     "Flight to Madrid, one seat", 39, 1,
     "Hand luggage only. I booked twice by mistake. The name can be changed "
     "for a small fee."),
    ("André C.",     "sports",    "2026-11-29", "17:30", "Estádio da Luz",
     "Football, upper tier", 38, 2,
     "Seats together. Two seats next to each other in the upper tier. "
     "Printed tickets."),
    ("Mariana S.",   "sports",    "2026-12-06", "08:00", "Parque das Nações",
     "Half marathon bib", 25, 1,
     "Transfer by 5 Dec. My bib for the half marathon. The transfer has to "
     "go through before the fifth of December."),
]

# The street address of each venue, so the entry can point at a map.
ADDRESSES = {
    "Rooftop Bairro Alto":     "R. do Norte 35, 1200-286 Lisboa",
    "Sete Rios":               "Terminal Rodoviário de Sete Rios, 1500-423 Lisboa",
    "Urban Beach":             "Cais da Viscondessa, 1200-109 Lisboa",
    "Jamor":                   "Complexo do Jamor, 1495-751 Cruz Quebrada",
    "Coliseu dos Recreios":    "R. das Portas de Santo Antão 96, 1150-269 Lisboa",
    "Museu Berardo":           "Praça do Império, 1449-003 Lisboa",
    "Hotel Cascais Miragem":   "Av. Marginal 8554, 2754-536 Cascais",
    "Lisbon Airport":          "Alameda das Comunidades Portuguesas, 1700-111 Lisboa",
    "Estádio da Luz":          "Av. Eusébio da Silva Ferreira, 1500-313 Lisboa",
    "Parque das Nações":       "Passeio de Neptuno, 1990-193 Lisboa",
}

MARKET = [
    ("Mariana S.", "iPad Air, 11 inch",        290, "Good condition · with pencil",
     "Two years old, always in a case. Comes with the pencil and the charger. Battery still "
     "holds a full day."),
    ("Lena K.",    "Desk and chair",            45, "Used · pick up in Carcavelos",
     "Simple desk and an office chair. Both work fine, the desk has a scratch on the top. "
     "Pick up only, I cannot deliver."),
    ("Tiago R.",   "Finance textbooks, bundle", 30, "Good condition · three books",
     "Three books from last year, Corporate Finance, Investments and Derivatives. Barely "
     "written in."),
    ("Sofia M.",   "City bike",                120, "Good condition · lock and lights",
     "City bike, seven gears, serviced last month. Lock and both lights are included."),
    ("André C.",   "Monitor, 27 inch",          95, "Good condition · no dead pixels",
     "27 inch monitor, 1440p. No dead pixels, no scratches. Stand and cable included."),
    ("Clara V.",   "Winter coat, size M",       25, "Good condition · worn one season",
     "Warm winter coat, size M, worn for one season only. Washed and ready."),
]

# Owner, course, title, free spots, grey line, description.
# Three of these are in a course you take, the rest are not. That difference is
# the whole point of the Groups tab.
GROUPS = [
    ("Marco C.",  "FIN2111", "Final project, panel data",     1, "Group of four · hand in 28 Nov",
     "We are three and need one more for the final project. Panel data, we already have the "
     "dataset. We meet twice a week in the library."),
    ("Inês B.",   "MGT3201", "Case study, group of five",     2, "Group of five · hand in 2 Dec",
     "Two spots left in our group of five. The case is already picked, we split the sections "
     "evenly."),
    ("João P.",   "FIN2104", "Valuation assignment",          1, "Group of three · hand in 5 Dec",
     "One spot in a group of three. You should be comfortable in Excel, the rest we work out "
     "together."),
    ("Noah B.",   "MGT3204", "Campaign brief, group work",    1, "Group of four · hand in 9 Dec",
     "One spot left. We meet on Wednesday afternoons, everything else is done on our own time."),
    ("Clara V.",  "BAN4305", "Pair assignment, exercise 3",   1, "Pair · hand in 21 Nov",
     "Looking for one partner for the pair assignment. I have started the first exercise already."),
    ("Sofia M.",  "BAN4301", "New group, no one picked yet",  2, "Group of four · hand in 12 Dec",
     "Starting a new group, two spots open. No preference on background, just show up."),
    ("Tiago R.",  "MGT3207", "Role play, need a partner",     1, "Pair · hand in 24 Nov",
     "Need one person for the negotiation role play. Half an hour of prep, that is all."),
    ("André C.",  "GEN1505", "Capstone, two seats left",      2, "Group of five · hand in 15 Dec",
     "Our capstone group lost two people. Topic is already agreed with the supervisor."),
    ("Lena K.",   "FIN2105", "Problem set, study group",      3, "Group of five · hand in 30 Nov",
     "Starting a study group for the weekly problem sets. We meet Mondays."),
    ("Mariana S.","FIN2103", "Pricing project, one spot",     1, "Group of four · hand in 8 Dec",
     "One spot in our group. You need to be fine with the Black Scholes part."),
]

# Something of mine that is already gone, so the profile shows both states.
CLOSED = ("Marco C.", "item", "Coffee machine, like new", 35, "Good condition · pick up on campus",
          "Small filter machine, used for one semester. Already taken, leaving it here for the record.")


def main():
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.setup()

    conn = db.connect()
    base = datetime.now(timezone.utc)

    def stamp(days_ago, hours=12, minutes=0):
        t = base - timedelta(days=days_ago)
        t = t.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        return t.isoformat(timespec="seconds")

    # db.setup() has imported the official course catalogue.
    # Use official course IDs rather than inventing additional courses.
    course_id = {}
    for old_code, official_code in DEMO_COURSE_IDS.items():
        row = conn.execute('SELECT id FROM courses WHERE code=?', (official_code,)).fetchone()
        if row is None:
            raise ValueError(f'Missing official course {official_code}')
        course_id[old_code] = row['id']

    # One hash for everyone, worked out once instead of ten times, because
    # the calculation is slow on purpose.
    demo_hash = passwords.hash_password(DEMO_PASSWORD)

    ids = {}
    for i, (email, name, programme, cems) in enumerate(STUDENTS):
        cur = conn.execute(
            "INSERT INTO users (email, name, programme, cems, password, verified,"
            " created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (email, name, programme, cems, demo_hash, stamp(60 - i)),
        )
        ids[name] = cur.lastrowid

    for student, codes in ENROLMENTS.items():
        for code in codes:
            conn.execute(
                "INSERT OR IGNORE INTO enrolments (user_id, course_id) VALUES (?, ?)",
                (ids[student], course_id[code]),
            )

    def add(owner, kind, title, price, info, description, category=None,
            event_date=None, event_time=None, place=None, address=None,
            quantity=None, course=None, days_ago=2, views=0, status="open"):
        cur = conn.execute(
            "INSERT INTO listings (owner_id, type, title, description, price, info,"
            " category, event_date, event_time, place, address, quantity,"
            " course_id, status, views, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ids[owner], kind, title, description, price, info, category,
             event_date, event_time, place, address, quantity,
             course_id[course] if course else None, status, views, stamp(days_ago)),
        )
        return cur.lastrowid

    listing = {}
    for n, (owner, title, price, info, text) in enumerate(HOUSING):
        listing[title] = add(owner, "housing", title, price, info, text,
                             days_ago=2 + n, views=31 - n * 3)
    for n, (owner, cat, date, at, place, title, price, many, text) in enumerate(TICKETS):
        listing[title] = add(owner, "ticket", title, price, "", text,
                             category=cat, event_date=date, event_time=at,
                             place=place, address=ADDRESSES.get(place),
                             quantity=many, days_ago=1 + (n % 6), views=24 - n)
    for n, (owner, title, price, info, text) in enumerate(MARKET):
        listing[title] = add(owner, "item", title, price, info, text,
                             days_ago=1 + n, views=24 - n * 2)
    for n, (owner, code, title, spots, info, text) in enumerate(GROUPS):
        listing[title] = add(owner, "group", title, None, info, text,
                             quantity=spots, course=code, days_ago=1 + n,
                             views=14 - n)

    owner, kind, title, price, info, text = CLOSED
    listing[title] = add(owner, kind, title, price, info, text, days_ago=9, views=40,
                         status="closed")

    # Conversations. Marco writes to three people, and two people write to Marco
    # about the same entry of his, which must stay two separate conversations.
    def talk(listing_title, starter, lines, days_ago=0, start_hour=14, read=True):
        conv = conn.execute(
            "INSERT INTO conversations (listing_id, starter_id, created_at) VALUES (?, ?, ?)",
            (listing[listing_title], ids[starter], stamp(days_ago, start_hour - 1)),
        ).lastrowid
        for n, (who, body) in enumerate(lines):
            last = n == len(lines) - 1
            conn.execute(
                "INSERT INTO messages (conversation_id, sender_id, body, created_at, read_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (conv, ids[who], body, stamp(days_ago, start_hour, n * 7),
                 None if (last and who != "Marco C." and not read) else stamp(days_ago, start_hour + 1)),
            )
        return conv

    talk("Room in a 3-bed flat", "Marco C.", [
        ("Marco C.",   "Hi Mariana! Is the room still free from February?"),
        ("Mariana S.", "Hi! Yes, from 1 Feb. Are you the one in MSc Finance?"),
        ("Marco C.",   "Yes, second semester. Could I come by this week to see it?"),
        ("Mariana S.", "Sure, Thursday after six? I will send the address."),
        ("Marco C.",   "Thursday works, thank you!"),
    ], days_ago=0, start_hour=14)

    talk("City bike", "Marco C.", [
        ("Marco C.", "Hi Sofia, is the bike still there?"),
        ("Sofia M.", "It is. Want to see it tomorrow?"),
        ("Marco C.", "Could you do 100 if I pick it up today?"),
    ], days_ago=0, start_hour=12, read=False)

    talk("Valuation assignment", "Marco C.", [
        ("Marco C.", "Hi João, is the spot in your group still open?"),
        ("João P.",  "Yes. How are you with Excel?"),
        ("Marco C.", "Fine with it, I did the modelling course last term."),
        ("João P.",  "Then come along. We meet Tuesday at six in the library."),
    ], days_ago=1, start_hour=17)

    talk("Final project, panel data", "Inês B.", [
        ("Inês B.",  "Hi Marco, I saw you still need one person. Is it taken?"),
        ("Marco C.", "Not yet. Have you done panel data before?"),
        ("Inês B.",  "A little, last semester. I can catch up quickly."),
    ], days_ago=1, start_hour=10, read=False)

    talk("Final project, panel data", "Noah B.", [
        ("Noah B.", "Hey, is the spot in the econometrics group free?"),
        ("Noah B.", "I am Erasmus, here until February."),
    ], days_ago=2, start_hour=16, read=False)

    courses_count = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    conn.commit()
    conn.close()

    print(f"database written to {db.DB_PATH}")
    print(f"{len(STUDENTS)} students, {courses_count} courses, "
          f"{len(HOUSING) + len(TICKETS) + len(MARKET) + len(GROUPS) + 1} entries, "
          f"5 conversations")
    print(f"you are {ME}, and every demo student's password is {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
