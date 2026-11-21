"""Campus Market, the web app.

Every page lives here. The database is only reached through db.py.
Start it with   uvicorn app.main:app --reload   from the project folder.
"""

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import quote, urlencode

from fastapi import BackgroundTasks, FastAPI, Form, Query, Request, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import (categories, db, housing, mailer, passwords, programmes, push,
               screenshots, ticket_import)

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
    """today, tomorrow, 16 days left, or overdue once the day is past."""
    if not iso_date:
        return ""
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    gap = (d - datetime.now().astimezone().date()).days
    if gap < 0:
        return "overdue"
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    return f"{gap} days left"


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
templates.env.globals["SORT_OPTIONS"] = SORT_OPTIONS
templates.env.globals["SORT_SHORT"] = SORT_SHORT
templates.env.globals["PRICE_BANDS"] = PRICE_BANDS
templates.env.globals["HOUSING"] = housing
templates.env.globals["SCREENSHOTS_ON"] = screenshots.is_set_up
templates.env.globals["SCREENSHOTS_MAX"] = screenshots.MAX_IMAGES
templates.env.globals["PUSH_ON"] = push.is_set_up
templates.env.globals["PUSH_KEY"] = push.public_key
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
                   movein, has):
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
    if bills:
        parts.append("bills in")
    if feats:
        parts.append(f"{len(feats)} must have" if len(feats) == 1
                     else f"{len(feats)} must haves")

    on = sum(bool(x) for x in (movein, rent or typed_low or typed_high,
                               mins or typed_mins, stay, kind, area, bills)) + len(feats)

    return {"kind": kind, "sort": sort, "rent": rent, "rmin": rmin.strip(),
            "rmax": rmax.strip(), "mins": mins, "minsx": minsx.strip(),
            "stay": stay, "area": area, "movein": movein, "picked": picked,
            "low": low, "high": high, "minutes": minutes, "bills": bills,
            "features": feats, "months": housing.STAY_BY_KEY[stay][2],
            "on": on, "summary": ", ".join(parts)}


# --------------------------------------------------------- saved searches

# The filters of each tab that a saved search keeps. Sort order and the open
# day are left out, they change how the list looks, not what is in it.
SEARCH_KEYS = {
    "ticket": ("q", "cat"),
    "item": ("q", "cat", "price", "cond"),
    "housing": ("q", "cat", "rent", "rmin", "rmax", "mins", "minsx", "stay",
                "area", "movein", "has"),
}


def search_of(kind, query):
    """The search on a tab as one JSON string, the same whoever wrote the address.

    query is the address's query part, as a string or as the request's own
    query parameters. Empty filters are dropped and the keys sorted, so the
    same search is always the same string.
    """
    from urllib.parse import parse_qs
    if isinstance(query, str):
        values = parse_qs(query, keep_blank_values=False)
        get = lambda k: (values.get(k) or [""])[0]
        get_all = lambda k: values.get(k) or []
    else:
        get, get_all = (lambda k: query.get(k) or ""), query.getlist
    found = {}
    for key in SEARCH_KEYS.get(kind, ()):
        if key == "has":
            picked = sorted({v.strip() for v in get_all("has") if v.strip()})
            if picked:
                found["has"] = picked
        elif get(key).strip():
            found[key] = get(key).strip()[:80]
    if kind == "housing":
        # Keep only what the panel itself would keep.
        hs = housing_search(found.get("cat", ""), "", found.get("rent", ""),
                            found.get("rmin", ""), found.get("rmax", ""),
                            found.get("mins", ""), found.get("minsx", ""),
                            found.get("stay", ""), found.get("area", ""),
                            found.get("movein", ""), found.get("has", []))
        if not hs["kind"]:
            found.pop("cat", None)
    else:
        if found.get("cat") and not categories.is_valid(found["cat"], kind):
            found.pop("cat")
        if found.get("price") not in (None, *BY_BAND):
            found.pop("price")
        if found.get("cond") and found["cond"] not in categories.CONDITION_LABELS:
            found.pop("cond")
    return json.dumps(found, sort_keys=True, ensure_ascii=False)


