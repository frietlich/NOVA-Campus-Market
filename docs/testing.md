# Tests

Every pull request and every push to main runs the whole suite on GitHub
(`.github/workflows/verify.yml`): install the hash-pinned packages, run the
tests, then check the packages for known vulnerabilities with pip-audit.

Run it on a laptop:

    python -m pip install -r requirements-test.txt
    python -m pytest tests -q
    python -m coverage run --source=app -m pytest tests -q && python -m coverage report

Nothing leaves the machine. Every test gets its own temporary database and
upload folder, `tests/conftest.py` blanks the mail, Claude and push keys
before the app is imported, and e-mail, Claude, Web Push and the ticket and
map sites are all replaced by stand-ins.

## What is tested where

| File | What it pins down |
|---|---|
| `test_passwords.py` | Each password rule at its exact boundary (7/8 and 30/31 characters), salted hashes, and stored values that must never let anybody in. |
| `test_accounts.py` | Every way signing up can be refused, without creating an account or losing the form; a second signup for an unfinished account; login that does not reveal who has an account. |
| `test_mailer.py` | Reading `.env` the way people write it, server settings winning over the file, the code e-mail itself, TLS before login, and the code never ending up in the log. |
| `test_search_and_filters.py` | Category, condition and price filters through the real pages, the edges of each price band, sorting, multi-word and label search, dates typed by hand, and links with values the page does not know. |
| `test_saved_and_chats.py` | The heart on an entry, the saved list, and archiving a chat on one side only. |
| `test_closing.py` | Entries with a date close at six the next morning, not at midnight. |
| `test_security.py` | Access control, CSRF origin checks, rate limits, single-use codes, uploads, escaping, cookies and headers in production. |
| `test_links_and_queue.py` | Housing and ticket links only from listed sites, the order of people asking, reading listing pages. |
| `test_ticket_import.py` | Filling a ticket from an event link, including redirects off the list and blocked pages. |
| `test_screenshots.py` | Filling an entry from screenshots, with Claude replaced by a stand-in. |
| `test_push.py` | Who gets a push for what, saved searches, watched events, and the on/off switches. |
| `test_maps.py` | Map links and addresses. |
| `test_course_catalogue.py` | The course list per programme. |
| `test_seed_lock.py` | The demo data never overwrites a real database. |

## Rules for new tests

* A test checks one behaviour and says which in its name.
* Go through the page (`TestClient`) when the page decides something, the
  database when only the database does. Do not test the same rule twice.
* Never call a real outside service. Replace it with `monkeypatch`.
* Reuse the `world` fixture from `test_security.py` for three verified,
  logged-in students instead of writing a new one.
