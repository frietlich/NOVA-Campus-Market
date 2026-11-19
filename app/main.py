"""Campus Market, the web app.

Every page lives here. The database is only reached through db.py.
Start it with   uvicorn app.main:app --reload   from the project folder.
"""

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import quote, urlencode

from fastapi import FastAPI, Form, Query, Request, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import categories, db, housing, mailer, passwords, programmes

# .env first, so CAMPUS_SECRET and the mail account can live in it.
mailer.load_env()

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(HERE, "static", "uploads")
LOCAL_DEMO = os.environ.get("CAMPUS_SECURITY_DEMO") == "1"
SECRET = os.environ.get("CAMPUS_SECRET", "")
if len(SECRET) < 32:
    raise RuntimeError("Set CAMPUS_SECRET to at least 32 random characters.")

# The four tabs. Everything about a tab is in this one list.
TABS = [
    {"kind": "housing", "label": "Housing", "path": "/housing",
     "placeholder": "Carcavelos, from January"},
    {"kind": "ticket", "label": "Tickets", "path": "/tickets",
     "placeholder": "Party, football, concert"},
    {"kind": "item", "label": "Market", "path": "/market",
     "placeholder": "Bike, desk, textbooks"},
    {"kind": "group", "label": "Groups", "path": "/groups",
     "placeholder": "Course or hand in date"},
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
templates.env.globals["CATEGORIES_FOR"] = categories.FOR_KIND
templates.env.globals["CONDITIONS"] = categories.CONDITION
templates.env.globals["CONDITION_LABELS"] = categories.CONDITION_LABELS
templates.env.globals["SORT_OPTIONS"] = SORT_OPTIONS
templates.env.globals["SORT_SHORT"] = SORT_SHORT
templates.env.globals["PRICE_BANDS"] = PRICE_BANDS
templates.env.globals["HOUSING"] = housing
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
TABS_MIN = 5
TABS_MAX = 7
TEAR_SHAPES = 6


def tear_tabs(listing):
    """One entry per tab at the bottom of a group notice.

    A hanging tab is a spot still free, a torn one is a spot somebody already
    took. The shape number picks one of six ragged edges and comes from the
    id of the entry, so the same notice always tears the same way and two
    notices next to each other do not.
    """
    size = listing["group_size"] or listing["quantity"] or TABS_MIN
    slots = max(TABS_MIN, min(TABS_MAX, size))
    hanging = max(0, min(listing["quantity"] or 0, slots))
    return [{"hanging": n >= slots - hanging,
             "shape": (listing["id"] + n) % TEAR_SHAPES}
            for n in range(slots)]


def by_course(rows):
    """Turn a flat list of group entries into one block per course.

    Groups has no date to read it by and no categories. The course is what
    you are looking for, so two entries for the same course belong under one
    heading. The rows arrive sorted by course, so walking them once is enough.
    """
    blocks = []
    for row in rows:
        name = row["course_name"] or "No course"
        if not blocks or blocks[-1]["head"] != name:
            blocks.append({"head": name, "rows": []})
        blocks[-1]["rows"].append(row)
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
            key = (row["event_time"] or "", (row["place"] or "").strip().lower())
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


def page(request, template, **values):
    """Render a template with the things every page needs."""
    me = me_or_none(request)
    values.setdefault("me", me)
    values.setdefault("unread", db.unread_total(me["id"]) if me else 0)
    values.setdefault("active", "")
    return templates.TemplateResponse(request, template, values)


def me_or_none(request):
    user_id = request.session.get("user_id")
    user = db.get_user(user_id) if user_id else None
    if user and user["verified"] and db.is_nova_email(user["email"]):
        return user
    return None


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


def send_code(user, why):
    """Make and send a fresh code. Gives back an error message or "".

    A code sent less than a minute ago is left alone. It still works, and the
    e-mail is probably on its way.
    """
    age = db.code_age(user["id"])
    if age is not None and age < RESEND_SECONDS:
        return ""
    if not mailer.is_set_up():
        return "Email delivery is not configured. Please contact the app team."
    try:
        code = db.new_code(user["id"], why)
    except ValueError as error:
        return str(error)
    if not mailer.send_code(user["email"], code, why):
        db.cancel_code(user["id"], code, why)
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

    # CEMS is never the programme itself, so the form has to say which master
    # it sits on top of.
    cems = programme == programmes.CEMS
    chosen = cems_programme if cems else programme
    if cems and not chosen:
        return fail("CEMS MIM only comes with a master. Please pick yours.")
    if not programmes.is_valid(chosen) or (cems and chosen not in programmes.MASTER):
        return fail("Please pick a programme from the list.")

    if not db.is_nova_email(email):
        return fail("Only a novasbe.pt address can join.")

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
    user_id = request.session.get("pending_id")
    if not user_id:
        return go("/start")
    return page(request, "verify.html", pending=db.get_user(user_id), error=error)


@app.post("/verify")
def verify(request: Request, d1: str = Form(""), d2: str = Form(""), d3: str = Form(""),
           d4: str = Form(""), d5: str = Form(""), d6: str = Form("")):
    user_id = request.session.get("pending_id")
    if not user_id:
        return go("/start")
    code = "".join([d1, d2, d3, d4, d5, d6]).strip()
    result = db.check_code(user_id, code, "join")
    if result != "ok":
        return page(request, "verify.html", pending=db.get_user(user_id),
                    error=CODE_ERRORS[result])
    request.session.clear()
    request.session["user_id"] = user_id
    # Whoever skipped the courses on the way in gets asked once now, so that
    # Groups is already theirs the first time they open it.
    if not db.courses_of(user_id):
        return go("/courses?back=/housing")
    return go("/housing")


@app.post("/verify/resend")
def resend(request: Request):
    user_id = request.session.get("pending_id")
    if not user_id:
        return go("/start")
    user = db.get_user(user_id)
    age = db.code_age(user_id)
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
    if not db.is_nova_email(email) or not 1 <= len(password) <= 128:
        return page(request, "login.html", email=email, error="That e-mail and password do not go together.")
    user = db.get_user_by_email(email)

    # The same answer whether the address is unknown or the password is wrong,
    # so nobody can use this page to find out who has an account.
    if user is None or not passwords.verify_password(user["password"], password):
        return page(request, "login.html", email=email,
                    error="That e-mail and password do not go together.")

    if not user["verified"]:
        request.session["pending_id"] = user["id"]
        problem = send_code(user, "join")
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
def reset_form(request: Request):
    user_id = request.session.get("reset_id")
    if not user_id:
        return go("/forgot")
    return page(request, "reset.html", pending=db.get_user(user_id))


@app.post("/forgot/reset")
def reset(request: Request, d1: str = Form(""), d2: str = Form(""), d3: str = Form(""),
          d4: str = Form(""), d5: str = Form(""), d6: str = Form(""),
          password: str = Form(""), password2: str = Form("")):
    user_id = request.session.get("reset_id")
    if not user_id:
        return go("/forgot")
    user = db.get_user(user_id)

    def fail(message):
        return page(request, "reset.html", pending=user, error=message)

    if password != password2:
        return fail("The two passwords are not the same.")
    wrong = passwords.problem(password)
    if wrong:
        return fail(wrong)
    result = db.check_code(user_id, "".join([d1, d2, d3, d4, d5, d6]).strip(), "reset")
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
    if not LOCAL_DEMO:
        return HTMLResponse("Not found", status_code=404)
    return page(request, "dev.html", users=[user for user in db.all_users()
                if user["verified"] and db.is_nova_email(user["email"])])


@app.post("/dev")
def dev_login(request: Request, user_id: int = Form(...)):
    if not LOCAL_DEMO:
        return HTMLResponse("Not found", status_code=404)
    user = db.get_user(user_id)
    if not user or not user["verified"] or not db.is_nova_email(user["email"]):
        return HTMLResponse("Access refused", status_code=403)
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
                link=link_maker(tab["path"], params))


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
    return page(request, "detail.html", listing=row, photos=db.photos_of(listing_id),
                tab=BY_KIND[row["type"]], me=me,
                tabs=tear_tabs(row) if row["type"] == "group" else [],
                saved=db.is_saved(me["id"], listing_id),
                saves=db.save_count(listing_id))


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
                    my_courses=mine, error="A group entry needs the hand in date.")

    if kind == "ticket" and not event_date.strip():
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="A ticket needs the date of the event.")

    from decimal import Decimal, InvalidOperation
    try:
        if price.strip():
            amount = Decimal(price)
            if not amount.is_finite() or amount < 0 or amount > 100000:
                raise ValueError
        if quantity.strip() and (not quantity.isascii() or not quantity.isdigit()
                                 or not 1 <= int(quantity) <= 100):
            raise ValueError
        if len(title.strip()) > 100 or len(description) > 2000 or len(info) > 300:
            raise ValueError
        if kind == "group" and int(course_id) not in {course["id"] for course in mine}:
            raise ValueError
        if event_date.strip():
            datetime.strptime(event_date, "%Y-%m-%d")
    except (ValueError, InvalidOperation):
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="Check the price, quantity, course and date.")
    # Decode every photo before creating the listing, so invalid files cannot create a partial entry.
    image_names = []
    for upload in (photos or []) if kind != "ticket" else []:
        if upload and upload.filename:
            image_names.append(await save_image(upload))

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

    for position, name in enumerate(image_names):
        db.add_photo(listing_id, name, position)

    return go(f"/listing/{listing_id}?done=published")