def search_label(kind, params):
    """A saved search in words, for the list in the settings."""
    p = json.loads(params)
    parts = [f"\u201c{p['q']}\u201d"] if p.get("q") else []
    if kind == "housing":
        hs = housing_search(p.get("cat", ""), "", p.get("rent", ""), p.get("rmin", ""),
                            p.get("rmax", ""), p.get("mins", ""), p.get("minsx", ""),
                            p.get("stay", ""), p.get("area", ""), p.get("movein", ""),
                            p.get("has", []))
        if hs["kind"]:
            parts.append(housing.KIND_LABELS[hs["kind"]])
        if hs["area"]:
            parts.append(housing.AREA_LABELS[hs["area"]])
        if hs["low"] is not None and hs["high"] is not None:
            parts.append(f"{money(hs['low'])} to {money(hs['high'])}")
        elif hs["high"] is not None:
            parts.append(f"up to {money(hs['high'])}")
        elif hs["low"] is not None:
            parts.append(f"from {money(hs['low'])}")
        if hs["movein"]:
            parts.append("free from " + pretty_date(hs["movein"]))
        if hs["minutes"]:
            parts.append(f"max {hs['minutes']} min to campus")
        if hs["stay"]:
            parts.append(housing.STAY_LABELS[hs["stay"]].lower())
        if hs["bills"]:
            parts.append("bills included")
        parts += [housing.FEATURE_LABELS[f].lower() for f in hs["features"]]
    else:
        if p.get("cat"):
            parts.append(categories.label(p["cat"]))
        if p.get("price"):
            parts.append(BY_BAND[p["price"]][1].lower())
        if p.get("cond"):
            parts.append(categories.CONDITION_LABELS[p["cond"]].lower())
    return " · ".join(parts) if parts else "Everything new"


def search_rows(kind, params):
    """The open entries a saved search finds, the way the tab finds them."""
    p = json.loads(params)
    if kind == "housing":
        hs = housing_search(p.get("cat", ""), "", p.get("rent", ""), p.get("rmin", ""),
                            p.get("rmax", ""), p.get("mins", ""), p.get("minsx", ""),
                            p.get("stay", ""), p.get("area", ""), p.get("movein", ""),
                            p.get("has", []))
        return db.listings_of_type(
            kind, p.get("q", ""), category=hs["kind"], min_price=hs["low"],
            max_price=hs["high"], price_inclusive=True, free_from=hs["movein"] or None,
            area=hs["area"], max_minutes=hs["minutes"], max_months=hs["months"],
            bills_included=hs["bills"], features=hs["features"])
    band = BY_BAND[p.get("price", "")]
    return db.listings_of_type(kind, p.get("q", ""), category=p.get("cat") or None,
                               min_price=band[2], max_price=band[3],
                               free_only=p.get("price") == "free",
                               condition=p.get("cond") or None)


def search_finds(kind, params, listing_id):
    """True when this saved search would show this entry on the tab."""
    return any(row["id"] == listing_id for row in search_rows(kind, params))


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


def page(request, template, **values):
    """Render a template with the things every page needs.

    Nothing here is ever kept by the browser. Every page carries live state,
    how many messages are unread, which entries are still open, and a page
    taken out of the browser's store shows the state you left and not the one
    there is. Going back after reading a chat used to bring back the dot you
    had just cleared. It also means none of this stays on the machine after
    somebody logs out, which on a shared laptop is worth the extra request.
    """
    me = me_or_none(request)
    values.setdefault("me", me)
    values.setdefault("unread", db.unread_total(me["id"]) if me else 0)
    values.setdefault("active", "")
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
            bills_included=hs["bills"], features=hs["features"])
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

    params = {"q": q or "", "cat": cat, "sort": sort, "price": price,
              "cond": cond, "day": day or ""}

    return page(request, "listings.html", tab=tab, listings=rows, q=q or "",
                active=kind, me=me, scope=scope, my_courses=mine,
                days=days, blocks=blocks, cat=cat, open_day=day, fresh=fresh,
                sort=sort, price=price, cond=cond, bands=PRICE_BANDS, hs=hs,
                link=link_maker(tab["path"], params),
                watching=(kind in SEARCH_KEYS and db.is_watching_search(
                    me["id"], kind, search_of(kind, request.query_params))),
                here=str(request.url.path) + (f"?{request.url.query}" if request.url.query else ""))


