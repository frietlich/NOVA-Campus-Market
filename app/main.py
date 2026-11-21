"""Campus Market, the web app.

Every page lives here. The database is only reached through db.py.
Start it with   uvicorn app.main:app --reload   from the project folder.
"""

import os
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import quote, urlencode, urlparse

from fastapi import FastAPI, Form, Query, Request, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import categories, db, housing, mailer, passwords, programmes

# .env first, so CAMPUS_SECRET and the mail account can live in it.
mailer.load_env()

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(HERE, "static", "uploads")
SECRET = os.environ.get("CAMPUS_SECRET") or "change-me-before-you-deploy"

# The four tabs. Everything about a tab is in this one list.
TABS = [
    {"kind": "housing", "label": "Housing", "path": "/housing",
     "placeholder": "Carcavelos, from January"},
    {"kind": "ticket", "label": "Tickets", "path": "/tickets",
     "placeholder": "Party, football, concert"},
    {"kind": "item", "label": "Market", "path": "/market",
     "placeholder": "Bike, desk, textbooks"},
    {"kind": "group", "label": "Groups", "path": "/groups",
     "placeholder": "Course or date"},
]
BY_KIND = {t["kind"]: t for t in TABS}

# What the Sort button on Market offers. The key is what stands in the
# address, db.py turns it into the order the rows come back in.
SORT_OPTIONS = [
    ("",     "Newest",            "Newest"),
    ("low",  "Price low to high", "Price low"),
    ("high", "Price high to low", "Price high"),
]
SORT_KEYS = {key for key, _, _ in SORT_OPTIONS}
SORT_SHORT = {key: short for key, _, short in SORT_OPTIONS}

# The price filter, in steps. Two number fields is something nobody fills in
# on a phone. Key, what the button says, floor, ceiling. Free is a step like
# any other rather than a switch standing next to them.
PRICE_BANDS = [
    ("",     "Any price", None, None),
    ("free", "Free only", None, None),
    ("10",   "Under 10",  None, 10),
    ("25",   "Under 25",  None, 25),
    ("50",   "Under 50",  None, 50),
    ("50+",  "50 and up", 50,   None),
]
BY_BAND = {band[0]: band for band in PRICE_BANDS}

# How long something counts as new, and how many of them the row holds.
FRESH_DAYS = 7
FRESH_MAX = 10

app = FastAPI(title="Campus Market")
app.add_middleware(SessionMiddleware, secret_key=SECRET, max_age=60 * 60 * 24 * 30)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))


@app.on_event("startup")
def start():
    db.setup()
    os.makedirs(UPLOADS, exist_ok=True)


# ------------------------------------------------------------ small helpers

def initials(name):
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def money(value):
    if value is None:
        return ""
    value = float(value)
    whole = int(round(value))
    return "€" + format(whole, ",")


def when(iso):
    """14:32 today, Yesterday before that, then 12 Nov.

    The day is put in by hand rather than with %-d. That flag strips the
    leading zero on a Mac and on Linux, and on Windows it is not a format at
    all, strftime throws and the page dies. This is the same trick in all
    four places below.
    """
    if not iso:
        return ""
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    t = t.astimezone()
    today = datetime.now().astimezone().date()
    days = (today - t.date()).days
    if days <= 0:
        return t.strftime("%H:%M")
    if days == 1:
        return "Yesterday"
    return f"{t.day} {t:%b}"


def month(iso):
    """Nov 26, for the joined stat on the profile."""
    if not iso:
        return ""
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone().strftime("%b %y")


def ago(iso):
    if not iso:
        return ""
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - t).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def event_badge(iso_date):
    """The little square on a ticket card, FRI / 20 / NOV."""
    if not iso_date:
        return None
    d = datetime.strptime(iso_date, "%Y-%m-%d")
    return {"weekday": d.strftime("%a").upper(), "day": str(d.day),
            "month": d.strftime("%b").upper()}


def day_label(iso_date):
    """FRIDAY 20 NOV for a heading, and TODAY or TOMORROW when it is close."""
    if not iso_date:
        return "NO DATE"
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    today = datetime.now().astimezone().date()
    if d == today:
        return "Today"
    if (d - today).days == 1:
        return "Tomorrow"
    return f"{d:%A} {d.day} {d:%B}"


def short_date(iso_date):
    """Tue 2 Dec, the line at the top of a group notice."""
    if not iso_date:
        return ""
    d = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{d:%a} {d.day} {d:%b}"


def day_month(iso_date):
    """15 Jan, for a move in date where the weekday says nothing."""
    if not iso_date:
        return ""
    d = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{d.day} {d:%b}"


def days_left(iso_date):
    """last day, 1 day left, 16 days left, or overdue once the day is past.

    One day says tomorrow in plain speech, but next to 2 days left and 16
    days left it reads as a different kind of fact and the eye stops. The
    count is the same word every time so a column of them can be scanned.

    The last day is not "today" either, for the same reason and one more:
    the notice puts "to join" after this, and last day to join says what
    happens, while today to join says only when.
    """
    if not iso_date:
        return ""
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    gap = (d - datetime.now().astimezone().date()).days
    if gap < 0:
        return "overdue"
    if gap == 0:
        return "last day"
    return f"{gap} day{'' if gap == 1 else 's'} left"


def pretty_date(iso_date):
    if not iso_date:
        return ""
    d = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{d.day} {d:%b %Y}"


def programme_label(name, cems=False):
    """Master in Management · CEMS, for a profile line."""
    return programmes.label(name, bool(cems))


templates.env.filters["initials"] = initials
templates.env.filters["short"] = programmes.short
templates.env.filters["programme"] = programme_label
templates.env.filters["money"] = money
templates.env.filters["when"] = when
templates.env.filters["month"] = month
templates.env.filters["ago"] = ago
templates.env.globals["event_badge"] = event_badge
templates.env.filters["day_label"] = day_label
templates.env.filters["short_date"] = short_date
templates.env.filters["day_month"] = day_month
templates.env.filters["days_left"] = days_left
templates.env.filters["category"] = categories.label
templates.env.filters["condition"] = categories.condition_label
templates.env.globals["pretty_date"] = pretty_date
templates.env.filters["pretty_date"] = pretty_date
def asset(path):
    """static/css/app.css?v=1763... so the browser never serves an old file.

    The number is the time the file was last saved. Change the file, the
    number changes, the browser fetches it again.
    """
    try:
        stamp = int(os.path.getmtime(os.path.join(HERE, "static", path)))
    except OSError:
        stamp = 0
    return f"/static/{path}?v={stamp}"


templates.env.globals["asset"] = asset
templates.env.globals["TABS"] = TABS
# The order the tabs stand in, so a page knows which one the capsule under
# the bar belongs on without counting the loop again.
templates.env.globals["TAB_ORDER"] = [t["kind"] for t in TABS] + ["chats"]
templates.env.globals["PROGRAMME_GROUPS"] = programmes.GROUPS
templates.env.globals["CEMS"] = programmes.CEMS
templates.env.globals["PASSWORD_RULES"] = passwords.RULES
templates.env.globals["NAME_MAX"] = db.NAME_MAX
templates.env.globals["EMAIL_MAX"] = db.EMAIL_LENGTH
templates.env.globals["EMAIL_DIGITS"] = db.EMAIL_DIGITS
templates.env.globals["EMAIL_PATTERN"] = db.EMAIL_PATTERN
templates.env.globals["EMAIL_DOMAIN"] = db.EMAIL_DOMAIN
templates.env.globals["CATEGORIES_FOR"] = categories.FOR_KIND
templates.env.globals["CONDITIONS"] = categories.CONDITION
templates.env.globals["CONDITION_LABELS"] = categories.CONDITION_LABELS
templates.env.globals["CATEGORY_LABELS"] = categories.LABELS
templates.env.globals["SORT_OPTIONS"] = SORT_OPTIONS
templates.env.globals["SORT_SHORT"] = SORT_SHORT
templates.env.globals["PRICE_BANDS"] = PRICE_BANDS
templates.env.globals["HOUSING"] = housing


def ordinal(n):
    """1st, 2nd, 3rd, 4th, and 11th, 12th, 13th the English way."""
    n = int(n)
    if 10 <= n % 100 <= 20:
        end = "th"
    else:
        end = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{end}"


templates.env.filters["ordinal"] = ordinal
templates.env.globals["PRICE_SHORT"] = {key: name for key, name, _, _ in PRICE_BANDS}


def as_utc(iso):
    """A stored time as something you can compare with now."""
    t = datetime.fromisoformat(iso)
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def fresh_rows(rows):
    """The ones put up in the last week, newest first.

    Market has no deadline the way Tickets has, so the only thing worth
    lifting out of the list is what is new. These are the same entries as in
    the list below, shown once more as a row you swipe along.
    """
    cut = datetime.now(timezone.utc) - timedelta(days=FRESH_DAYS)
    new = [r for r in rows if r["created_at"] and as_utc(r["created_at"]) >= cut]
    new.sort(key=lambda r: r["created_at"], reverse=True)
    return new[:FRESH_MAX]


