"""Fill the database with fake students and fake entries.

Run it with   python -m app.seed   from the project folder.
It wipes what is there and writes the demo content again, so you can always
get back to a clean state. Every person and every entry in here is invented.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from . import db

ME = "20241234@novasbe.pt"          # the student you are logged in as

STUDENTS = [
    (ME,                       "Marco C.",   "MSc Finance"),
    ("mariana.s@novasbe.pt",   "Mariana S.", "MSc Finance"),
    ("tiago.r@novasbe.pt",     "Tiago R.",   "MSc Management"),
    ("clara.v@novasbe.pt",     "Clara V.",   "MSc Finance"),
    ("sofia.m@novasbe.pt",     "Sofia M.",   "MSc Business Analytics"),
    ("andre.c@novasbe.pt",     "André C.",   "Alumni"),
    ("lena.k@novasbe.pt",      "Lena K.",    "MSc Finance"),
    ("ines.b@novasbe.pt",      "Inês B.",    "MSc Management"),
    ("joao.p@novasbe.pt",      "João P.",    "MSc Finance"),
    ("noah.b@novasbe.pt",      "Noah B.",    "Erasmus"),
]

# Every course on offer. Invented, but the sort of list a school really has,
# long enough that the Groups tab is useless without the filter.
COURSES = [
    ("FIN2101", "Corporate Finance",            "MSc Finance"),
    ("FIN2102", "Investments",                  "MSc Finance"),
    ("FIN2103", "Derivatives",                  "MSc Finance"),
    ("FIN2104", "Financial Modelling",          "MSc Finance"),
    ("FIN2105", "Fixed Income",                 "MSc Finance"),
    ("FIN2106", "Risk Management",              "MSc Finance"),
    ("FIN2107", "Private Equity",               "MSc Finance"),
    ("FIN2108", "Behavioural Finance",          "MSc Finance"),
    ("FIN2109", "Financial Statement Analysis", "MSc Finance"),
    ("FIN2110", "Mergers and Acquisitions",     "MSc Finance"),
    ("FIN2111", "Econometrics I",               "MSc Finance"),
    ("FIN2112", "Econometrics II",              "MSc Finance"),

    ("MGT3201", "Strategy",                     "MSc Management"),
    ("MGT3202", "Organisational Behaviour",     "MSc Management"),
    ("MGT3203", "Operations Management",        "MSc Management"),
    ("MGT3204", "Marketing Management",         "MSc Management"),
    ("MGT3205", "Leadership",                   "MSc Management"),
    ("MGT3206", "Business Law",                 "MSc Management"),
    ("MGT3207", "Negotiation",                  "MSc Management"),
    ("MGT3208", "Entrepreneurship",             "MSc Management"),
    ("MGT3209", "Supply Chain Management",      "MSc Management"),
    ("MGT3210", "Project Management",           "MSc Management"),

    ("BAN4301", "Machine Learning",             "MSc Business Analytics"),
    ("BAN4302", "Data Visualisation",           "MSc Business Analytics"),
    ("BAN4303", "Statistics for Business",      "MSc Business Analytics"),
    ("BAN4304", "Database Systems",             "MSc Business Analytics"),
    ("BAN4305", "Introduction to Programming",  "MSc Business Analytics"),
    ("BAN4306", "Big Data Tools",               "MSc Business Analytics"),
    ("BAN4307", "Forecasting",                  "MSc Business Analytics"),
    ("BAN4308", "Optimisation",                 "MSc Business Analytics"),
    ("BAN4309", "Text Analytics",               "MSc Business Analytics"),
    ("BAN4310", "Deep Learning",                "MSc Business Analytics"),

    ("ECO5401", "Microeconomics",               "MSc Economics"),
    ("ECO5402", "Macroeconomics",               "MSc Economics"),
    ("ECO5403", "Development Economics",        "MSc Economics"),
    ("ECO5404", "Labour Economics",             "MSc Economics"),
    ("ECO5405", "International Trade",          "MSc Economics"),
    ("ECO5406", "Public Finance",               "MSc Economics"),
    ("ECO5407", "Game Theory",                  "MSc Economics"),
    ("ECO5408", "Monetary Economics",           "MSc Economics"),

    ("GEN1501", "Business Ethics",              "Open to all"),
    ("GEN1502", "Sustainability",               "Open to all"),
    ("GEN1503", "Academic Writing",             "Open to all"),
    ("GEN1504", "Portuguese for Beginners",     "Open to all"),
    ("GEN1505", "Capstone Project",             "Open to all"),
    ("GEN1506", "Consulting Lab",               "Open to all"),
]

# Who is taking what. You are in five, which is why the Groups tab is short.
ENROLMENTS = {
    "Marco C.":   ["FIN2111", "FIN2104", "BAN4305", "FIN2101", "FIN2102"],
    "Mariana S.": ["FIN2111", "FIN2103", "FIN2109", "GEN1501"],
    "Tiago R.":   ["MGT3201", "MGT3204", "MGT3207", "GEN1502"],
    "Clara V.":   ["BAN4305", "FIN2102", "FIN2106", "GEN1503"],
    "Sofia M.":   ["BAN4301", "BAN4302", "BAN4307", "FIN2104"],
    "André C.":   ["GEN1505", "MGT3208"],
    "Lena K.":    ["FIN2101", "FIN2105", "FIN2111", "GEN1504"],
    "Inês B.":    ["MGT3201", "MGT3202", "MGT3205", "FIN2111"],
    "João P.":    ["FIN2104", "FIN2110", "ECO5407", "FIN2101"],
    "Noah B.":    ["MGT3204", "ECO5403", "GEN1504", "GEN1506"],
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

TICKETS = [
    ("Tiago R.",   "Sunset rooftop party",       15, "2 available · face value €20", "2026-11-20",
     "Two tickets left for the rooftop party. I paid twenty each, happy to pass them on for "
     "fifteen. Transfer by app, I send them the same day."),
    ("Clara V.",   "Student night, Urban Beach", 12, "1 available · entry before 1am", "2026-11-21",
     "One spare ticket. Entry only before one in the morning, after that the ticket is dead."),
    ("Sofia M.",   "Finance Ball, seated table", 45, "1 available · table of eight", "2026-11-27",
     "One seat at our table of eight. Dinner included, drinks are not."),
    ("Lena K.",    "Padel tournament, day pass", None, "3 available · Saturday morning", "2026-11-28",
     "Three day passes going free, we signed up and cannot make it. First to write gets them."),
    ("André C.",   "Football, upper tier",       38, "2 available · seats together", "2026-11-29",
     "Two seats next to each other in the upper tier. Printed tickets, I hand them over on campus."),
    ("Mariana S.", "Half marathon bib",          25, "1 available · transfer by 5 Dec", "2026-12-06",
     "My bib for the half marathon. The transfer has to go through before the fifth of December."),
]

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

# Owner, course, title, spots, grey line, description.
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

    course_id = {}
    for code, name, programme in COURSES:
        cur = conn.execute(
            "INSERT INTO courses (code, name, programme) VALUES (?, ?, ?)",
            (code, name, programme),
        )
        course_id[code] = cur.lastrowid

    ids = {}
    for i, (email, name, course) in enumerate(STUDENTS):
        cur = conn.execute(
            "INSERT INTO users (email, name, course, verified, created_at)"
            " VALUES (?, ?, ?, 1, ?)",
            (email, name, course, stamp(60 - i)),
        )
        ids[name] = cur.lastrowid

    for student, codes in ENROLMENTS.items():
        for code in codes:
            conn.execute(
                "INSERT INTO enrolments (user_id, course_id) VALUES (?, ?)",
                (ids[student], course_id[code]),
            )

    def add(owner, kind, title, price, info, description, event_date=None,
            spots=None, course=None, days_ago=2, views=0, status="open"):
        cur = conn.execute(
            "INSERT INTO listings (owner_id, type, title, description, price, info,"
            " event_date, spots, course_id, status, views, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ids[owner], kind, title, description, price, info, event_date, spots,
             course_id[course] if course else None, status, views, stamp(days_ago)),
        )
        return cur.lastrowid

    listing = {}
    for n, (owner, title, price, info, text) in enumerate(HOUSING):
        listing[title] = add(owner, "housing", title, price, info, text,
                             days_ago=2 + n, views=31 - n * 3)
    for n, (owner, title, price, info, date, text) in enumerate(TICKETS):
        listing[title] = add(owner, "ticket", title, price, info, text,
                             event_date=date, days_ago=1 + n, views=18 - n)
    for n, (owner, title, price, info, text) in enumerate(MARKET):
        listing[title] = add(owner, "item", title, price, info, text,
                             days_ago=1 + n, views=24 - n * 2)
    for n, (owner, code, title, spots, info, text) in enumerate(GROUPS):
        listing[title] = add(owner, "group", title, None, info, text, spots=spots,
                             course=code, days_ago=1 + n, views=14 - n)

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

    conn.commit()
    conn.close()

    print(f"database written to {db.DB_PATH}")
    print(f"{len(STUDENTS)} students, {len(COURSES)} courses, "
          f"{len(HOUSING) + len(TICKETS) + len(MARKET) + len(GROUPS) + 1} entries, "
          f"5 conversations")
    print(f"you are {ME}")


if __name__ == "__main__":
    main()
