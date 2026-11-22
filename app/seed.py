"""Fill the database with fake students and fake entries.

Run it with   python -m app.seed   from the project folder.
It wipes what is there and writes the demo content again, so you can always
get back to a clean state. Every person and every entry in here is invented.
"""

import os
import shutil
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

# Owner, title, kind, area, rent, bills included, bills estimate, deposit in
# months, free from, minimum stay, minutes to campus, flatmates, what it has,
# address, description. Everything a place is searched by is a field, so the
# description only carries what a person would actually say out loud.
HOUSING = [
    ("Noah B.",    "Cheap room, Lisboa centre", "shared_flat", "lisboa",
     420, 0, 50, 1, "2026-12-01", 4, 55, 4,
     "furnished,own_room,wifi,washing_machine", "R. da Madalena 61",
     "Small room in a big old flat near Martim Moniz. Four of us, three "
     "studying, one working. Cheap, lively, and a long way from campus."),
    ("João P.",    "Studio with parking", "studio", "oeiras",
     690, 1, None, 2, "2027-01-01", 12, 28, 0,
     "furnished,own_bathroom,own_room,desk,wifi,washing_machine,parking,air_conditioning",
     "Rua Alto da Loba 5",
     "My studio while I am away for the year. Everything stays, including "
     "the car space downstairs. Quiet building, mostly families."),
    ("Clara V.",   "Single room, short term", "shared_flat", "oeiras",
     430, 0, 45, 1, "2027-01-05", 3, 25, 3,
     "furnished,own_room,wifi,washing_machine", "Rua Cândido dos Reis 9",
     "Single room for the winter term only. Good if you are here for one "
     "semester and do not want to sign for a year."),
    ("Lena K.",    "Room in Parede, near the train", "shared_flat", "parede",
     450, 0, None, 1, "2027-03-28", None, 12, 2,
     "own_room,wifi,washing_machine,dishwasher", "Parede",
     "Single room in a big flat in Parede, a few minutes from the train. "
     "Non smokers only. The full advert with all the photos is on "
     "Imovirtual, the button below opens it."),
    ("Mariana S.", "Room in a 3-bed flat", "shared_flat", "carcavelos",
     600, 1, None, 1, "2027-02-01", 1, 10, 2,
     "furnished,own_room,desk,wifi,washing_machine,pets",
     "Rua Flora, Carcavelos",
     "Double room in a three bedroom house, ten minutes on foot to Nova and "
     "to the beach. Water, power, gas and internet are in the rent. More "
     "photos on Uniplaces, the button below opens the advert."),
    ("Tiago R.",   "Studio sublet, Feb to June", "studio", "carcavelos",
     720, 1, None, 1, "2027-02-01", 4, 10, 0,
     "furnished,own_bathroom,own_room,desk,wifi,washing_machine,air_conditioning",
     "Av. Jorge V 22",
     "My own studio, free while I am on exchange. Everything stays in it, "
     "you only bring clothes. Bills and internet are in the price."),
    ("André C.",   "Room with balcony, long stay", "shared_flat", "sao_pedro",
     560, 0, 60, 1, "2027-02-01", 12, 22, 3,
     "furnished,own_room,desk,wifi,washing_machine,balcony", "Av. Marginal 118",
     "Large room with its own balcony facing the sea. Twelve month contract "
     "only, the landlord does not do shorter."),
    ("Inês B.",    "Room in Cascais, sea view", "shared_flat", "cascais",
     620, 0, 70, 2, "2027-02-15", 6, 35, 1,
     "furnished,own_room,own_bathroom,desk,wifi,washing_machine,dishwasher,balcony",
     "Rua Frederico Arouca 44",
     "One flatmate, also Nova, very quiet. The flat is above the old town, "
     "five minutes from the beach and a train ride from campus."),
    ("Sofia M.",   "Whole T3, looking for flatmates", "whole_flat", "carcavelos",
     1500, 0, None, None, "2027-01-01", None, 15, 0,
     "balcony", "Rua das Amoras 271",
     "I found this renovated T3 on Idealista and want to rent it with two "
     "other Nova students, so about 500 each. Third floor with a lift, a "
     "balcony, viewings from 1 December. Full advert behind the button."),
    ("Mariana S.", "Room, pets welcome", "shared_flat", "parede",
     455, 0, 50, 1, "2027-03-01", 6, 12, 2,
     "furnished,own_room,wifi,washing_machine,balcony,pets", "Rua do Moinho 12",
     "The one flat around here that says yes to a cat. Two flatmates, both "
     "fine with it, and there is a balcony she can sit on."),
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

# Owner, title, price, category, condition, grey line, description.
# The grey line no longer repeats the condition, that is a field of its own.
# The order is the order they went up, newest first, which is what decides
# what lands in the row at the top of the tab.
MARKET = [
    ("Mariana S.", "iPad Air, 11 inch",               290, "electronics", "like_new",
     "with the pencil and the charger",
     "Two years old, always in a case. Comes with the pencil and the charger. Battery still "
     "holds a full day."),
    ("Lena K.",    "Desk and chair",                   45, "furniture",   "used",
     "pick up in Carcavelos",
     "Simple desk and an office chair. Both work fine, the desk has a scratch on the top. "
     "Pick up only, I cannot deliver."),
    ("Clara V.",   "Finance textbooks, bundle",        30, "books",       "used",
     "three books together",
     "Three books from last year, Corporate Finance, Investments and Derivatives. Barely "
     "written in."),
    ("Tiago R.",   "Surfboard, 7 foot",               150, "sports",      "used",
     "beginner board, soft top",
     "Seven foot soft top, the board I learned on. A few dings on the nose, all sealed. "
     "Carcavelos is a five minute walk, you can try it first."),
    ("Inês B.",    "Winter coat, size M",              25, "clothes",     "used",
     "worn one season",
     "Warm winter coat, size M, worn for one season only. Washed and ready."),
    ("Lena K.",    "Statistics lecture notes, printed", None, "books",    "used",
     "two folders, whole course",
     "My printed notes for the whole statistics course, in two folders. Giving them away, "
     "I am done with the exam."),
    ("Sofia M.",   "City bike",                       120, "sports",      "used",
     "lock and lights included",
     "City bike, seven gears, serviced last month. Lock and both lights are included."),
    ("Marco C.",   "Monitor, 27 inch",                 95, "electronics", "used",
     "no dead pixels",
     "27 inch monitor, 1440p. No dead pixels, no scratches. Stand and cable included."),
    ("João P.",    "Bookshelf, white",                 20, "furniture",   "used",
     "I can help carry it",
     "White shelf, five shelves, from the flat I am leaving. I can help carry it down if "
     "you come with a car."),
    ("Noah B.",    "Wetsuit, size M",                  55, "sports",      "like_new",
     "worn five times",
     "Three two wetsuit, size M, bought in September and worn maybe five times. No tears."),
    ("André C.",   "Headphones, noise cancelling",     60, "electronics", "like_new",
     "case and cable included",
     "Over ear, noise cancelling. Barely used since I started working from the office. "
     "Case and cable are with them."),
    ("Mariana S.", "Desk lamp with USB",                8, "furniture",   "used",
     "warm light",
     "Small desk lamp with a USB socket in the base. Warm light, works fine."),
    ("Tiago R.",   "Suit, size 48, navy",              70, "clothes",     "like_new",
     "worn twice, for interviews",
     "Navy suit, size 48, worn twice for interviews. Dry cleaned and in the bag."),
    ("Clara V.",   "Corporate Finance, 4th edition",   18, "books",       "like_new",
     "nothing written in it",
     "The edition the course uses. I read it on the screen in the end, so there is nothing "
     "written in this one."),
    ("Sofia M.",   "Mattress, 90x200",                None, "furniture",  "used",
     "clean, with a cover",
     "Single mattress, 90 by 200, with a washed cover. Giving it away, I leave in December."),
    ("Noah B.",    "Kettle and toaster",              None, "other",      "well_used",
     "both work",
     "Kettle and toaster from my kitchen. Both work, both look their age. Free, I just "
     "cannot take them home."),
]

# Owner, course, title, free spots, grey line, description.
# Three of these are in a course you take, the rest are not. That difference is
# the whole point of the Groups tab.
# Owner, course, title, spots free, group size, hand in, grey line, text.
# The hand in date and the size are real fields now, so the grey line only
# carries the bit a person actually wrote. Three of these sit in a course
# Marco takes, which is what makes the course headings in the tab worth
# having.
GROUPS = [
    ("Marco C.",  "FIN2111", "Final project, panel data",    1, 4, "2026-11-28",
     "We meet twice a week in the library",
     "We are three and need one more for the final project. Panel data, we already have the "
     "dataset. We meet twice a week in the library."),
    ("Clara V.",  "FIN2111", "Panel data, second group",     2, 4, "2026-12-01",
     "Thursdays, online",
     "Second group for the same project. Two of us so far, we work Thursday evenings over a "
     "call. Bring your own laptop and that is it."),
    ("João P.",   "FIN2111", "Econometrics, need two",       2, 5, "2026-11-28",
     "Stata or R, either is fine",
     "Three of us, two places open. Half the group uses Stata and half uses R, nobody minds."),
    ("João P.",   "FIN2104", "Valuation assignment",         1, 3, "2026-12-05",
     "Excel heavy",
     "One spot in a group of three. You should be comfortable in Excel, the rest we work out "
     "together."),
    ("Lena K.",   "FIN2104", "Modelling case, one spot",     1, 3, "2026-12-05",
     "We split the model in three",
     "One spot left. We split the model in three parts and put it together on the last "
     "weekend."),
    ("Clara V.",  "BAN4305", "Pair assignment, exercise 3",  1, 2, "2026-11-21",
     "First exercise already started",
     "Looking for one partner for the pair assignment. I have started the first exercise already."),
    ("Inês B.",   "MGT3201", "Case study, group of five",    2, 5, "2026-12-02",
     "Case already picked",
     "Two spots left in our group of five. The case is already picked, we split the sections "
     "evenly."),
    ("Noah B.",   "MGT3204", "Campaign brief, group work",   1, 4, "2026-12-09",
     "Wednesday afternoons",
     "One spot left. We meet on Wednesday afternoons, everything else is done on our own time."),
    ("Sofia M.",  "BAN4301", "New group, no one picked yet", 2, 4, "2026-12-12",
     "No preference on background",
     "Starting a new group, two spots open. No preference on background, just show up."),
    ("Tiago R.",  "MGT3207", "Role play, need a partner",    1, 2, "2026-11-24",
     "Half an hour of prep",
     "Need one person for the negotiation role play. Half an hour of prep, that is all."),
    ("André C.",  "GEN1505", "Capstone, two seats left",     2, 5, "2026-12-15",
     "Topic agreed with the supervisor",
     "Our capstone group lost two people. Topic is already agreed with the supervisor."),
    ("Lena K.",   "FIN2105", "Problem set, study group",     3, 5, "2026-11-30",
     "We meet Mondays",
     "Starting a study group for the weekly problem sets. We meet Mondays."),
    ("Mariana S.","FIN2103", "Pricing project, one spot",    1, 4, "2026-12-08",
     "Black Scholes part included",
     "One spot in our group. You need to be fine with the Black Scholes part."),
]


# Something of mine that is already gone, so the profile shows both states.
CLOSED = ("Marco C.", "item", "Coffee machine, like new", 35, "pick up on campus",
          "Small filter machine, used for one semester. Already taken, leaving it here for the record.")

# A few hearts, so the number on an entry and the Saved list on a profile are
# not empty in the demo. Nobody saves their own entry, there is no button for
# it. Student, then what they saved.
SAVES = [
    ("Marco C.",  ["Surfboard, 7 foot", "Jazz at the Coliseu", "Room in a 3-bed flat"]),
    ("Lena K.",   ["Surfboard, 7 foot", "iPad Air, 11 inch"]),
    ("Tiago R.",  ["iPad Air, 11 inch"]),
    ("Sofia M.",  ["Surfboard, 7 foot"]),
    ("João P.",   ["iPad Air, 11 inch"]),
    ("Clara V.",  ["Statistics lecture notes, printed"]),
]


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
            condition=None, event_date=None, event_time=None, place=None,
            address=None, quantity=None, course=None, hand_in=None,
            group_size=None, available_from=None, months_min=None,
            bills_included=None, bills_estimate=None, deposit=None,
            minutes_campus=None, flatmates=None, features=None,
            days_ago=2, views=0, status="open"):
        cur = conn.execute(
            "INSERT INTO listings (owner_id, type, title, description, price, info,"
            " category, condition, event_date, event_time, place, address, quantity,"
            " course_id, hand_in, group_size, available_from, months_min,"
            " bills_included, bills_estimate, deposit, minutes_campus,"
            " flatmates, features, status, views, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " ?, ?, ?, ?, ?, ?, ?, ?)",
            (ids[owner], kind, title, description, price, info, category, condition,
             event_date, event_time, place, address, quantity,
             course_id[course] if course else None, hand_in, group_size,
             available_from, months_min, bills_included, bills_estimate,
             deposit, minutes_campus, flatmates, features,
             status, views, stamp(days_ago)),
        )
        return cur.lastrowid

    listing = {}
    for n, (owner, title, kind, area, rent, allin, bills, dep, free, least,
            mins, mates, has, where, text) in enumerate(HOUSING):
        listing[title] = add(owner, "housing", title, rent, "", text,
                             category=kind, place=area, address=where,
                             available_from=free, months_min=least,
                             bills_included=allin, bills_estimate=bills,
                             # The table above says the deposit in months,
                             # which is how anybody writing it thinks of it.
                             # The column holds the sum, so it is worked out
                             # here rather than stored twice.
                             deposit=(rent * dep if dep is not None else None), minutes_campus=mins,
                             flatmates=mates, features=has,
                             days_ago=2 + n, views=34 - n * 3)
    # Three places are real adverts on housing sites (checked 18 Nov 2026),
    # so the button on the entry opens the actual advert. The details of the
    # entry match the advert. Adverts do come down when a place is let: check
    # the three links before a demo and swap in a live advert if one is gone.
    ELSEWHERE = {
        "Room in a 3-bed flat":
            "https://www.uniplaces.com/accommodation/lisbon/635692",
        "Whole T3, looking for flatmates":
            "https://www.idealista.pt/en/imovel/35486802/",
        "Room in Parede, near the train":
            "https://www.imovirtual.com/pt/anuncio/quarto-localizado-em-carcavelos-lisbon-ID1hsY5",
    }
    for title, url in ELSEWHERE.items():
        conn.execute("UPDATE listings SET external_url = ? WHERE id = ?",
                     (url, listing[title]))

    # Real photos for the rooms that are not linked to an advert. They are
    # free photos from Unsplash (see static/demo/CREDITS.md), kept in git in
    # static/demo and copied into the uploads folder, which git ignores. The
    # three linked rooms keep their drawing: a stock photo there would show a
    # different flat from the real advert behind the button.
    # Some places have several photos, to show the gallery on the entry.
    PHOTOS = {
        "Cheap room, Lisboa centre": ["room-lisboa.jpg"],
        "Studio with parking": ["studio-oeiras.jpg"],
        "Single room, short term": ["room-short-term.jpg"],
        "Studio sublet, Feb to June": ["studio-sublet.jpg", "studio-sublet-2.jpg"],
        "Room with balcony, long stay": ["room-balcony.jpg"],
        "Room in Cascais, sea view": ["room-cascais.jpg"],
        "Room, pets welcome": ["room-pets.jpg", "room-pets-2.jpg", "room-pets-3.jpg"],
    }
    here = os.path.dirname(os.path.abspath(__file__))
    uploads = os.path.join(here, "static", "uploads")
    os.makedirs(uploads, exist_ok=True)
    for title, names in PHOTOS.items():
        for position, name in enumerate(names):
            shutil.copyfile(os.path.join(here, "static", "demo", name),
                            os.path.join(uploads, "demo-" + name))
            conn.execute("INSERT INTO photos (listing_id, filename, position)"
                         " VALUES (?, ?, ?)", (listing[title], "demo-" + name, position))

    for n, (owner, cat, date, at, place, title, price, many, text) in enumerate(TICKETS):
        listing[title] = add(owner, "ticket", title, price, "", text,
                             category=cat, event_date=date, event_time=at,
                             place=place, address=ADDRESSES.get(place),
                             quantity=many, days_ago=1 + (n % 6), views=24 - n)
    for n, (owner, title, price, cat, worn, info, text) in enumerate(MARKET):
        listing[title] = add(owner, "item", title, price, info, text,
                             category=cat, condition=worn,
                             days_ago=1 + n, views=26 - n)
    for n, (owner, code, title, spots, size, due, info, text) in enumerate(GROUPS):
        listing[title] = add(owner, "group", title, None, info, text,
                             quantity=spots, course=code, hand_in=due,
                             group_size=size, days_ago=1 + n, views=22 - n)

    owner, kind, title, price, info, text = CLOSED
    listing[title] = add(owner, kind, title, price, info, text, category="other",
                         condition="like_new", days_ago=9, views=40,
                         status="closed")

    for n, (student, titles) in enumerate(SAVES):
        for m, what in enumerate(titles):
            conn.execute(
                "INSERT OR IGNORE INTO saves (user_id, listing_id, created_at)"
                " VALUES (?, ?, ?)",
                (ids[student], listing[what], stamp(n, 9 + m)),
            )

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
          f"5 conversations, {sum(len(t) for _, t in SAVES)} hearts")
    print(f"you are {ME}, and every demo student's password is {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