# The tear off tabs under a group notice. The row holds between five and
# seven of them whatever the group really is, because fewer looks broken and
# more looks like a comb. The true numbers are printed on the paper anyway.
# A group notice always has five tabs along the bottom, whatever size the
# group is. The hanging ones are the spots still free and the rest are drawn
# already torn off, so a notice with one spot left looks like a notice late
# in the day. More than five free still shows five, because what the picture
# says is that there is room, not exactly how much.
# Nobody hands in group work in a crowd, and a title that long is a
# description. Both are here so the form and the check cannot drift apart.
GROUP_MAX = 20
TITLE_MAX = 60

# How long a description may be, per tab. A group says what the work is and
# when you meet, a thing for sale may need to list what is wrong with it, so
# it gets more room. A tab that is not in here is not limited yet.
DESC_MAX = {"group": 500, "item": 750, "ticket": 500, "housing": 1000}

# What the housing form will take. Every one of these is also checked on
# the way in, because the boxes only hold back a browser.
MONTHS_MAX = 36        # three years, longer than any exchange
MINUTES_MAX = 180      # three hours door to campus is already absurd
FLATMATES_MAX = 20
BILLS_MAX = 1000       # a deposit needs no ceiling of its own, the price
                       # check already stops anything over ten thousand

# The venue and the street, which only tickets ask for. A venue is a name
# people say out loud, an address is a line off a ticket, so one is short
# and the other is not.
PLACE_MAX = 60
ADDRESS_MAX = 120

# Nobody is holding more than fifty tickets to one thing, and a number
# somebody mistyped should not turn an entry into a wholesale stand.
TICKET_MAX = 50


def today_iso():
    """Today where the school is, for a date box that cannot go backwards."""
    return datetime.now().astimezone().date().isoformat()

# What a price may be. The shape is what stops a word, a minus sign or
# 1e9 from ever reaching float(), which used to take the whole page down.
# One or two decimals, a comma or a dot, nothing else, no sign.
PRICE_MAX = 10000
PRICE_SHAPE = re.compile(r"\d{1,6}([.,]\d{1,2})?")


def clean_price(text):
    """A price somebody typed, as a number, or a sentence saying what is wrong.

    Nothing typed is not a mistake. On a thing for sale it means free, and
    the form says so under the field.
    """
    text = (text or "").strip()
    if not text:
        return None, None
    if not PRICE_SHAPE.fullmatch(text):
        return None, "A price is a plain number, like 25 or 12.50."
    value = float(text.replace(",", "."))
    if value > PRICE_MAX:
        return None, f"A price can be at most {PRICE_MAX:,} euros."
    return value, None


# The form draws its own maxlength from the same three numbers the checks
# above use, so the box and the rule can never drift apart.
templates.env.globals["TITLE_MAX"] = TITLE_MAX
templates.env.globals["DESC_MAX"] = DESC_MAX
templates.env.globals["PRICE_MAX"] = PRICE_MAX
templates.env.globals["PLACE_MAX"] = PLACE_MAX
templates.env.globals["ADDRESS_MAX"] = ADDRESS_MAX
templates.env.globals["TICKET_MAX"] = TICKET_MAX
templates.env.globals["MONTHS_MAX"] = MONTHS_MAX
templates.env.globals["MINUTES_MAX"] = MINUTES_MAX
templates.env.globals["FLATMATES_MAX"] = FLATMATES_MAX
templates.env.globals["today_iso"] = today_iso

TEAR_TABS = 5
TEAR_SHAPES = 6


def tear_tabs(listing):
    """One entry per tab at the bottom of a group notice.

    A hanging tab is a spot still free, a torn one is a spot somebody already
    took. The shape number picks one of six ragged edges and comes from the
    id of the entry, so the same notice always tears the same way and two
    notices next to each other do not.
    """
    hanging = max(0, min(listing["quantity"] or 0, TEAR_TABS))
    return [{"hanging": n >= TEAR_TABS - hanging,
             "shape": (listing["id"] + n) % TEAR_SHAPES}
            for n in range(TEAR_TABS)]


def by_course(rows):
    """Turn a flat list of group entries into one block per course.

    Groups has no date to read it by and no categories. The course is what
    you are looking for, so two entries for the same course belong under one
    heading.

    The blocks are then put in order of how soon their next deadline is, and
    not by the name of the course. In group work the date is the whole point,
    and sorting by name buried a thing due in two days under a course that
    happens to start with an F. A course whose dates have all passed sinks to
    the bottom, because nobody can join those any more.
    """
    far = "9999"
    blocks, seen = [], {}
    for row in rows:
        name = row["course_name"] or "No course"
        block = seen.get(name)
        if block is None:
            block = seen[name] = {"head": name, "rows": []}
            blocks.append(block)
        block["rows"].append(row)

    today = datetime.now().astimezone().date().isoformat()
    def gone(row):
        return bool(row["hand_in"]) and row["hand_in"] < today

    for block in blocks:
        block["rows"].sort(key=lambda r: (gone(r), r["hand_in"] or far, r["id"]))
        soon = [r["hand_in"] for r in block["rows"]
                if r["hand_in"] and not gone(r)]
        block["soon"] = min(soon) if soon else far
    blocks.sort(key=lambda b: (b["soon"], b["head"]))
    return blocks


def month_label(iso_date):
    """Free from January, the heading over a block of places."""
    if not iso_date:
        return "Date not given"
    d = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"Free from {d:%B}"


def by_month(rows):
    """One block per month you could move in.

    Housing has no categories worth a row of chips and no course, but it
    does have a date, so the month is the heading. Same idea as the day on
    Tickets, one step coarser, because nobody moves on a Tuesday.
    """
    blocks = []
    for row in rows:
        name = month_label(row["available_from"])
        if not blocks or blocks[-1]["head"] != name:
            blocks.append({"head": name, "rows": []})
        blocks[-1]["rows"].append(row)
    return blocks


def housing_search(cat, sort, rent, rmin, rmax, mins, minsx, stay, area,
                   movein, mates, has):
    """Everything the filter panel sent, cleaned up and counted.

    A number somebody typed beats the band above it and switches that band
    off, so the panel never shows two answers to the same question.
    """
    kind = housing.clean_kind(cat)
    sort = sort if sort in housing.SORT_KEYS else ""

    rent = rent if rent in housing.RENT_BY_KEY else ""
    low, high = housing.RENT_BY_KEY[rent][2], housing.RENT_BY_KEY[rent][3]
    typed_low = housing.whole_number(rmin, 100000)
    typed_high = housing.whole_number(rmax, 100000)
    if typed_low or typed_high:
        rent, low, high = "", typed_low, typed_high

    mins = mins if mins in housing.CAMPUS_BY_KEY else ""
    minutes = housing.CAMPUS_BY_KEY[mins][2]
    typed_mins = housing.whole_number(minsx, 600)
    if typed_mins:
        mins, minutes = "", typed_mins

    mates = mates if mates in housing.MATES_BY_KEY else ""
    stay = stay if stay in housing.STAY_BY_KEY else ""
    area = housing.clean_area(area)
    movein = movein if re.fullmatch(r"\d{4}-\d{2}-\d{2}", movein or "") else ""

    picked = [str(p).strip() for p in (has or []) if str(p).strip()]
    bills = "bills" in picked
    feats = [p for p in picked if p in housing.FEATURE_KEYS]

    parts = []
    if movein:
        parts.append("from " + pretty_date(movein))
    if typed_low or typed_high:
        parts.append(" to ".join(money(x) for x in (low, high) if x is not None))
    elif rent:
        band = housing.RENT_BY_KEY[rent]
        parts.append("to " + money(band[3]) if band[3] else "over " + money(band[2]))
    if typed_mins:
        parts.append(f"max {typed_mins} min")
    elif mins:
        parts.append("max " + housing.CAMPUS_LABELS[mins])
    if stay:
        parts.append(housing.STAY_LABELS[stay].lower())
    if kind:
        parts.append(housing.KIND_LABELS[kind])
    if area:
        parts.append(housing.AREA_LABELS[area])
    if mates:
        parts.append(housing.MATES_LABELS[mates].lower())
    if bills:
        parts.append("bills in")
    if feats:
        parts.append(f"{len(feats)} must have" if len(feats) == 1
                     else f"{len(feats)} must haves")

    on = sum(bool(x) for x in (movein, rent or typed_low or typed_high,
                               mins or typed_mins, stay, kind, area, mates,
                               bills)) + len(feats)

    return {"kind": kind, "sort": sort, "rent": rent, "rmin": rmin.strip(),
            "rmax": rmax.strip(), "mins": mins, "minsx": minsx.strip(),
            "stay": stay, "area": area, "movein": movein, "picked": picked,
            "mates": mates,
            # Alone means nobody else, so the ceiling is a real zero and
            # cannot be told apart from "no answer" by truth alone.
            "mates_max": housing.MATES_BY_KEY[mates][2] if mates else None,
            # 1 or 2 means at least one, otherwise living alone would
            # answer a question it is the opposite of.
            "mates_min": 3 if mates == "3" else (1 if mates == "2" else None),
            "low": low, "high": high, "minutes": minutes, "bills": bills,
            "features": feats, "months": housing.STAY_BY_KEY[stay][2],
            "on": on, "summary": ", ".join(parts)}


