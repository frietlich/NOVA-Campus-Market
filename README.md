# Campus Market

Housing, tickets, things for sale and free spots in group projects, for verified
Nova students. A web app you can add to the home screen.

What it is and what it is not is settled in `docs/one-pager.docx`. Who builds
what is in `docs/tasks.docx`. Read both before you write code.

## Run it

You need Python 3.10 or newer. From this folder, once:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m app.seed

And every time you work:

    source .venv/bin/activate
    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000 in the browser.

`python -m app.seed` wipes the database and writes the fake students and entries
again. Run it whenever you want a clean start.

## Logging in

Two ways, and both work right now.

The real one is at `/signup`. Put in an address ending in `novasbe.pt`, and the
6-digit code is printed in the terminal where the server runs. There is no mail
provider wired up yet, so copy it from there.

The quick one is at `/dev`. Pick any fake student and you are that person. Use
this while building. It goes away once the real sign up is finished.

The student you are by default is Marco C., `20241234@novasbe.pt`.

## What is where

    app/main.py        every page and every form, nothing else
    app/db.py          every read and write of the database, nobody else writes SQL
    app/schema.sql     the five tables
    app/seed.py        the fake students and entries
    app/templates/     one file per screen, plus partials for the icons and the tab bar
    app/static/css/    one stylesheet for the whole app
    app/static/js/     the few bits of behaviour the pages need
    app/static/uploads/ photos people upload, not in git
    docs/              the one pager and the task split

## The seven tables

    users          a student, and whether the e-mail code was right
    courses        every course the school offers
    enrolments     which courses a student is taking
    listings       one entry, with a type of housing, ticket, item or group
    photos         the pictures of one entry
    conversations  one entry plus the one student who wrote about it
    messages       the lines inside a conversation

Several students can write about the same entry. Each of them gets a separate
conversation, and neither sees the other.

A course is a row, not a piece of text. A group entry points at one, so two
students can never write the same course two different ways.

## How Groups stays short

There are dozens of courses, so showing every group entry would be useless.
You pick your own courses once, and the Groups tab then shows only entries in
those courses. The toggle at the top switches to all courses when you want to
look wider, and search still works in both.

Only Groups works this way. Housing, Tickets and Market are untouched.

## The pages

    /signup                 put in a Nova address
    /verify                 the 6-digit code
    /dev                    development login
    /housing /tickets /market /groups
    /groups?scope=all       every course, not only yours
    /courses                pick the courses you are taking
    /listing/<id>           one entry
    /new?kind=housing       put something up
    /chats                  every conversation you are in
    /chat/<id>              one conversation
    /profile                you, and the entries you put up

## Rules we agreed on

Every student and every entry in the demo is invented. We use no Nova logo and
no Nova branding, and no real student data goes in.

## Adding to the home screen

Open the site in Safari on the iPhone, tap Share, then Add to Home Screen. It
then opens full screen with no address bar. On a plain `http` address some of
this behaves worse, so test it properly once the app is deployed.
