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

The real one starts at `/start`. Create an account with a `novasbe.pt` address
and a password, tick the courses you are taking, confirm the 6-digit code, and
you are in. Whoever skips the courses is asked once right after the code. After that you sign
in at `/login` with the address and the password. Forgotten passwords go
through `/forgot`, which sends a fresh code.

Without a mail account the code is printed in the terminal where the server
runs. Copy it from there. With one, it arrives by e-mail, see below.

The quick one is at `/dev`. Pick any fake student and you are that person. Use
this while building. It goes away once we are happy with the real one.

The student you are by default is Marco C., `58412@novasbe.pt`. Every demo
student has the password `Nova2026!`, which is why `app/seed.py` says so out
loud. They are invented people, so it is not a secret.

## Passwords

A password is never stored. `app/passwords.py` turns it into a salted hash with
PBKDF2, which comes with Python and is slow on purpose, and that hash is what
goes into the database. Checking a password repeats the calculation and
compares with `hmac.compare_digest`, so the time it takes never tells an
attacker how much of a guess was right.

The rules are in the same file, one function, which makes them easy to test.
At least 8 characters, at most 30, one capital letter, one number and one
special character.

## The code by e-mail

`app/mailer.py` sends the code. It reads its settings from a file called
`.env` in this folder, which is in `.gitignore` and never goes into git. Copy
`.env.example` to `.env` and fill it in.

For a Gmail account:

1. Turn on 2-step verification for that Google account.
2. Create an app password at https://myaccount.google.com/apppasswords.
   Google shows 16 letters, that is what goes into `SMTP_PASSWORD`.
3. Put the Gmail address into `SMTP_USER` and restart the server.

Never put the normal Gmail password in there, and never commit `.env`. Each
of us who wants real e-mails keeps their own.

Gmail sends a few hundred mails a day from a normal account, which is fine for
building and a small test. For the real launch we want a proper provider.

## How the code is protected

A 6-digit code is only a million possibilities, so it gets three limits.

* It works for 15 minutes.
* After 5 wrong tries it is dead and a new one has to be sent.
* A new one is sent at most once a minute per address.

The code is made with `secrets`, not `random`, because `random` is
predictable by design. All of it lives in `db.new_code` and `db.check_code`.

## What is where

    app/main.py        every page and every form, nothing else
    app/db.py          every read and write of the database, nobody else writes SQL
    app/programmes.py  the list of programmes the school offers
    app/passwords.py   the password rules and how a password is stored
    app/mailer.py      sending the 6-digit code, and reading .env
    app/categories.py  what a ticket can be for
    app/schema.sql     the five tables
    app/seed.py        the fake students and entries
    app/templates/     one file per screen, plus partials for the icons and the tab bar
    app/static/css/    one stylesheet for the whole app
    app/static/js/     the few bits of behaviour the pages need
    app/static/uploads/ photos people upload, not in git
    docs/              the one pager and the task split

## The nine tables

    users             a student, their programme, photo and hashed password,
                      whether the e-mail code was right, and the code itself
                      with when it was sent and how often it was guessed wrong
    courses           every course the school offers
    course_offerings  which programme a course belongs to, and how
    enrolments        which courses a student is taking
    listings          one entry, of type housing, ticket, item or group
    photos            the pictures of one entry
    saves             one student put a heart on one entry
    conversations     one entry plus the one student who wrote about it
    messages          the lines inside a conversation

Several students can write about the same entry. Each of them gets a separate
conversation, and neither sees the other.

A course is a row, not a piece of text. A group entry points at one, so two
students can never write the same course two different ways.

## Programmes and CEMS

The programme on a profile comes from one fixed list in `app/programmes.py`,
never from free text, so it always matches the programme on a course.

CEMS MIM is a double degree, you always do it on top of a master. The form
shows it in the dropdown and then asks which master it sits on, but we store
the master in `users.programme` and a plain yes or no in `users.cems`. That
way every other part of the app reads a normal programme and the special case
lives in one place.

## How Tickets is read by day

A long list of tickets sorted by date is unusable, because the day you care
about is buried. So Tickets is not one list, it is one block per day with the
date as a heading.

Inside a day, two tickets are the same event when they are at the same time
and the same place. The name does not count, because six students selling for
the same night will call their entry six different things. The short view then
shows one card per event with a note saying how many others are selling, so a
party with forty tickets cannot push the other events of that day off the
screen. `View all` opens the day in full, sorted by time and then by price.