def link_maker(path, params):
    """Gives the page a link() that changes one thing and keeps the rest.

    Without it, tapping a category would quietly throw away the price filter
    and the sort order that are already set.
    """
    def link(**changes):
        merged = dict(params)
        merged.update(changes)
        pairs = [(key, value) for key, value in merged.items() if value]
        return path + ("?" + urlencode(pairs) if pairs else "")
    return link


PER_DAY = 4


def plain(text):
    """A piece of text boiled down so two spellings of it meet.

    Lower case, accents off, punctuation out, runs of spaces to one. Urban
    Beach, urban beach, Urban-Beach and URBAN BEACH all come out the same.
    It will still miss two people who name a place differently, and that is
    the harmless way round, because then it simply does not bundle.
    """
    text = unicodedata.normalize("NFKD", (text or "").strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def event_key(row):
    """What makes two tickets the same event.

    The same day at the same time at the same place, whatever their owners
    called the listing. The tickets tab folds a day's listings with this, and
    the chats tab puts the people you asked about one party together with it.
    One function, so the app can never give two answers to the same question.
    """
    return ((row["event_date"] or ""), (row["event_time"] or ""),
            plain(row["place"]))


def by_day(rows, open_day=None):
    """Turn a flat list of tickets into one block per day.

    Two tickets are the same event when they are at the same time and the
    same place, whatever their owners called them. The short view then shows
    one card per event, so a party with forty tickets cannot push the rest of
    the day off the screen.
    """
    days = []
    for row in rows:
        date = row["event_date"] or ""
        if not days or days[-1]["date"] != date:
            days.append({"date": date, "all": []})
        days[-1]["all"].append(row)

    for day in days:
        events, seen = [], {}
        for row in day["all"]:
            key = event_key(row)
            if key in seen:
                seen[key]["extra"] += 1
            else:
                card = {"listing": row, "extra": 0}
                seen[key] = card
                events.append(card)

        day["total"] = len(day["all"])
        day["open"] = day["date"] == open_day
        one_each = [{"listing": r, "extra": 0} for r in day["all"]]

        if day["open"]:
            day["cards"] = one_each
        elif len(events) == 1:
            # Only one event that day, so there is nothing for it to push off
            # the screen. Show the tickets themselves instead of one card
            # standing in for all of them.
            day["cards"] = one_each[:PER_DAY]
        else:
            day["cards"] = events[:PER_DAY]

        day["more"] = not day["open"] and day["total"] > len(day["cards"])
    return days


@app.exception_handler(RequestValidationError)
async def bad_address(request: Request, error: RequestValidationError):
    """An address that does not fit its route shows the Not here page.

    /listing/abc and /student/abc used to answer with the raw error the
    framework builds, which is a wall of JSON in the middle of the app. Only
    a GET whose problem is in the path is turned into a page. Anything else,
    above all a form that was filled in wrongly, keeps the old answer, so the
    pages that read those errors still get what they expect.
    """
    im_pfad = all(e.get("loc", ("",))[0] == "path" for e in error.errors())
    if request.method == "GET" and im_pfad:
        return page(request, "missing.html", active="")
    return JSONResponse({"detail": error.errors()}, status_code=422)


# Where a back arrow may point. Said the right way round on purpose: there
# are four or five of these and a dozen of the other kind, and a list of what
# counts cannot quietly forget a page the way a list of exceptions can.
#
# A tab is what the profile goes back to, because the profile is opened from
# a tab. A place is what an entry goes back to, which is a tab or the profile
# or the chats, depending on where the entry was opened from.
TAB_PAGES = ("listings.html", "chats.html")
PLACES = TAB_PAGES + ("profile.html",)


def page(request, template, **values):
    """Render a template with the things every page needs.

    Nothing here is ever kept by the browser. Every page carries live state,
    how many messages are unread, which entries are still open, and a page
    taken out of the browser's store shows the state you left and not the one
    there is. Going back after reading a chat used to bring back the dot you
    had just cleared. It also means none of this stays on the machine after
    somebody logs out, which on a shared laptop is worth the extra request.
    """

    # Once a day, the entries whose day has been close themselves, a ticket
    # by its event and a group by its last day to join. It sits here
    # because every screen comes through this function, so the first person
    # to open anything after midnight does it for everybody.
    db.close_past_dates()
    me = me_or_none(request)
    values.setdefault("me", me)
    values.setdefault("unread", db.unread_total(me["id"]) if me else 0)
    values.setdefault("active", "")
    if template in PLACES:
        where = request.url.path
        if request.url.query:
            where += "?" + request.url.query
        request.session["last_place"] = where
        if template in TAB_PAGES:
            request.session["last_tab"] = where

    answer = templates.TemplateResponse(request, template, values)
    answer.headers["Cache-Control"] = "no-store"
    return answer


def speculative(request):
    """True when the browser is fetching this ahead of anybody asking for it.

    Browsers load a link before it is clicked so the tap feels instant. That
    is welcome for a page, but opening a chat marks its messages read, and a
    guess must not clear something nobody has looked at. Chats were losing
    their unread mark while the list was merely sitting on screen.
    """
    said = (request.headers.get("sec-purpose", "")
            + " " + request.headers.get("purpose", "")).lower()
    return "prefetch" in said or "prerender" in said


def me_or_none(request):
    user_id = request.session.get("user_id")
    return db.get_user(user_id) if user_id else None


def waiting_or_none(request, key):
    """The account a half finished sign up or reset points at, or None.

    A session outlives the row it names. An account can be deleted while a
    browser still has the page open, and then the id in the cookie leads
    nowhere. Every route that reads one of these keys comes through here, so
    a stale one is thrown away and the person starts again, instead of the
    None travelling further in and breaking the page.
    """
    user_id = request.session.get(key)
    user = db.get_user(user_id) if user_id else None
    if user is None:
        request.session.pop(key, None)
    return user


def go(path):
    return RedirectResponse(path, status_code=303)


# How long somebody waits before the same address gets another code. Stops a
# finger on "Send it again", or a script, from flooding an inbox.
RESEND_SECONDS = 60

CODE_ERRORS = {
    "wrong": "That code is not right. Try again.",
    "expired": "That code has run out. Send a new one.",
    "locked": "Too many wrong tries. Send a new code.",
    "none": "There is no code for this address yet. Send a new one.",
}


def verify_url(error=""):
    return "/verify?error=" + quote(error) if error else "/verify"


def reset_url(error="", sent=False):
    """The page for setting a new password, with something to say or not."""
    if error:
        return "/forgot/reset?error=" + quote(error)
    return "/forgot/reset?sent=1" if sent else "/forgot/reset"


def send_code(user, why):
    """Make and send a fresh code. Gives back an error message or "".

    A code sent less than a minute ago is left alone. It still works, and the
    e-mail is probably on its way.
    """
    age = db.code_age(user["id"])
    if age is not None and age < RESEND_SECONDS:
        return ""
    code = db.new_code(user["id"])
    if not mailer.send_code(user["email"], code, why):
        return "We could not send the e-mail. Try again in a minute."
    return ""


# -------------------------------------------------------------------- doors

@app.get("/favicon.ico")
def favicon():
    return RedirectResponse("/static/img/icon-192.png", status_code=301)


@app.get("/")
def home(request: Request):
    return go("/housing" if me_or_none(request) else "/start")


@app.get("/start")
def start_page(request: Request):
    if me_or_none(request):
        return go("/housing")
    return page(request, "start.html")


# ------------------------------------------------------------- creating one

def join_page(request, form, error="", picked=()):
    return page(request, "join.html", f=form, error=error,
                masters=programmes.MASTER, courses=db.all_catalogue_options(),
                picked=set(picked))


@app.get("/join")
def join_form(request: Request):
    if me_or_none(request):
        return go("/housing")
    return join_page(request, {"name": "", "email": "", "programme": "",
                               "cems_programme": ""})


@app.post("/join")
async def join(request: Request,
               name: str = Form(""),
               programme: str = Form(""),
               cems_programme: str = Form(""),
               email: str = Form(""),
               password: str = Form(""),
               password2: str = Form(""),
               photo: UploadFile = File(default=None)):
    email = email.strip().lower()
    form = {"name": name, "email": email, "programme": programme,
            "cems_programme": cems_programme}

    # The ticked courses. They come as a list, so they are read from the form
    # itself rather than as one named argument.
    body = await request.form()
    picked = [v for v in body.getlist("course_id") if str(v).isdigit()]

    def fail(message):
        return join_page(request, form, message, picked)

    if not name.strip():
        return fail("Please put in your name.")
    if len(name.strip()) > db.NAME_MAX:
        return fail(f"A name can be at most {db.NAME_MAX} characters.")

    # CEMS is never the programme itself, so the form has to say which master
    # it sits on top of.
    cems = programme == programmes.CEMS
    chosen = cems_programme if cems else programme
    if cems and not chosen:
        return fail("CEMS MIM only comes with a master. Please pick yours.")
    if not programmes.is_valid(chosen) or (cems and chosen not in programmes.MASTER):
        return fail("Please pick a programme from the list.")

    if not db.is_nova_email(email):
        return fail(f"Your Nova address is your {db.EMAIL_DIGITS} digit student "
                    f"number and {db.EMAIL_DOMAIN}, like {db.EMAIL_HINT}.")

    if password != password2:
        return fail("The two passwords are not the same.")
    wrong = passwords.problem(password)
    if wrong:
        return fail(wrong)

    if photo is not None and photo.filename and not is_picture(photo):
        return fail("That file is not a picture. Use a jpg, png or heic.")

    existing = db.get_user_by_email(email)
    if existing is not None and existing["verified"]:
        return fail("That address already has an account. Log in instead.")

    hashed = passwords.hash_password(password)
    if existing is None:
        user_id = db.create_user(email, name.strip(), chosen, hashed, cems)
    else:
        # Somebody started before and never put the code in. Take the new
        # details and send a fresh code.
        user_id = existing["id"]
        db.update_profile(user_id, name, chosen, cems, None)
        db.set_password(user_id, hashed)

    saved = await save_image(photo)
    if saved:
        db.update_profile(user_id, name, chosen, cems, saved)

    db.set_enrolments(user_id, set(map(int, picked)) & db.valid_course_ids(chosen))

    request.session["pending_id"] = user_id
    problem = send_code(db.get_user(user_id), "join")
    return go(verify_url(problem))


@app.get("/verify")
def verify_form(request: Request, error: str = ""):
    pending = waiting_or_none(request, "pending_id")
    if pending is None:
        return go("/start")
    return page(request, "verify.html", pending=pending, error=error)


@app.post("/verify")
def verify(request: Request, d1: str = Form(""), d2: str = Form(""), d3: str = Form(""),
           d4: str = Form(""), d5: str = Form(""), d6: str = Form("")):
    pending = waiting_or_none(request, "pending_id")
    if pending is None:
        return go("/start")
    user_id = pending["id"]
    code = "".join([d1, d2, d3, d4, d5, d6]).strip()
    result = db.check_code(user_id, code)
    if result != "ok":
        return page(request, "verify.html", pending=pending,
                    error=CODE_ERRORS[result])
    request.session.pop("pending_id", None)
    request.session["user_id"] = user_id
    # Straight in. Whoever left the courses blank is not stopped for them
    # here. Groups says so itself the first time it is opened, and the
    # profile has the list whenever they want it.
    return go("/housing")


@app.post("/verify/resend")
def resend(request: Request):
    user = waiting_or_none(request, "pending_id")
    if user is None:
        return go("/start")
    age = db.code_age(user["id"])
    if age is not None and age < RESEND_SECONDS:
        wait = int(RESEND_SECONDS - age) + 1
        return go(verify_url(f"Wait {wait} seconds, then ask again."))
    problem = send_code(user, "join")
    return go(verify_url(problem))


# ------------------------------------------------------------- coming back

@app.get("/login")
def login_form(request: Request):
    if me_or_none(request):
        return go("/housing")
    return page(request, "login.html")


@app.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form("")):
    user = db.get_user_by_email(email)

    # The same answer whether the address is unknown or the password is wrong,
    # so nobody can use this page to find out who has an account.
    if user is None or not passwords.verify_password(user["password"], password):
        return page(request, "login.html", email=email,
                    error="That e-mail and password do not go together.")

    if not user["verified"]:
        request.session["pending_id"] = user["id"]
        problem = send_code(user, "login")
        return go(verify_url(problem))

    request.session.clear()
    request.session["user_id"] = user["id"]
    return go("/housing")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return go("/start")