@app.get("/housing")
def housing_tab(request: Request, q: str = "", cat: str = "", sort: str = "",
                rent: str = "", rmin: str = "", rmax: str = "", mins: str = "",
                minsx: str = "", stay: str = "", area: str = "",
                movein: str = "", has: List[str] = Query(default=[])):
    hs = housing_search(cat, sort, rent, rmin, rmax, mins, minsx, stay, area,
                        movein, has)
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
def listing_detail(request: Request, listing_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    row = db.get_listing(listing_id)
    if row is None:
        return page(request, "missing.html", active="")
    if row["owner_id"] != me["id"]:
        db.count_view(listing_id)
        row = db.get_listing(listing_id)
    watching = (row["type"] == "ticket" and bool(row["event_date"])
                and db.is_watching_event(me["id"], event_key(row)))
    return page(request, "detail.html", listing=row, photos=db.photos_of(listing_id),
                tab=BY_KIND[row["type"]], me=me,
                tabs=tear_tabs(row) if row["type"] == "group" else [],
                saved=db.is_saved(me["id"], listing_id),
                saves=db.save_count(listing_id), watching_event=watching)


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
                active=kind, my_courses=mine)


@app.post("/new/ticket-autofill")
def new_ticket_autofill(request: Request, url: str = Form("")):
    """Fill the ticket form from the link to the event. Answers in JSON.

    Only links to the sites in ticket_import.PLATFORMS are ever fetched. The
    seller sees the filled form and checks it before anything is published.
    """
    if me_or_none(request) is None:
        return JSONResponse({"ok": False, "reason": "login"}, status_code=401)
    return JSONResponse(ticket_import.autofill(url))


@app.post("/new/screenshot")
def new_from_screenshots(request: Request, kind: str = Form(""),
                         screenshots_: List[UploadFile] = File(default=[], alias="screenshots")):
    """Fill the ticket or housing form from screenshots, read by Claude.

    Same JSON as the link. The pictures are only read, never stored, and each
    student has a daily limit because every picture costs money.
    """
    me = me_or_none(request)
    if me is None:
        return JSONResponse({"ok": False, "reason": "login"}, status_code=401)
    if not screenshots.is_set_up():
        return JSONResponse({"ok": False, "reason": "setup"})
    files = [f for f in screenshots_ if f and f.filename]
    if len(files) > screenshots.MAX_IMAGES:
        return JSONResponse({"ok": False, "reason": "many"})
    if not db.take_ai_read(me["id"], screenshots.READS_PER_DAY, max(1, len(files))):
        return JSONResponse({"ok": False, "reason": "limit"})
    pictures = [f.file.read(screenshots.MAX_UPLOAD + 1) for f in files]
    return JSONResponse(screenshots.read(kind, pictures))


