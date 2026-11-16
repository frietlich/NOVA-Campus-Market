"""Campus Market, the web app.

Every page lives here. The database is only reached through db.py.
Start it with   uvicorn app.main:app --reload   from the project folder.
"""

import os
import re
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import categories, db, passwords, programmes

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(HERE, "static", "uploads")
SECRET = os.environ.get("CAMPUS_SECRET", "change-me-before-you-deploy")

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
    """14:32 today, Yesterday before that, then 12 Nov."""
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
    return t.strftime("%-d %b")


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
    return {"weekday": d.strftime("%a").upper(), "day": d.strftime("%-d"),
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
    return d.strftime("%A %-d %B")


def pretty_date(iso_date):
    if not iso_date:
        return ""
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%-d %b %Y")


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
templates.env.filters["category"] = categories.label
templates.env.globals["pretty_date"] = pretty_date
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
templates.env.globals["PROGRAMME_GROUPS"] = programmes.GROUPS
templates.env.globals["CEMS"] = programmes.CEMS
templates.env.globals["PASSWORD_RULES"] = passwords.RULES
templates.env.globals["TICKET_CATEGORIES"] = categories.TICKET


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
    return db.get_user(user_id) if user_id else None


def go(path):
    return RedirectResponse(path, status_code=303)


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
                masters=programmes.MASTER, courses=db.all_courses(),
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

    db.set_enrolments(user_id, picked)

    code = db.new_code(user_id)
    # Person 2 replaces this print with a real e-mail. Until then the code is
    # in the terminal where the server runs.
    print(f"\n  code for {email} is {code}\n", flush=True)
    request.session["pending_id"] = user_id
    return go("/verify")


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
    if not db.check_code(user_id, code):
        return page(request, "verify.html", pending=db.get_user(user_id),
                    error="That code is not right. Try again.")
    request.session.pop("pending_id", None)
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
    code = db.new_code(user_id)
    print(f"\n  new code is {code}\n", flush=True)
    return go("/verify")


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
        code = db.new_code(user["id"])
        print(f"\n  code for {user['email']} is {code}\n", flush=True)
        request.session["pending_id"] = user["id"]
        return go("/verify")

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
    code = db.new_code(user["id"])
    print(f"\n  reset code for {email} is {code}\n", flush=True)
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
    if not db.check_code(user_id, "".join([d1, d2, d3, d4, d5, d6]).strip()):
        return fail("That code is not right. Try again.")

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

def tab_page(request, kind, q, scope="mine", cat="", day=""):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    tab = BY_KIND[kind]

    # Groups is the only tab that is narrowed to your own courses, because it
    # is the only one where the whole school would otherwise be in your list.
    mine = db.courses_of(me["id"]) if kind == "group" else []
    only_for = me["id"] if (kind == "group" and scope == "mine") else None

    cat = cat if categories.is_valid(cat) else ""
    rows = db.listings_of_type(kind, q or "", only_for=only_for,
                               category=cat or None)

    # Tickets are the one tab that is read by day, so they are grouped before
    # the page sees them. Everything else stays a plain list.
    days = by_day(rows, day) if kind == "ticket" else None

    return page(request, "listings.html", tab=tab, listings=rows, q=q or "",
                active=kind, me=me, scope=scope, my_courses=mine,
                days=days, cat=cat, open_day=day)


@app.get("/housing")
def housing(request: Request, q: str = ""):
    return tab_page(request, "housing", q)


@app.get("/tickets")
def tickets(request: Request, q: str = "", cat: str = "", day: str = ""):
    return tab_page(request, "ticket", q, cat=cat, day=day)


@app.get("/market")
def market(request: Request, q: str = ""):
    return tab_page(request, "item", q)


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

    # Your own programme first, because that is where your courses are.
    mine_first = sorted(
        db.all_courses(),
        key=lambda c: (c["programme"] != (me["programme"] or ""), c["programme"], c["name"]),
    )
    return page(request, "courses.html", courses=mine_first, chosen=chosen,
                back=back, me=me)


@app.post("/courses")
async def courses_save(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/start")
    form = await request.form()
    picked = [v for v in form.getlist("course_id") if str(v).isdigit()]
    db.set_enrolments(me["id"], picked)
    back = form.get("back") or "/profile"
    return go(back if str(back).startswith("/") else "/profile")


@app.post("/courses/new")
def courses_add(request: Request, code: str = Form(""), name: str = Form(""),
                back: str = Form("/profile")):
    """Add a course that is not on the list, and join it straight away."""
    me = me_or_none(request)
    if me is None:
        return go("/start")
    new_id = db.create_course(code, name)
    if new_id:
        db.enrol(me["id"], new_id)
    return go(f"/courses?back={back}")


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
                tab=BY_KIND[row["type"]], me=me)


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
                      event_date: str = Form(""),
                      event_time: str = Form(""),
                      place: str = Form(""),
                      address: str = Form(""),
                      quantity: str = Form(""),
                      course_id: str = Form(""),
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
        category=categories.clean(category) if kind == "ticket" else None,
        event_date=event_date.strip() or None,
        event_time=event_time.strip() or None,
        place=place.strip() or None,
        address=address.strip() or None,
        quantity=int(quantity) if quantity.strip().isdigit() else None,
        course_id=int(course_id) if (kind == "group" and course_id.strip().isdigit())
        else None,
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
                chat_count=len(db.conversations_of(me["id"])), me=me)