# ---------------------------------------------------------- a new password

@app.get("/forgot")
def forgot_form(request: Request):
    return page(request, "forgot.html")


@app.post("/forgot")
def forgot(request: Request, email: str = Form("")):
    email = email.strip().lower()
    user = db.get_user_by_email(email)
    if user is None:
        # Again the same answer either way, so this page tells nobody which
        # addresses exist. The code simply never arrives.
        return page(request, "forgot.html", email=email,
                    error="If that address has an account, the code is on its way.")
    problem = send_code(user, "reset")
    if problem:
        return page(request, "forgot.html", email=email, error=problem)
    request.session["reset_id"] = user["id"]
    return go("/forgot/reset")


@app.get("/forgot/reset")
def reset_form(request: Request, error: str = "", sent: int = 0):
    user = waiting_or_none(request, "reset_id")
    if user is None:
        return go("/forgot")
    return page(request, "reset.html", pending=user, error=error, sent=sent)


@app.post("/forgot/reset/resend")
def reset_resend(request: Request):
    """Another code for somebody already on the page, without sending them
    back to the form that asks for an address they have just given."""
    user = waiting_or_none(request, "reset_id")
    if user is None:
        return go("/forgot")
    age = db.code_age(user["id"])
    if age is not None and age < RESEND_SECONDS:
        wait = int(RESEND_SECONDS - age) + 1
        return go(reset_url(f"Wait {wait} seconds, then ask again."))
    problem = send_code(user, "reset")
    return go(reset_url(problem) if problem else reset_url(sent=True))


@app.post("/forgot/reset")
def reset(request: Request, d1: str = Form(""), d2: str = Form(""), d3: str = Form(""),
          d4: str = Form(""), d5: str = Form(""), d6: str = Form(""),
          password: str = Form(""), password2: str = Form("")):
    user = waiting_or_none(request, "reset_id")
    if user is None:
        return go("/forgot")
    user_id = user["id"]

    def fail(message):
        return page(request, "reset.html", pending=user, error=message)

    if password != password2:
        return fail("The two passwords are not the same.")
    wrong = passwords.problem(password)
    if wrong:
        return fail(wrong)
    result = db.check_code(user_id, "".join([d1, d2, d3, d4, d5, d6]).strip())
    if result != "ok":
        return fail(CODE_ERRORS[result])

    db.set_password(user_id, passwords.hash_password(password))
    request.session.pop("reset_id", None)
    request.session["user_id"] = user_id
    return go("/housing")


# ---------------------------------------------------------------------- dev

@app.get("/dev")
def dev_form(request: Request):
    """Development login. Delete this page once the real one works."""
    return page(request, "dev.html", users=db.all_users())


@app.post("/dev")
def dev_login(request: Request, user_id: int = Form(...)):
    request.session.clear()
    request.session["user_id"] = user_id
    return go("/housing")


# --------------------------------------------------------------- the four tabs

def tab_page(request, kind, q, scope="mine", cat="", day="", sort="",
             price="", cond="", hs=None):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    tab = BY_KIND[kind]

    # Groups is the only tab that is narrowed to your own courses, because it
    # is the only one where the whole school would otherwise be in your list.
    mine = db.courses_of(me["id"]) if kind == "group" else []
    only_for = me["id"] if (kind == "group" and scope == "mine") else None

    if hs is not None:
        # Housing arrives already cleaned, because its panel asks about ten
        # things and the cleaning of those lives in one place.
        rows = db.listings_of_type(
            kind, q or "", category=hs["kind"], sort=hs["sort"] or None,
            min_price=hs["low"], max_price=hs["high"], price_inclusive=True,
            free_from=hs["movein"] or None, area=hs["area"],
            max_minutes=hs["minutes"], max_months=hs["months"],
            bills_included=hs["bills"], features=hs["features"],
            max_mates=hs["mates_max"], min_mates=hs["mates_min"])
        cat, sort = hs["kind"] or "", hs["sort"]
        price = cond = ""
    else:
        # Anything the address does not recognise is dropped rather than
        # argued with, so a hand typed link can never put the page in a state
        # it has no button for.
        cat = cat if categories.is_valid(cat, kind) else ""
        sort = sort if sort in SORT_KEYS else ""
        price = price if price in BY_BAND else ""
        cond = cond if cond in categories.CONDITION_LABELS else ""
        band = BY_BAND[price]

        rows = db.listings_of_type(kind, q or "", only_for=only_for,
                                   category=cat or None, sort=sort or None,
                                   min_price=band[2], max_price=band[3],
                                   free_only=price == "free",
                                   condition=cond or None)

    # Tickets are read by day, Groups by course and Housing by month, so all
    # three are grouped before the page sees them. Market stays a plain list
    # because a thing for sale has no date of its own.
    days = by_day(rows, day) if kind == "ticket" else None
    blocks = None
    if kind == "group":
        blocks = by_course(rows)
    elif kind == "housing" and not sort:
        # Sorting by rent and heading by month at the same time would say two
        # different things about the same list.
        blocks = by_month(rows)

    # The row is what you get when you have asked for nothing. The moment you
    # pick a category, a sort, a price or type a search, the list itself is
    # the answer and a second unfiltered row next to it would only confuse.
    untouched = not (q or cat or sort or price or cond)
    fresh = fresh_rows(rows) if kind == "item" and untouched else []

    # Whatever the row at the top is showing comes out of the list below it.
    # The two were sorted the same way, so the row was the first four of the
    # list shown a second time and said nothing the list did not. Now the
    # row is this week and the list is everything before it.
    if fresh:
        lifted = {r["id"] for r in fresh}
        rows = [r for r in rows if r["id"] not in lifted]

    params = {"q": q or "", "cat": cat, "sort": sort, "price": price,
              "cond": cond, "day": day or ""}

    # Everything that is in the address except the search text itself, so
    # the search box can hand it all back when it is used. Without this,
    # typing in the box threw away the filters you had just set, while the
    # filters kept your search. The two halves of one screen have to agree.
    keep = {name: value for name, value in request.query_params.items()
            if name != "q" and value}

    return page(request, "listings.html", tab=tab, listings=rows, q=q or "",
                keep=keep,
                active=kind, me=me, scope=scope, my_courses=mine,
                days=days, blocks=blocks, cat=cat, open_day=day, fresh=fresh,
                sort=sort, price=price, cond=cond, bands=PRICE_BANDS, hs=hs,
                link=link_maker(tab["path"], params))