PICTURE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic")


def is_picture(upload):
    """True when a file was given and it looks like a picture we accept."""
    if not upload or not upload.filename:
        return False
    return os.path.splitext(upload.filename)[1].lower() in PICTURE_TYPES


async def save_image(upload):
    from io import BytesIO
    from PIL import Image, ImageOps, UnidentifiedImageError
    from fastapi import HTTPException
    if not upload or not upload.filename:
        return None
    data = await upload.read(5_000_001)
    if len(data) > 5_000_000:
        raise HTTPException(400, "Images must be under 5 MB.")
    try:
        with Image.open(BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as picture:
            if picture.width * picture.height > 20_000_000:
                raise HTTPException(400, "Image dimensions are too large.")
            picture = ImageOps.exif_transpose(picture).convert("RGB")
            picture.thumbnail((1400, 1400))
            name = uuid.uuid4().hex + ".jpg"
            picture.save(os.path.join(UPLOADS, name), "JPEG", quality=85)
            return name
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(400, "Upload a valid JPEG, PNG or WebP image.") from None


# -------------------------------------------------------------------- chats

@app.get("/chats")
def chats(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    return page(request, "chats.html", conversations=db.conversations_of(me["id"]),
                active="chats", me=me)


@app.get("/chat/{conv_id}")
def chat(request: Request, conv_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    conv = db.get_conversation(conv_id)
    if not db.can_see_conversation(conv, me["id"]):
        return page(request, "missing.html", active="chats")
    db.mark_read(conv_id, me["id"])
    other_id = conv["starter_id"] if conv["owner_id"] == me["id"] else conv["owner_id"]
    return page(request, "chat.html", conv=conv, other=db.get_user(other_id),
                messages=db.messages_of(conv_id), active="chats", me=me)


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


# ------------------------------------------------------------------ profile

def edit_page(request, me, error="", form_name=None, current=None):
    return page(request, "edit_profile.html", me=me, error=error,
                form_name=form_name,
                current=current if current is not None else (
                    programmes.CEMS if me["cems"] else me["programme"]),
                masters=programmes.MASTER)


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
                my_courses=db.courses_of(me["id"]),
                saved=db.saved_listings(me["id"]),
                chat_count=len(db.conversations_of(me["id"])), me=me)


@app.middleware("http")
async def security_checks(request, call_next):
    from urllib.parse import urlsplit
    if request.url.path.startswith("/static/uploads/") and me_or_none(request) is None:
        return HTMLResponse("Sign in required", status_code=403)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.url.path in ("/login", "/join", "/forgot", "/verify", "/verify/resend", "/forgot/reset"):
            from hashlib import sha256
            address = request.client.host if request.client else "unknown"
            key = sha256(f"{request.url.path}:{address}".encode()).hexdigest()
            if not db.take_security_attempt(key, limit=20):
                return HTMLResponse("Too many attempts. Please wait ten minutes.", status_code=429)
        origin = request.headers.get("origin") or request.headers.get("referer")
        source = urlsplit(origin) if origin else None
        if not source or source.scheme != request.url.scheme or source.netloc != request.url.netloc:
            return HTMLResponse("Request origin refused", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers["Cache-Control"] = "no-store"
    if not LOCAL_DEMO:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


app.add_middleware(SessionMiddleware, secret_key=SECRET, max_age=60 * 60 * 8, https_only=not LOCAL_DEMO, same_site="lax")