@app.post("/new")
async def new_listing(request: Request,
                      background: BackgroundTasks,
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
                      deposit_months: str = Form(""),
                      minutes_campus: str = Form(""),
                      flatmates: str = Form(""),
                      features: List[str] = Form(default=[]),
                      description: str = Form(""),
                      photos: List[UploadFile] = File(default=[])):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    if kind not in BY_KIND:
        kind = "housing"

    mine = db.courses_of(me["id"]) if kind == "group" else []

    if len(title.strip()) > TITLE_MAX:
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=db.courses_of(me["id"]) if kind == "group" else [],
                    error=f"A title can be at most {TITLE_MAX} characters.")

    if not title.strip():
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="An entry needs a title.")

    if kind == "group" and not course_id.strip().isdigit():
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="Pick the course this group is for.")

    if kind == "housing" and not available_from.strip():
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="Say from when the place is free.")

    if kind == "group" and not hand_in.strip():
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="A group entry needs the date the group has to be together.")

    # You are in your own group, so the free seats can never be the whole
    # group. Three of three free would mean nobody is in it.
    if kind == "group":
        size = int(group_size) if group_size.strip().isdigit() else 0
        free = int(quantity) if quantity.strip().isdigit() else 0
        if size < 2 or size > GROUP_MAX:
            return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                        my_courses=mine,
                        error=f"A group is between 2 and {GROUP_MAX} people.")
        if free < 1 or free >= size:
            return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                        my_courses=mine,
                        error=f"With a group of {size} you can offer at most "
                              f"{size - 1} spots, because one of them is yours.")
        if hand_in.strip() < datetime.now().astimezone().date().isoformat():
            return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                        my_courses=mine,
                        error="That date has passed. Pick the last day somebody "
                              "can still join.")

    if kind == "ticket" and not event_date.strip():
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="A ticket needs the date of the event.")

    listing_id = db.create_listing(
        owner_id=me["id"],
        kind=kind,
        title=title.strip(),
        description=description.strip(),
        price=float(price) if price.strip() else None,
        info=info.strip(),
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
        months_min=housing.whole_number(months_min, 36) if kind == "housing" else None,
        bills_included=(1 if bills_included.strip() == "1" else 0) if kind == "housing" else None,
        bills_estimate=(float(bills_estimate) if kind == "housing"
                        and bills_estimate.strip() else None),
        deposit_months=housing.whole_number(deposit_months, 12) if kind == "housing" else None,
        minutes_campus=housing.whole_number(minutes_campus, 600) if kind == "housing" else None,
        flatmates=housing.whole_number(flatmates, 20) if kind == "housing" else None,
        features=housing.clean_features(features) if kind == "housing" else None,
    )

    position = 0
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

    # Everyone watching this tab hears about it, after the page has answered.
    background.add_task(push.new_listing, db.get_listing(listing_id), event_key,
                        search_finds)
    return go(f"/listing/{listing_id}?done=published")


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
          q: str = ""):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    rows = db.conversations_of(me["id"])
    mine = [r for r in rows if r["owner_id"] == me["id"]]
    theirs = [r for r in rows if r["owner_id"] != me["id"]]

    # Which side you were on is remembered, so opening a chat and coming
    # back does not quietly put you on the other one.
    if side not in ("sell", "buy"):
        side = request.session.get("chats_side", "buy")
    side = "sell" if side == "sell" else "buy"
    here = mine if side == "sell" else theirs

    # A remembered side with nothing in it is not worth opening while the
    # other one has something to read, so the list goes where the chats are.
    if not here and (theirs if side == "sell" else mine):
        side = "buy" if side == "sell" else "sell"
        here = mine if side == "sell" else theirs
    request.session["chats_side"] = side

    # Only the tabs that have something on this side, and on the asking side
    # also the things you wrote to several people about. A filter that is
    # sure to give you nothing is a button not worth pressing.
    kinds = [t for t in TABS if any(r["kind"] == t["kind"] for r in here)]
    bundles = bundles_of(here) if side == "buy" else []
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

    return page(request, "chats.html", blocks=blocks, chats=chats_flat,
                side=side, kind=kind, bundle=bundle, q=q,
                kinds=kinds, bundles=bundles,
                has_sell=bool(mine), has_buy=bool(theirs),
                unread_sell=sum(r["unread"] for r in mine),
                unread_buy=sum(r["unread"] for r in theirs),
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
    return page(request, "chat.html", conv=conv, other=db.get_user(other_id),
                messages=db.messages_of(conv_id), active="chats", me=me)


@app.post("/chat/{conv_id}")
def chat_send(request: Request, background: BackgroundTasks, conv_id: int,
              body: str = Form("")):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    conv = db.get_conversation(conv_id)
    if not db.can_see_conversation(conv, me["id"]):
        return page(request, "missing.html", active="chats")
    if db.send_message(conv_id, me["id"], body):
        background.add_task(push.new_message, conv, me["id"], body.strip())
    return go(f"/chat/{conv_id}")


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
    return page(request, "student.html", them=them, open_rows=open_rows, me=me)


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


# --------------------------------------------------------- notifications

@app.get("/sw.js")
def service_worker():
    """The service worker has to come from the top of the site, or it may
    only look after the pages below /static."""
    return FileResponse(os.path.join(HERE, "static", "js", "sw.js"),
                        media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.post("/push/device")
async def push_device(request: Request):
    """The browser said yes to notifications. Remember this device."""
    me = me_or_none(request)
    if me is None:
        return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await request.json()
        endpoint, keys = data["endpoint"], data["keys"]
        p256dh, auth = keys["p256dh"], keys["auth"]
    except (ValueError, KeyError, TypeError):
        return JSONResponse({"ok": False}, status_code=400)
    if not (isinstance(endpoint, str) and endpoint.startswith("https://")
            and len(endpoint) < 1000 and isinstance(p256dh, str) and len(p256dh) < 200
            and isinstance(auth, str) and len(auth) < 100):
        return JSONResponse({"ok": False}, status_code=400)
    db.save_device(me["id"], endpoint, p256dh, auth)
    return JSONResponse({"ok": True})


@app.post("/push/device/forget")
async def push_device_forget(request: Request):
    me = me_or_none(request)
    if me is None:
        return JSONResponse({"ok": False}, status_code=401)
    try:
        endpoint = (await request.json())["endpoint"]
    except (ValueError, KeyError, TypeError):
        return JSONResponse({"ok": False}, status_code=400)
    db.drop_device(str(endpoint), me["id"])
    return JSONResponse({"ok": True})


@app.post("/push/test")
def push_test(request: Request):
    """A notification to yourself, to see that it works on this phone."""
    me = me_or_none(request)
    if me is None:
        return JSONResponse({"ok": False}, status_code=401)
    reached = push.send(me["id"], "Campus Market",
                        "Notifications work on this device.", "/profile/notifications",
                        test=True)
    return JSONResponse({"ok": reached > 0, "reached": reached})


@app.get("/profile/notifications")
def notifications_form(request: Request, done: str = ""):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    return page(request, "notifications.html", me=me, prefs=db.prefs_of(me["id"]),
                areas=push.AREAS, devices=len(db.devices_of(me["id"])), done=done,
                events=db.events_watched(me["id"]), searches=db.searches_watched(me["id"]),
                tab_names={t["kind"]: t["label"] for t in TABS})


@app.post("/profile/notifications")
async def notifications_save(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    form = await request.form()
    on = set(form.getlist("on"))
    for area in db.NOTIFY_AREAS:
        db.set_pref(me["id"], area, area in on)
    return go("/profile/notifications?done=saved")


@app.post("/notify/event")
def notify_event(request: Request, listing_id: int = Form(0), on: str = Form("1")):
    """The bell on a ticket: tell me about more tickets for this same event."""
    me = me_or_none(request)
    if me is None:
        return go("/start")
    row = db.get_listing(listing_id)
    if row is None or row["type"] != "ticket" or not row["event_date"]:
        return go("/tickets")
    if on == "1":
        db.watch_event(me["id"], event_key(row), row["title"], row["place"])
    else:
        db.unwatch_event(me["id"], event_key(row))
    return go(f"/listing/{listing_id}?done=" + ("watching" if on == "1" else "unwatched"))


@app.post("/notify/event/remove")
def notify_event_remove(request: Request, watch_id: int = Form(0)):
    """Stop watching one event, from the list in the settings."""
    me = me_or_none(request)
    if me is None:
        return go("/start")
    db.unwatch_event(me["id"], watch_id=watch_id)
    return go("/profile/notifications?done=removed")


@app.post("/notify/watch")
def notify_watch(request: Request, kind: str = Form(""), back: str = Form("")):
    """The bell on a tab: save the search on screen, or forget it again."""
    me = me_or_none(request)
    if me is None:
        return go("/start")
    if kind not in SEARCH_KEYS:
        return go("/profile/notifications")
    # Only ever back to a page of our own.
    back = back if back.startswith("/") and not back.startswith("//") else BY_KIND[kind]["path"]
    params = search_of(kind, back.partition("?")[2])
    if db.is_watching_search(me["id"], kind, params):
        db.unwatch_search(me["id"], kind, params)
        done = "search-off"
    else:
        db.watch_search(me["id"], kind, params, search_label(kind, params))
        done = "search-on"
    return go(back + ("&" if "?" in back else "?") + "done=" + done)


@app.post("/notify/search/remove")
def notify_search_remove(request: Request, watch_id: int = Form(0)):
    """Forget one saved search, from the list in the settings."""
    me = me_or_none(request)
    if me is None:
        return go("/start")
    db.unwatch_search(me["id"], watch_id=watch_id)
    return go("/profile/notifications?done=removed-search")


@app.get("/profile")
def profile(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    mine = db.listings_of_user(me["id"])
    return page(request, "profile.html", mine=mine,
                my_courses=db.courses_of(me["id"]),
                saved=db.saved_listings(me["id"]),
                chat_count=len(db.conversations_of(me["id"])), me=me)