@app.get("/housing")
def housing_tab(request: Request, q: str = "", cat: str = "", sort: str = "",
                rent: str = "", rmin: str = "", rmax: str = "", mins: str = "",
                minsx: str = "", stay: str = "", area: str = "",
                movein: str = "", mates: str = "",
                has: List[str] = Query(default=[])):
    hs = housing_search(cat, sort, rent, rmin, rmax, mins, minsx, stay, area,
                        movein, mates, has)
    return tab_page(request, "housing", q, hs=hs)


@app.get("/tickets")
def tickets(request: Request, q: str = "", cat: str = "", day: str = ""):
    return tab_page(request, "ticket", q, cat=cat, day=day)


@app.get("/market")
def market(request: Request, q: str = "", cat: str = "", sort: str = "",
           price: str = "", cond: str = ""):
    return tab_page(request, "item", q, cat=cat, sort=sort, price=price,
                    cond=cond)


@app.get("/groups")
def groups(request: Request, q: str = "", scope: str = "mine"):
    return tab_page(request, "group", q, "all" if scope == "all" else "mine")


# ------------------------------------------------------------------- courses

@app.get("/courses")
def courses_form(request: Request, back: str = "/profile"):
    """Pick the courses you are taking. This is what makes Groups short."""
    me = me_or_none(request)
    if me is None:
        return go("/start")
    chosen = {c["id"] for c in db.courses_of(me["id"])}

    courses = db.courses_for_programme(me["programme"])
    return page(request, "courses.html", courses=courses, chosen=chosen,
                back=back, me=me)


