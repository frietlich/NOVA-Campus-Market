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

from . import db

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


def pretty_date(iso_date):
    if not iso_date:
        return ""
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%-d %b %Y")


templates.env.filters["initials"] = initials
templates.env.filters["money"] = money
templates.env.filters["when"] = when
templates.env.filters["month"] = month
templates.env.filters["ago"] = ago
templates.env.globals["event_badge"] = event_badge
templates.env.globals["pretty_date"] = pretty_date
templates.env.globals["TABS"] = TABS


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
    return go("/housing" if me_or_none(request) else "/signup")


@app.get("/signup")
def signup_form(request: Request, error: str = ""):
    return page(request, "signup.html", error=error)


@app.post("/signup")
def signup(request: Request, email: str = Form(""), name: str = Form("")):
    email = email.strip().lower()
    if not db.is_nova_email(email):
        return page(request, "signup.html",
                    error="Only a novasbe.pt address can join.", email=email, name=name)
    user = db.get_user_by_email(email)
    if user is None:
        if not name.strip():
            return page(request, "signup.html",
                        error="Please put in your name as well.", email=email)
        user_id = db.create_user(email, name.strip())
    else:
        user_id = user["id"]

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
        return go("/signup")
    return page(request, "verify.html", pending=db.get_user(user_id), error=error)


@app.post("/verify")
def verify(request: Request, d1: str = Form(""), d2: str = Form(""), d3: str = Form(""),
           d4: str = Form(""), d5: str = Form(""), d6: str = Form("")):
    user_id = request.session.get("pending_id")
    if not user_id:
        return go("/signup")
    code = "".join([d1, d2, d3, d4, d5, d6]).strip()
    if not db.check_code(user_id, code):
        return page(request, "verify.html", pending=db.get_user(user_id),
                    error="That code is not right. Try again.")
    request.session.pop("pending_id", None)
    request.session["user_id"] = user_id
    return go("/housing")


@app.post("/verify/resend")
def resend(request: Request):
    user_id = request.session.get("pending_id")
    if not user_id:
        return go("/signup")
    code = db.new_code(user_id)
    print(f"\n  new code is {code}\n", flush=True)
    return go("/verify")


@app.get("/dev")
def dev_form(request: Request):
    """Development login. Delete this page once the real one works."""
    return page(request, "dev.html", users=db.all_users())


@app.post("/dev")
def dev_login(request: Request, user_id: int = Form(...)):
    request.session.clear()
    request.session["user_id"] = user_id
    return go("/housing")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return go("/signup")


# --------------------------------------------------------------- the four tabs

def tab_page(request, kind, q, scope="mine"):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
    tab = BY_KIND[kind]

    # Groups is the only tab that is narrowed to your own courses, because it
    # is the only one where the whole school would otherwise be in your list.
    mine = db.courses_of(me["id"]) if kind == "group" else []
    only_for = me["id"] if (kind == "group" and scope == "mine") else None

    rows = db.listings_of_type(kind, q or "", only_for=only_for)
    return page(request, "listings.html", tab=tab, listings=rows, q=q or "",
                active=kind, me=me, scope=scope, my_courses=mine)


@app.get("/housing")
def housing(request: Request, q: str = ""):
    return tab_page(request, "housing", q)


@app.get("/tickets")
def tickets(request: Request, q: str = ""):
    return tab_page(request, "ticket", q)


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
        return go("/signup")
    chosen = {c["id"] for c in db.courses_of(me["id"])}

    # Your own programme first, because that is where your courses are.
    mine_first = sorted(
        db.all_courses(),
        key=lambda c: (c["programme"] != (me["course"] or ""), c["programme"], c["name"]),
    )
    return page(request, "courses.html", courses=mine_first, chosen=chosen,
                back=back, me=me)


@app.post("/courses")
async def courses_save(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
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
        return go("/signup")
    new_id = db.create_course(code, name)
    if new_id:
        db.enrol(me["id"], new_id)
    return go(f"/courses?back={back}")


# ------------------------------------------------------------- one listing

@app.get("/listing/{listing_id}")
def listing_detail(request: Request, listing_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
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
        return go("/signup")
    db.close_listing(listing_id, me["id"])
    return go("/profile")


@app.post("/listing/{listing_id}/reopen")
def listing_reopen(request: Request, listing_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
    db.reopen_listing(listing_id, me["id"])
    return go("/profile")


@app.post("/listing/{listing_id}/chat")
def listing_chat(request: Request, listing_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
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
        return go("/signup")
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
                      event_date: str = Form(""),
                      spots: str = Form(""),
                      course_id: str = Form(""),
                      description: str = Form(""),
                      photos: List[UploadFile] = File(default=[])):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
    if kind not in BY_KIND:
        kind = "housing"

    mine = db.courses_of(me["id"]) if kind == "group" else []

    if not title.strip():
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="An entry needs a title.")

    if kind == "group" and not course_id.strip().isdigit():
        return page(request, "new.html", tab=BY_KIND[kind], me=me, active=kind,
                    my_courses=mine, error="Pick the course this group is for.")

    listing_id = db.create_listing(
        owner_id=me["id"],
        kind=kind,
        title=title.strip(),
        description=description.strip(),
        price=float(price) if price.strip() else None,
        info=info.strip(),
        event_date=event_date.strip() or None,
        spots=int(spots) if spots.strip().isdigit() else None,
        course_id=int(course_id) if (kind == "group" and course_id.strip().isdigit())
        else None,
    )

    position = 0
    for upload in photos or []:
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

    return go(f"/listing/{listing_id}")


# -------------------------------------------------------------------- chats

@app.get("/chats")
def chats(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
    return page(request, "chats.html", conversations=db.conversations_of(me["id"]),
                active="chats", me=me)


@app.get("/chat/{conv_id}")
def chat(request: Request, conv_id: int):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
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
        return go("/signup")
    conv = db.get_conversation(conv_id)
    if not db.can_see_conversation(conv, me["id"]):
        return page(request, "missing.html", active="chats")
    db.send_message(conv_id, me["id"], body)
    return go(f"/chat/{conv_id}")


# ------------------------------------------------------------------ profile

@app.get("/profile")
def profile(request: Request):
    me = me_or_none(request)
    if me is None:
        return go("/signup")
    mine = db.listings_of_user(me["id"])
    return page(request, "profile.html", mine=mine,
                my_courses=db.courses_of(me["id"]),
                chat_count=len(db.conversations_of(me["id"])), me=me)