Grouping only happens when there is something to protect. A day left with a
single event, which is what a category filter usually does, shows the tickets
themselves instead of one card standing in for all of them.

The chips above the list filter by category, which is the other half of the
same problem. Both live in the address, so a filtered day can be sent to
somebody as a link.

## How Market is put in order

Tickets has a deadline and Market has none, so the day something went up says
almost nothing and there is no point grouping by it. What Market gets instead
is a line of two controls under the chips, a sort and a price. Everything
they do stands in the address, so a filtered list can be sent to somebody and
the back button does what you expect.

The price filter is steps and not two number fields, because nobody fills in
two number fields on a phone. Free is one of the steps rather than a switch
standing beside them. An entry with no price is free, and free counts as
being under every ceiling.

Above the list sits one row of new entries that you swipe along. It is the
same entries as in the list below, which is the point, it is a shortcut to
what arrived this week. It shows on one condition, that nothing is set.
No search, no category, Newest, Any price. Pick any one of those and the list
itself is the answer, and an unfiltered row next to a filtered list would
only say something that is not true of the list.

A thing for sale carries a condition of its own, New, Like new, Used or Well
used. It used to be typed into the grey line, where nothing could be done
with it.

## Saving something

The heart sits top right on every entry, in all four tabs. Your own entries
have none, saving your own thing says nothing. What you saved waits under
SAVED on your profile, newest heart first. A saved ticket for a day that is
over drops out by itself.

An entry says how many students saved it, next to how many viewed it. The
number only. Who saved it is never shown to anybody, which keeps the heart a
thing you press for yourself.

The button is a real form, so it works with JavaScript switched off, the page
simply comes back fresh. With JavaScript it answers in JSON and the heart
fills in on the spot.

## How Groups stays short

There are dozens of courses, so showing every group entry would be useless.
You pick your own courses once, and the Groups tab then shows only entries in
those courses. The toggle at the top switches to all courses when you want to
look wider, and search still works in both.

Only Groups works this way. Housing, Tickets and Market are untouched.

## The pages

    /start                  create an account, or log in
    /join                   name, programme, photo, e-mail and password
    /verify                 the 6-digit code
    /login                  e-mail and password
    /forgot                 a new password, by code
    /dev                    development login
    /housing /tickets /market /groups
    /groups?scope=all       every course, not only yours
    /courses                pick the courses you are taking
    /profile/edit           name, programme and photo
    /profile/password       change your password
    /listing/<id>           one entry
    /new?kind=housing       put something up
    /chats                  every conversation you are in
    /chat/<id>              one conversation
    /profile                you, and the entries you put up

## Where a ticket is

A ticket carries two things about the place, and they do different jobs.

`place` is the venue as everyone says it, Urban Beach or Jamor. It is what
shows on the ticket at the top of the page, and together with the date and
the time it is what decides whether two entries are the same event.

`address` is the street address off the ticket. It sits under the description
with a link that hands it to whatever map the phone already has. We draw no
map ourselves, which is why this costs one column and one line of markup
instead of a mapping library and an API key.

## Not now, but worth knowing

Things we left out on purpose. If somebody has time at the end, this is the
list, in the order that pays off most.

A real map on the page instead of a link out, which needs a mapping library,
an API key and a way to turn an address into coordinates. Tests, one file per
area, which is the biggest single gap against the plan. Filters for Housing
the way Market has them. Editing an entry you already put up. The mail
provider, so the 6-digit code arrives by e-mail instead of in the terminal.

## Rules we agreed on

Every student and every entry in the demo is invented. We use no Nova logo and
no Nova branding, and no real student data goes in.

## Adding to the home screen

Open the site in Safari on the iPhone, tap Share, then Add to Home Screen. It
then opens full screen with no address bar. On a plain `http` address some of
this behaves worse, so test it properly once the app is deployed.

## Official 2026/27 courses (course selection enhancement)

The catalogue lives in `app/data/course_catalogue.csv` (808 source entries, six MSc
programme groups). The database stores one course record per code and programme-specific
classifications in `course_offerings`. The exceptional code 2743 has two official
IDPP titles, stored separately while both are *displayed* as 2743; `TBD` is also
displayed verbatim. The catalogue is imported safely at app startup.

Students can select predefined courses on **My courses** and at signup. They cannot
create a course. Unsupported programmes have no predefined offerings yet.
The existing seed command still **deletes the local database**, so do not run it on
real or shared data. This branch does not change other contributors' code.