@app.post("/courses")
async def courses_save(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    form = await request.form()
    picked = [v for v in form.getlist("course_id") if str(v).isdigit()]
    db.set_enrolments(me["id"], set(map(int, picked)) & db.valid_course_ids(me["programme"]))
    back = form.get("back") or "/profile"
    return go(back if str(back).startswith("/") else "/profile")


# ------------------------------------------------------------- one listing

@app.get("/listing/{listing_id}")
def listing_detail(request: Request, listing_id: int, back: str = ""):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    row = db.get_listing(listing_id)
    if row is None:
        return page(request, "missing.html", active="")
    if row["owner_id"] != me["id"]:
        db.count_view(listing_id, me["id"])
        row = db.get_listing(listing_id)
    queue = db.interest_in(listing_id)
    return page(request, "detail.html", listing=row, photos=db.photos_of(listing_id),
                tab=BY_KIND[row["type"]], me=me,
                back=back or request.session.get("last_place")
                     or BY_KIND[row["type"]]["path"],
                tabs=tear_tabs(row) if row["type"] == "group" else [],
                saved=db.is_saved(me["id"], listing_id),
                saves=db.save_count(listing_id),
                queue=queue, my_place=db.place_in_queue(queue, me["id"]))


@app.post("/listing/{listing_id}/close")
def listing_close(request: Request, listing_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    db.close_listing(listing_id, me["id"])
    return go("/profile?done=closed")


@app.post("/listing/{listing_id}/reopen")
def listing_reopen(request: Request, listing_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    db.reopen_listing(listing_id, me["id"])
    return go("/profile?done=reopened")


@app.post("/listing/{listing_id}/save")
def listing_save(request: Request, listing_id: int):
    """The heart, top right of an entry.

    It answers in JSON when the page asks with fetch, so the heart fills in
    on the spot. Without JavaScript the same button still works, the page
    simply comes back fresh.
    """
    me = me_or_none(request)
    if me is None:
        return go("/start")
    saved = db.toggle_save(me["id"], listing_id)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"saved": saved, "count": db.save_count(listing_id)})
    return go(f"/listing/{listing_id}")


@app.post("/listing/{listing_id}/chat")
def listing_chat(request: Request, listing_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    row = db.get_listing(listing_id)
    if row is None or row["owner_id"] == me["id"]:
        return go(f"/listing/{listing_id}")
    conv_id = db.open_conversation(listing_id, me["id"])
    return go(f"/chat/{conv_id}")


# --------------------------------------------------------------- putting up

def form_values(listing=None):
    """What the entry form shows in its fields, all empty for a new entry.

    One dict, so the template never has to ask whether it is writing an
    entry or changing one. Everything comes back as text because that is
    what an input field holds, and a price of 45.0 would otherwise appear
    as 45.0 in the box.
    """
    def text(name):
        if listing is None:
            return ""
        value = listing[name]
        if value is None:
            return ""
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)

    fields = {name: text(name) for name in db.EDITABLE if name != "features"}
    fields["features"] = set(
        p.strip() for p in ((listing["features"] or "") if listing else "").split(",")
        if p.strip())
    return fields


@app.get("/listing/{listing_id}/edit")
def edit_form(request: Request, listing_id: int, error: str = "", back: str = ""):
    """The same form again, with the entry already in it."""
    me = me_or_none(request)
    if me is None:
        return go("/start")
    listing = db.get_listing(listing_id)
    if listing is None or listing["owner_id"] != me["id"]:
        return page(request, "missing.html", me=me)
    kind = listing["type"]
    return page(request, "new.html", tab=BY_KIND[kind], error=error, me=me,
                active=kind, v=form_values(listing), edit_id=listing_id,
                back=back or BY_KIND[kind]["path"],
                my_courses=db.courses_of(me["id"]) if kind == "group" else [])


@app.get("/new")
def new_form(request: Request, kind: str = "housing", error: str = ""):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    if kind not in BY_KIND:
        kind = "housing"
    mine = db.courses_of(me["id"]) if kind == "group" else []
    if kind == "group" and not mine:
        # You cannot put up a group entry without saying which course it is for.
        return go("/courses?back=/new%3Fkind%3Dgroup")
    return page(request, "new.html", tab=BY_KIND[kind], error=error, me=me,
                active=kind, my_courses=mine, v=form_values())


@app.post("/new/autofill")
def new_autofill(request: Request, url: str = Form(""), text: str = Form("")):
    """Fill the housing form from an advert, by its link or by its pasted text.

    Answers in JSON: the fields we could read, and how. With a link the
    server fetches the page itself; sites that block robots (Idealista does)
    get an honest "blocked", and the page then offers the paste instead.
    Only links to the sites in housing.PLATFORMS are ever fetched.
    """
    if me_or_none(request) is None:
        return JSONResponse({"ok": False, "reason": "login"}, status_code=401)

    if text.strip():
        fields = housing.parse_listing_text(text[:60000])
        # The first real line of a copied advert is almost always its headline.
        first = next((l.strip() for l in text.splitlines() if len(l.strip()) > 8), "")
        if first and len(first) <= 120 and "€" not in first:
            fields["title"] = housing._clean_title(first)
        return JSONResponse({"ok": bool(fields), "how": "text", "fields": fields})

    link = housing.clean_listing_url(url)
    if not link:
        return JSONResponse({"ok": False, "reason": "site"})
    site = housing.platform_of(link)["name"]
    if housing.blocks_apps(link):
        # No point asking: these sites refuse every app. Straight to the paste box.
        return JSONResponse({"ok": False, "reason": "blocked", "site": site})
    if not housing.may_fetch(me_or_none(request)["id"]):
        return JSONResponse({"ok": False, "reason": "limit", "site": site})
    try:
        status, page = housing.fetch_listing(link)
    except Exception:
        return JSONResponse({"ok": False, "reason": "unreachable", "site": site})
    if housing.looks_blocked(status, page):
        return JSONResponse({"ok": False, "reason": "blocked", "site": site})
    fields = housing.parse_listing_page(page)
    return JSONResponse({"ok": bool(fields), "how": "link", "site": site,
                         "fields": fields, "reason": "" if fields else "empty"})


@app.post("/new")
async def new_listing(request: Request,
                      kind: str = Form("housing"),
                      title: str = Form(""),
                      price: str = Form(""),
                      info: str = Form(""),
                      category: str = Form(""),
                      condition: str = Form(""),
                      event_date: str = Form(""),
                      event_time: str = Form(""),
                      place: str = Form(""),
                      address: str = Form(""),
                      quantity: str = Form(""),
                      course_id: str = Form(""),
                      hand_in: str = Form(""),
                      group_size: str = Form(""),
                      available_from: str = Form(""),
                      months_min: str = Form(""),
                      bills_included: str = Form(""),
                      bills_estimate: str = Form(""),
                      deposit: str = Form(""),
                      minutes_campus: str = Form(""),
                      flatmates: str = Form(""),
                      features: List[str] = Form(default=[]),
                      external_url: str = Form(""),
                      description: str = Form(""),
                      photos: List[UploadFile] = File(default=[]),
                      edit_id: str = Form(""),
                      back: str = Form("")):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    if kind not in BY_KIND:
        kind = "housing"

    # Everything that was typed, so a page sent back with a complaint still
    # holds it. Without this a long entry is lost to one wrong field, and
    # changing an entry would be worse still, since the loss is the entry.
    typed = {
        "title": title, "description": description, "price": price,
        "info": info, "category": category, "condition": condition,
        "event_date": event_date, "event_time": event_time, "place": place,
        "address": address, "quantity": quantity, "course_id": course_id,
        "hand_in": hand_in, "group_size": group_size,
        "available_from": available_from, "months_min": months_min,
        "bills_included": bills_included, "bills_estimate": bills_estimate,
        "deposit": deposit, "minutes_campus": minutes_campus,
        "flatmates": flatmates, "features": set(features or []),
    }
    mine = db.courses_of(me["id"]) if kind == "group" else []

    # Changing an entry goes through the same form and the same checks. Only
    # the owner, and the kind cannot be swapped, because it comes from the
    # entry and not from the request.
    changing = db.get_listing(int(edit_id)) if edit_id.strip().isdigit() else None
    if changing is not None and changing["owner_id"] != me["id"]:
        changing = None
    if edit_id.strip() and changing is None:
        # Somebody sent an entry that is not theirs, or one that is gone.
        # Making a new entry out of that would be a strange thing to do, so
        # nothing happens at all.
        return page(request, "missing.html", me=me)
    if changing is not None:
        kind = changing["type"]

    def oops(message):
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, v=typed, error=message, back=back,
                    edit_id=changing["id"] if changing else None)

    if len(title.strip()) > TITLE_MAX:
        return oops(f"A title can be at most {TITLE_MAX} characters.")

    if not title.strip():
        return oops("An entry needs a title.")

    # A description is what somebody actually reads before writing to you, so
    # on these two tabs an entry without one is not worth putting up.
    if kind in DESC_MAX:
        if not description.strip():
            return oops("An entry needs a description.")
        if len(description.strip()) > DESC_MAX[kind]:
            return oops("A description can be at most "
                        f"{DESC_MAX[kind]} characters.")

    money, wrong = clean_price(price)
    if wrong:
        return oops(wrong)

    if kind == "group" and not course_id.strip().isdigit():
        return oops("Pick the course this group is for.")

    if kind == "group" and int(course_id) not in {c["id"] for c in mine}:
        return oops("That is not one of your courses.")

    if kind == "housing":
        # Everything somebody searches or compares by has to be there. A
        # place without a rent, a date or a deposit is not an offer, it is
        # a question, and it would sit in the list answering nothing.
        if not available_from.strip():
            return oops("Say from when the place is free.")
        if not place.strip():
            return oops("Pick the area the place is in.")
        if not address.strip():
            return oops("A place needs its address.")

        rent, wrong = clean_price(price)
        if wrong:
            return oops(wrong)
        if rent is None:
            return oops("Say what the rent per month is.")

        # Included means there is nothing to say, so whatever arrived in
        # the box is dropped rather than argued with.
        if bills_included.strip() == "1":
            bills_estimate = ""
        else:
            bills, wrong = clean_price(bills_estimate)
            if wrong:
                return oops(wrong)
            if bills is not None and bills > BILLS_MAX:
                return oops(f"Bills of at most {BILLS_MAX:,} euros, please.")

        down, wrong = clean_price(deposit)
        if wrong:
            return oops(wrong)
        if down is None:
            return oops("Say what the deposit is. Write 0 if there is none.")

        for text, name, ceiling in (
                (months_min, "the shortest stay in months", MONTHS_MAX),
                (minutes_campus, "how long it takes to campus in minutes",
                 MINUTES_MAX)):
            if housing.whole_number(text, ceiling) is None:
                return oops(f"Say {name}, 1 to {ceiling}.")
        if not flatmates.strip().isdigit() or int(flatmates) > FLATMATES_MAX:
            return oops(f"Say how many flatmates there are, 0 to {FLATMATES_MAX}.")

    link = housing.clean_listing_url(external_url) if kind == "housing" else None
    if kind == "housing" and external_url.strip() and not link:
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine,
                    error="That link is not from a housing site we know. "
                          "Use one from " + ", ".join(housing.PLATFORM_NAMES) + ".")

    if kind == "group" and not hand_in.strip():
        return oops("A group entry needs the date the group has to be together.")

    # You are in your own group, so the free seats can never be the whole
    # group. Three of three free would mean nobody is in it.
    if kind == "group":
        size = int(group_size) if group_size.strip().isdigit() else 0
        free = int(quantity) if quantity.strip().isdigit() else 0
        if size < 2 or size > GROUP_MAX:
            return oops(f"A group is between 2 and {GROUP_MAX} people.")
        if free < 1 or free >= size:
            return oops(f"With a group of {size} you can offer at most "
                              f"{size - 1} spots, because one of them is yours.")
        if hand_in.strip() < datetime.now().astimezone().date().isoformat():
            return oops("That date has passed. Pick the last day somebody "
                              "can still join.")

    if kind == "ticket":
        if not event_date.strip():
            return oops("A ticket needs the date of the event.")
        # The time is as compulsory as the day, because the day, the time
        # and the venue together are what decide that two tickets are to
        # the same event. Leave one out and a ticket stands on its own
        # beside the party it belongs to.
        if not event_time.strip():
            return oops("A ticket needs the time the event starts.")
        # Both of these are compulsory because both are read by somebody
        # else. The venue with the day is what puts two tickets to the same
        # party in one bundle, and the address is what opens in maps.
        if not place.strip():
            return oops("A ticket needs the name of the venue.")
        if not address.strip():
            return oops("A ticket needs the address of the venue.")
        if len(place.strip()) > PLACE_MAX:
            return oops(f"A venue name can be at most {PLACE_MAX} characters.")
        if len(address.strip()) > ADDRESS_MAX:
            return oops(f"An address can be at most {ADDRESS_MAX} characters.")
        # The day of the event still counts, a party is sold until the door,
        # but yesterday is nothing anybody can buy any more.
        if event_date.strip() < today_iso():
            return oops("That date has passed. A ticket can only be for "
                        "today or a day after it.")
        # The box says one to fifty and so does this, because the box can be
        # got around and the number ends up on somebody else's screen.
        many = int(quantity) if quantity.strip().isdigit() else 0
        if many < 1 or many > TICKET_MAX:
            return oops(f"Say how many tickets you have, 1 to {TICKET_MAX}.")

    fields = dict(
        title=title.strip(),
        description=description.strip(),
        price=money,
        # The grey line is gone from every tab. Nothing writes it any more
        # and nothing reads it, the description says all of it.
        info="",
        # Housing keeps its kind of place in the same column, but its list
        # lives in housing.py, not in categories.py.
        category=(housing.clean_kind(category) if kind == "housing"
                  else categories.clean(category, kind)
                  if kind in categories.FOR_KIND else None),
        condition=categories.clean_condition(condition) if kind == "item" else None,
        event_date=event_date.strip() or None,
        event_time=event_time.strip() or None,
        place=(housing.clean_area(place) if kind == "housing"
               else place.strip() or None),
        address=address.strip() or None,
        quantity=int(quantity) if quantity.strip().isdigit() else None,
        course_id=int(course_id) if (kind == "group" and course_id.strip().isdigit())
        else None,
        hand_in=(hand_in.strip() or None) if kind == "group" else None,
        group_size=(int(group_size) if kind == "group" and group_size.strip().isdigit()
                    else None),
        available_from=(available_from.strip() or None) if kind == "housing" else None,
        months_min=(housing.whole_number(months_min, MONTHS_MAX)
                    if kind == "housing" else None),
        bills_included=(1 if bills_included.strip() == "1" else 0) if kind == "housing" else None,
        bills_estimate=(clean_price(bills_estimate)[0] if kind == "housing"
                        else None),
        deposit=(clean_price(deposit)[0] if kind == "housing" else None),
        minutes_campus=(housing.whole_number(minutes_campus, MINUTES_MAX)
                        if kind == "housing" else None),
        flatmates=(int(flatmates) if kind == "housing"
                   and flatmates.strip().isdigit() else None),
        features=housing.clean_features(features) if kind == "housing" else None,
        external_url=link,
    )

    if changing is not None:
        db.update_listing(changing["id"], me["id"], **fields)
        listing_id = changing["id"]
    else:
        listing_id = db.create_listing(owner_id=me["id"], kind=kind, **fields)

    # Pictures added while changing an entry go after the ones already there.
    position = len(db.photos_of(listing_id)) if changing is not None else 0
    for upload in (photos or []) if kind != "ticket" else []:
        if not upload or not upload.filename:
            continue
        ext = os.path.splitext(upload.filename)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
            continue
        name = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(UPLOADS, name), "wb") as out:
            out.write(await upload.read())
        db.add_photo(listing_id, name, position)
        position += 1

    # The way out is carried through the form, because the page before this
    # one is now the form itself and an arrow pointing there is a trap.
    done = "saved" if changing is not None else "published"
    where = f"/listing/{listing_id}?done={done}"
    if changing is not None and back.startswith("/") and not back.startswith("//"):
        where += "&back=" + quote(back)
    return go(where)


PICTURE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic")


def is_picture(upload):
    """True when a file was given and it looks like a picture we accept."""
    if not upload or not upload.filename:
        return False
    return os.path.splitext(upload.filename)[1].lower() in PICTURE_TYPES


async def save_image(upload):
    """Write one uploaded picture to the uploads folder. Gives back its name."""
    if not is_picture(upload):
        return None
    ext = os.path.splitext(upload.filename)[1].lower()
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOADS, name), "wb") as out:
        out.write(await upload.read())
    return name


# -------------------------------------------------------------------- chats

# How many chats a block shows before it offers the rest behind a line. It is
# a floor and not a ceiling, because every unread chat is shown whatever the
# count says. Forty people writing about one ticket are forty rows, and that
# is right, they are all waiting on you.
SHOW_AT_LEAST = 4


def bundle_key(row):
    """What two conversations must share to be about the same thing.

    Only a ticket and a group spot can be asked of several people at once,
    because several students sell a ticket to one party and several groups
    look for someone in one course. A room and a desk exist once, so a
    conversation about one never joins another. None means it stands alone.
    """
    if row["kind"] == "ticket":
        # Nothing to go on is not the same as going on nothing. Without a day
        # and a place two tickets would share an empty key and be thrown
        # together although nobody said they belong together.
        if not (row["event_date"] and plain(row["place"])):
            return None
        return ("ticket",) + event_key(row)
    if row["kind"] == "group" and row["course_id"]:
        return ("group", row["course_id"])
    return None


def bundle_heading(row):
    """The line over a bundle, taken from what the bundle is keyed on."""
    if row["kind"] == "ticket":
        parts = [row["place"], short_date(row["event_date"])]
        said = " \u00b7 ".join(p for p in parts if p)
        if said:
            return said
    if row["course_name"]:
        return row["course_name"]
    return row["title"]


def dress(block):
    """Fill in what every block needs, whichever side it is on.

    Newest message first inside the block, the same order a messenger uses.
    Unread is not pulled to the top on purpose: an order that changes when
    you read something moves the row out from under your thumb.

    Whether a block stands open is the one thing that does follow unread. A
    block with something waiting shows every chat, because that is how you
    find it. A settled one with more than a couple of chats folds into its
    own heading, so a list of finished conversations does not bury the one
    that wants you.
    """
    chats = block["chats"]
    # Newest message first and nothing else, the way a messenger has always
    # done it. Writing to somebody lifts them just as receiving does, because
    # both make their last message the newest one. Unread is a mark on a row,
    # not a place in the order, so reading something never shuffles the list
    # under your thumb.
    chats.sort(key=lambda r: (r["last_at"] or "", r["id"]), reverse=True)
    block["unread"] = sum(r["unread"] for r in chats)
    block["total"] = len(chats)
    block["at"] = chats[0]["last_at"] or ""

    # What is on show runs from the top down to the last unread chat, and
    # never stops before the fourth. Down to it and not just at it, so there
    # is never a hole in the middle: reading nine of ten still leaves all ten
    # standing, because the tenth is still waiting under them.
    waiting = [n for n, r in enumerate(chats) if r["unread"]]
    cut = max(SHOW_AT_LEAST, (waiting[-1] + 1) if waiting else 0)
    block["show_ids"] = {r["id"] for r in chats[:cut]}
    block["rest"] = max(0, block["total"] - cut)
    return block


def block_key(row, bundle=None):
    """A name for a block that survives the list being built again.

    The browser remembers which blocks you had open, and it has to find the
    same block afterwards even though the order may have changed and the
    unread may be gone. The position in the list is useless for that, the
    thing the block is about is not.
    """
    if bundle is None:
        return "l%s" % row["listing_id"]
    return "b" + "|".join(str(part) for part in bundle)


def selling_blocks(rows):
    """One block per entry of yours, with everyone who wrote about it.

    Newest message first, the way a messenger orders anything. Reading does
    not move a block, because reading leaves the last message where it was,
    so the list only ever rearranges when something actually arrives. That is
    the one time you want it to.
    """
    blocks = {}
    for row in rows:
        block = blocks.get(row["listing_id"])
        if block is None:
            block = blocks[row["listing_id"]] = {"listing": row, "chats": []}
        block["chats"].append(row)
    out = [dress(b) for b in blocks.values()]
    for block in out:
        block["key"] = block_key(block["listing"])
    out.sort(key=lambda b: (b["at"] or "", b["listing"]["listing_id"]),
             reverse=True)
    return out


def bundles_of(rows):
    """The things you asked more than one person about.

    These are the only groups worth offering as a filter. Asking one person
    about one room is not a group, it is a chat. The label is the place and
    the day for an event and the course for a group spot, which is what the
    bundle is keyed on anyway.
    """
    found = {}
    for row in rows:
        key = bundle_key(row)
        if key is None:
            continue
        here = found.get(key)
        if here is None:
            here = found[key] = {"key": block_key(row, key), "kind": row["kind"],
                                 "label": bundle_heading(row), "count": 0,
                                 "unread": 0, "at": row["last_at"] or ""}
            here["raw"] = key
        here["count"] += 1
        here["unread"] += row["unread"]
        here["at"] = max(here["at"], row["last_at"] or "")
    ready = [b for b in found.values() if b["count"] > 1]
    ready.sort(key=lambda b: b["at"], reverse=True)
    return ready


def matches(row, words):
    """Does this conversation answer to what was typed in the search box?"""
    if not words:
        return True
    hay = " ".join(plain(str(part)) for part in
                   (row["other_name"], row["title"], row["last_body"],
                    row["course_name"], row["place"]) if part)
    return all(word in hay for word in words)


@app.get("/chats")
def chats(request: Request, side: str = "", kind: str = "", bundle: str = "",
          q: str = "", archived: int = 0):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    everything = db.conversations_of(me["id"])
    # What somebody put away is kept out of the list and counted at its
    # foot. The archive is one screen with nothing on it but the chats, so
    # the switch, the filters and the search all stay behind.
    live = [r for r in everything if not r["archived"]]
    away = [r for r in everything if r["archived"]]
    archived = bool(archived)
    rows = away if archived else live
    mine = [r for r in rows if r["owner_id"] == me["id"]]
    theirs = [r for r in rows if r["owner_id"] != me["id"]]
    away_mine = [r for r in away if r["owner_id"] == me["id"]]
    away_theirs = [r for r in away if r["owner_id"] != me["id"]]

    # Which side you were on is remembered, so opening a chat and coming
    # back does not quietly put you on the other one.
    if side not in ("sell", "buy"):
        side = request.session.get("chats_side", "buy")
    side = "sell" if side == "sell" else "buy"
    here = mine if side == "sell" else theirs

    # A remembered side with nothing in it is not worth opening while the
    # other one has something to read, so the list goes where the chats are.
    # A side whose chats are all archived is not empty though, it has the way
    # in to them at its foot, and sliding off it would hide them for good.
    # The archive itself is left alone, because you asked for one side of it.
    bare = not here and not (away_mine if side == "sell" else away_theirs)
    if not archived and bare and (theirs if side == "sell" else mine):
        side = "buy" if side == "sell" else "sell"
        here = mine if side == "sell" else theirs
    request.session["chats_side"] = side

    # Only the tabs that have something on this side, and on the asking side
    # also the things you wrote to several people about. A filter that is
    # sure to give you nothing is a button not worth pressing.
    kinds = [] if archived else [t for t in TABS
                                 if any(r["kind"] == t["kind"] for r in here)]
    bundles = bundles_of(here) if side == "buy" and not archived else []
    if kind not in {t["kind"] for t in kinds}:
        kind = ""
    if bundle not in {b["key"] for b in bundles}:
        bundle = ""
    # One filter at a time. A bundle already says which tab it is in.
    if bundle:
        kind = ""
        keyed = {b["key"]: b["raw"] for b in bundles}[bundle]
        here = [r for r in here if bundle_key(r) == keyed]
    elif kind:
        here = [r for r in here if r["kind"] == kind]

    words = [w for w in plain(q).split() if w]
    if words:
        here = [r for r in here if matches(r, words)]

    if side == "sell":
        blocks = selling_blocks(here)
        chats_flat = []
    else:
        blocks = []
        chats_flat = sorted(here, key=lambda r: (r["last_at"] or "", r["id"]),
                            reverse=True)

    # The foot of the list, so the archive is a place you can see rather
    # than one you have to know about. Counted for this side only.
    # Entries on the one side and chats on the other, because that is what
    # the line says and what the side is made of. Two chats about one entry
    # of yours are one thing in the archive, not two.
    kept = away_mine if side == "sell" else away_theirs
    kept_n = (len({r["listing_id"] for r in kept}) if side == "sell"
              else len(kept))

    # The switch counts the archive as well. A side with nothing but
    # archived chats still has to be one you can press, or the only way
    # back to them would be to type the address.
    return page(request, "chats.html", blocks=blocks, chats=chats_flat,
                side=side, kind=kind, bundle=bundle, q=q,
                kinds=kinds, bundles=bundles, archived=archived,
                kept=kept_n, kept_unread=sum(r["unread"] for r in kept),
                has_sell=any(r["owner_id"] == me["id"] for r in everything),
                has_buy=any(r["owner_id"] != me["id"] for r in everything),
                unread_sell=sum(r["unread"] for r in live
                                if r["owner_id"] == me["id"]),
                unread_buy=sum(r["unread"] for r in live
                               if r["owner_id"] != me["id"]),
                active="chats", me=me)


@app.get("/chat/{conv_id}")
def chat(request: Request, conv_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    conv = db.get_conversation(conv_id)
    if not db.can_see_conversation(conv, me["id"]):
        return page(request, "missing.html", active="chats")
    if not speculative(request):
        db.mark_read(conv_id, me["id"])
    other_id = conv["starter_id"] if conv["owner_id"] == me["id"] else conv["owner_id"]
    # Your own side of the archive. The other person's stamp is theirs.
    away = (conv["archived_owner"] if conv["owner_id"] == me["id"]
            else conv["archived_starter"])
    return page(request, "chat.html", conv=conv, other=db.get_user(other_id),
                messages=db.messages_of(conv_id), archived=bool(away),
                active="chats", me=me)


@app.post("/chat/{conv_id}")
def chat_send(request: Request, conv_id: int, body: str = Form("")):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    conv = db.get_conversation(conv_id)
    if not db.can_see_conversation(conv, me["id"]):
        return page(request, "missing.html", active="chats")
    db.send_message(conv_id, me["id"], body)
    return go(f"/chat/{conv_id}")


@app.post("/chat/{conv_id}/archive")
def chat_archive(request: Request, conv_id: int):
    """Put one chat away. The asking side only.

    On your own entries a whole entry goes away in one piece, so there is
    no single chat to put away there and the button is on the entry.
    Nothing here asks whether the entry is closed. A student who stops
    answering never closes anything, and that is the chat you most want
    out of your list.
    """
    me = me_or_none(request)
    if me is None:
        return go("/start")
    conv = db.get_conversation(conv_id)
    if not db.can_see_conversation(conv, me["id"]):
        return page(request, "missing.html", active="chats")
    if conv["owner_id"] == me["id"]:
        return go("/chats?side=sell")
    db.archive_chat(conv_id, me["id"], on=True)
    return go("/chats?side=buy")


@app.post("/chat/{conv_id}/unarchive")
def chat_unarchive(request: Request, conv_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    conv = db.get_conversation(conv_id)
    if not db.can_see_conversation(conv, me["id"]):
        return page(request, "missing.html", active="chats")
    if conv["owner_id"] == me["id"]:
        return go("/chats?side=sell")
    db.archive_chat(conv_id, me["id"], on=False)
    return go("/chats?side=buy")


@app.post("/listing/{listing_id}/archive")
def entry_archive(request: Request, listing_id: int):
    """Put a whole entry of yours away, with everyone who wrote about it."""
    me = me_or_none(request)
    if me is None:
        return go("/start")
    db.archive_entry(listing_id, me["id"], on=True)
    return go("/chats?side=sell")


@app.post("/listing/{listing_id}/unarchive")
def entry_unarchive(request: Request, listing_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    db.archive_entry(listing_id, me["id"], on=False)
    return go("/chats?side=sell")


# ------------------------------------------------------------------ profile

def edit_page(request, me, error="", form_name=None, current=None):
    return page(request, "edit_profile.html", me=me, error=error,
                form_name=form_name,
                current=current if current is not None else (
                    programmes.CEMS if me["cems"] else me["programme"]),
                masters=programmes.MASTER)


@app.get("/student/{user_id}")
def student(request: Request, user_id: int):
    """Somebody else, as far as another student may see them.

    Name, programme and what they have up. No address, no e-mail, nothing
    they did not put up themselves.
    """
    me = me_or_none(request)
    if me is None:
        return go("/start")
    if user_id == me["id"]:
        return go("/profile")
    them = db.get_user(user_id)
    if them is None or not them["verified"]:
        return page(request, "missing.html", me=me)
    open_rows = [l for l in db.listings_of_user(user_id) if l["status"] == "open"]
    return page(request, "student.html", them=them, open_rows=open_rows, me=me,
                back=request.session.get("last_place") or "/chats")


@app.get("/profile/edit")
def profile_edit_form(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    return edit_page(request, me)


@app.post("/profile/edit")
async def profile_edit(request: Request,
                       name: str = Form(""),
                       programme: str = Form(""),
                       cems_programme: str = Form(""),
                       photo: UploadFile = File(default=None)):
    me = me_or_none(request)
    if me is None:
        return go("/start")

    if not name.strip():
        return edit_page(request, me, "Your name cannot be empty.",
                         form_name=name, current=programme)
    if len(name.strip()) > db.NAME_MAX:
        return edit_page(request, me,
                         f"A name can be at most {db.NAME_MAX} characters.",
                         form_name=name, current=programme)

    # CEMS is never the programme itself. It is a yes next to a real master,
    # so the form has to say which master it sits on top of.
    cems = programme == programmes.CEMS
    chosen = cems_programme if cems else programme

    if cems and not chosen:
        return edit_page(request, me,
                         "CEMS MIM only comes with a master. Please pick yours.",
                         form_name=name, current=programme)

    if not programmes.is_valid(chosen) or (cems and chosen not in programmes.MASTER):
        return edit_page(request, me, "Please pick a programme from the list.",
                         form_name=name, current=programme)

    # A file was picked but it is not a picture we can show. Say so instead of
    # quietly keeping the old one.
    if photo is not None and photo.filename and not is_picture(photo):
        return edit_page(request, me,
                         "That file is not a picture. Use a jpg, png or heic.",
                         form_name=name, current=programme)

    db.update_profile(me["id"], name, chosen, cems, await save_image(photo))
    return go("/profile")


@app.get("/profile/password")
def password_form(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    return page(request, "password.html", me=me)


@app.post("/profile/password")
def password_change(request: Request, current: str = Form(""),
                    password: str = Form(""), password2: str = Form("")):
    me = me_or_none(request)
    if me is None:
        return go("/start")

    def fail(message):
        return page(request, "password.html", me=me, error=message)

    # The one you have now, so nobody who picks up an unlocked phone can
    # lock the owner out.
    if not passwords.verify_password(me["password"], current):
        return fail("That is not your current password.")
    if password != password2:
        return fail("The two new passwords are not the same.")
    if password == current:
        return fail("That is the password you already have.")
    wrong = passwords.problem(password)
    if wrong:
        return fail(wrong)

    db.set_password(me["id"], passwords.hash_password(password))
    return go("/profile")


@app.get("/profile")
def profile(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    mine = db.listings_of_user(me["id"])
    return page(request, "profile.html", mine=mine,
                back=request.session.get("last_tab") or "/housing",
                my_courses=db.courses_of(me["id"]),
                saved=db.saved_listings(me["id"]),
                chat_count=len(db.conversations_of(me["id"])), me=me)
