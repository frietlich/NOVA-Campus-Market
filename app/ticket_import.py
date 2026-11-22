"""Filling the ticket form from the link to the event.

Whoever sells a ticket bought it somewhere, on Luma, DICE, Xceed, BOL and the
like. That page already says what the event is called, when it starts, where
it is and what a ticket cost. Instead of typing all of it again, the seller
pastes the link and the form fills itself in. They check it and put their own
price before publishing.

Almost every ticket site writes the event into its page a second time, in a
form made for search engines (schema.org Event, as JSON-LD). That is what we
read. It is the same on every site, so one reader covers all of them, and a
site that changes its design does not break it.

Only links to the sites below are ever fetched, every redirect is checked
again, and nothing but the page itself is read.

Where the address comes from is worth knowing, because the sites disagree.
Most write a proper street into their structured block. Luma writes the
name of the venue there instead, and Xceed leaves out the post code, so
whatever coordinates the page carries are turned into an address the same
way a pasted maps link is, and the street the page gave is kept where it
agrees. Checked by hand on 2026-11-22: Luma, DICE, Xceed, BOL, Eventbrite
and Shotgun all come back with a full address.

The rest cannot be read at all, and not for anything we do. Fever,
Resident Advisor and Fourvenues refuse apps outright, Ticketline refuses
the connection, and Blueticket sends every visitor into a waiting room on
another site. Then we say so and the seller types it in.
"""

import html
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

from . import maps

try:
    from zoneinfo import ZoneInfo
    LISBON = ZoneInfo("Europe/Lisbon")
except Exception:  # no time zone data on this machine
    LISBON = timezone.utc

# The domain we check against, and the name we show. A subdomain counts too,
# so www.eventbrite.pt is Eventbrite.
PLATFORMS = [
    ("luma.com",           "Luma"),
    ("lu.ma",              "Luma"),
    ("dice.fm",            "DICE"),
    ("xceed.me",           "Xceed"),
    ("bol.pt",             "BOL"),
    ("eventbrite.pt",      "Eventbrite"),
    ("eventbrite.com",     "Eventbrite"),
    ("eventbrite.co.uk",   "Eventbrite"),
    ("eventbrite.de",      "Eventbrite"),
    ("eventbrite.es",      "Eventbrite"),
    ("eventbrite.fr",      "Eventbrite"),
    ("eventbrite.it",      "Eventbrite"),
    ("eventbrite.nl",      "Eventbrite"),
    ("shotgun.live",       "Shotgun"),
    ("ra.co",              "Resident Advisor"),
    ("feverup.com",        "Fever"),
    ("fourvenues.com",     "Fourvenues"),
    ("ticketline.sapo.pt", "Ticketline"),
    ("blueticket.meo.pt",  "Blueticket"),
]
PLATFORM_NAMES = sorted({name for _, name in PLATFORMS})

LINK_LIMIT = 500
PAGE_LIMIT = 4_000_000
TIMEOUT = 8
MAX_REDIRECTS = 4

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15")


# ---------------------------------------------------------------- the link

def platform_for_host(host):
    """The name of the ticket site a host belongs to, or None."""
    host = (host or "").lower().rstrip(".")
    for domain, name in PLATFORMS:
        if host == domain or host.endswith("." + domain):
            return name
    return None


def platform_of(url):
    """The site a stored link is on, as a dict, or None.

    The twin of housing.platform_of, down to the keys, because the entry
    page draws the two the same way and should not have to know which kind
    of entry it is looking at.
    """
    from urllib.parse import urlsplit

    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    for domain, name in PLATFORMS:
        if host == domain or host.endswith("." + domain):
            return {"name": name, "domain": domain, "url": url}
    return None


def clean_url(text):
    """A pasted link made safe, or None when we do not take it.

    It has to be on one of the sites above. https is added when it is
    missing, http becomes https, and anything with a password, a strange
    port or spaces in it is refused.
    """
    text = (text or "").strip()
    if not text or len(text) > LINK_LIMIT or any(c.isspace() for c in text):
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.username or parts.password:
        return None
    if port not in (None, 80, 443):
        return None
    if not platform_for_host(parts.hostname):
        return None
    return urlunsplit(("https", parts.hostname.lower(), parts.path or "/",
                       parts.query, ""))


# ------------------------------------------------------------- the fetching

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """We follow redirects ourselves, so each one is checked against the list."""
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def fetch(url):
    """Get one page. Gives back (status, html).

    A redirect is only followed when it stays on a site from the list, so a
    link can never be used to make our server open anything else. Raises
    ValueError for a redirect that leaves the list, OSError when the site
    cannot be reached.
    """
    for _ in range(MAX_REDIRECTS + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en,pt;q=0.8",
        })
        try:
            res = _opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                nxt = clean_url(urljoin(url, e.headers["Location"]))
                if not nxt:
                    raise ValueError("redirect off the list")
                url = nxt
                continue
            return e.code, ""
        with res:
            charset = res.headers.get_content_charset() or "utf-8"
            return res.status, res.read(PAGE_LIMIT).decode(charset, "replace")
    raise ValueError("too many redirects")


def looks_blocked(status, page):
    """A site that refuses apps answers 403 or 429, or sends a puzzle page."""
    if status in (401, 403, 405, 429, 503):
        return True
    head = (page or "")[:20000].lower()
    return any(w in head for w in ("datadome", "captcha", "are you a robot",
                                   "access denied", "pardon our interruption",
                                   "just a moment..."))


# -------------------------------------------------------------- the reading

def _events_in(page):
    """Every schema.org Event written into the page, in the order found."""
    found = []
    for blob in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>",
                           page, re.S | re.I):
        try:
            data = json.loads(blob.strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            item = stack.pop(0)
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            kinds = item.get("@type")
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if any(isinstance(k, str) and k.endswith("Event") for k in kinds):
                found.append(item)
            for key in ("@graph", "itemListElement", "item", "mainEntity"):
                if key in item:
                    stack.append(item[key])
    return found


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def _text(value, limit):
    if not isinstance(value, str):
        return ""
    value = re.sub(r"\s+", " ", html.unescape(value)).strip()
    return value[:limit].rstrip()


def _when(start):
    """'2026-12-09T21:30:00+00:00' as ('2026-12-09', '21:30') in Lisbon time.

    A time without a zone is taken as Lisbon time already, which is what the
    Portuguese sites write.
    """
    if not isinstance(start, str) or not start.strip():
        return None, None
    start = start.strip()
    only_date = re.fullmatch(r"\d{4}-\d{2}-\d{2}", start)
    if only_date:
        return start, None
    clean = re.sub(r"(\.\d+)", "", start).replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(clean)
    except ValueError:
        return None, None
    if moment.tzinfo is not None:
        moment = moment.astimezone(LISBON)
    return moment.date().isoformat(), moment.strftime("%H:%M")


def _point(location):
    """(lat, lng) out of a schema.org Place, or None."""
    if not isinstance(location, dict):
        return None
    for holder in (location.get("geo"), location):
        if not isinstance(holder, dict):
            continue
        try:
            lat = float(holder["latitude"])
            lng = float(holder["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    return None


def _address(location):
    """One line of address out of a schema.org Place."""
    if not isinstance(location, dict):
        return ""
    addr = location.get("address")
    if isinstance(addr, str):
        return _text(addr, 120)
    if not isinstance(addr, dict):
        return ""
    street = _text(addr.get("streetAddress"), 80)
    code = _text(addr.get("postalCode"), 80)
    town = _text(addr.get("addressLocality"), 80)
    # Some sites put the whole address into streetAddress already, and then
    # the code and the town are in there twice.
    if code and code.lower() in street.lower():
        code = ""
    if town and town.lower() in street.lower():
        town = ""
    # The post code and the town are one thing, "1600-583 Lisboa", not two.
    # Split by a comma they read as a list of places.
    parts = [street, " ".join(bit for bit in (code, town) if bit)]
    # "1950-142 Lisbon, Lisbon, Portugal" once is enough.
    pieces = []
    for piece in ", ".join(bit for bit in parts if bit).split(","):
        piece = piece.strip()
        if piece and not any(piece.lower() in p.lower() for p in pieces):
            pieces.append(piece)
    return maps.plain_address(", ".join(pieces))


def _price(offers):
    """The lowest price a ticket was sold for, in euros, or None."""
    prices = []
    for offer in offers if isinstance(offers, list) else [offers]:
        if not isinstance(offer, dict):
            continue
        if offer.get("priceCurrency") not in (None, "", "EUR"):
            continue
        for key in ("price", "lowPrice"):
            try:
                value = float(str(offer.get(key)).replace(",", "."))
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 5000:
                prices.append(value)
    if not prices:
        return None
    low = min(prices)
    return int(low) if low == int(low) else round(low, 2)


# Words that say which category a ticket belongs in. First match wins, so
# the more certain ones come first.
_CATEGORY_WORDS = [
    ("sports",  r"\b(football|futebol|benfica|sporting|porto fc|match|jogo|"
                r"tennis|t[eé]nis|basket|rugby|surf|marathon|maratona|padel)\b"),
    ("travel",  r"\b(trip|viagem|tour|excurs[aã]o|weekend in|boat trip|road trip)\b"),
    ("party",   r"\b(party|festa|club|clube|dj|rave|techno|electronik|electronic|"
                r"house music|afterparty|"
                r"after party|boat party|pub crawl|open bar|night)\b"),
    ("concert", r"\b(concert|concerto|live|ao vivo|tour \d{4}|festival|orchestra|"
                r"orquestra|band|banda)\b"),
    ("culture", r"\b(theat(er|re)|teatro|comedy|com[eé]dia|stand-?up|museum|museu|"
                r"exhibition|exposi[cç][aã]o|cinema|film|ballet|opera|talk|conference|"
                r"summit|workshop)\b"),
]

_TYPE_CATEGORY = {
    "SportsEvent": "sports", "MusicEvent": "concert", "Festival": "concert",
    "DanceEvent": "party", "SocialEvent": "party", "TheaterEvent": "culture",
    "ComedyEvent": "culture", "ScreeningEvent": "culture",
    "ExhibitionEvent": "culture", "VisualArtsEvent": "culture",
    "LiteraryEvent": "culture", "EducationEvent": "culture",
    "BusinessEvent": "culture",
}


# Sites that only sell nights out. When nothing else decides it, that is Party.
_NIGHTLIFE_SITES = {"Xceed", "Shotgun", "Fourvenues"}


def _category(event, words, site=None):
    """The ticket category, from the words first and the event type second.

    The words win because sites call nearly everything a MusicEvent, also a
    club night that students would look for under Party.
    """
    for key, pattern in _CATEGORY_WORDS:
        if re.search(pattern, words, re.I):
            return key
    kinds = event.get("@type")
    for kind in kinds if isinstance(kinds, list) else [kinds]:
        if kind in _TYPE_CATEGORY:
            return _TYPE_CATEGORY[kind]
    return "party" if site in _NIGHTLIFE_SITES else None


def _meta(page, name):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(name)
                  + r'["\'][^>]*content=["\']([^"\']*)', page, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']'
                      + re.escape(name), page, re.I)
    return html.unescape(m.group(1)).strip() if m else ""


_SITE_WORDS = (r"\b(luma|dice|xceed|eventbrite|bol|shotgun|fever|ticketline|"
               r"blueticket|tickets?|bilhetes?)\b")


def _clean_title(title):
    """The event name without ' | DICE', ' · Luma', ' Tickets' and the like.

    Only the tail pieces that name a site are cut, so 'THE GIFT | CORAL
    EXPANDED' stays whole.
    """
    parts = re.split(r"\s+[|·—–]\s+", _text(title, 300))
    while len(parts) > 1 and re.search(_SITE_WORDS, parts[-1], re.I):
        parts.pop()
    title = re.sub(r"\s+(tickets?|bilhetes?)$", "", " | ".join(parts), flags=re.I)
    return title[:60].rstrip()


def parse_event_page(page, site=None):
    """Read an event page into form fields. Only what is found comes back.

    The fields are the ones on the ticket form: title, category, event_date,
    event_time, place, address and price.
    """
    found = {}
    events = _events_in(page or "")
    if events:
        event = events[0]
        location = _first(event.get("location"))
        name = _text(event.get("name"), 200)
        if name:
            found["title"] = _clean_title(name)
        day, time = _when(event.get("startDate"))
        if day:
            found["event_date"] = day
        if time and time != "00:00":
            found["event_time"] = time
        if isinstance(location, dict):
            venue = _text(location.get("name"), 60)
            # Luma writes "Tasca Bica, Lisbon". The town is not the venue.
            venue = re.sub(r",\s*(lisbon|lisboa|porto|cascais|oeiras)$", "", venue, flags=re.I)
            if venue:
                found["place"] = venue
            # Where the place is, when the page says. Luma gives the
            # coordinates of every venue and writes the venue's name into
            # the street field, so the one usable thing in there is the
            # pair of numbers. It is handed up rather than looked up here,
            # because reading a page and calling a service are two jobs
            # and this one does not touch the network.
            point = _point(location)
            if point:
                found["_point"] = point
            address = _address(location)
            # A line with no number anywhere in it is a name, not an
            # address. Some pages put the venue, or the event itself, where
            # the street belongs, and a wrong address that fills itself in
            # is worse than an empty box: the box stops asking to be looked
            # at, and the one thing a ticket has to get right is where to
            # turn up. A street number or a post code is what tells the two
            # apart, and in Lisbon an address carries one or the other.
            if address and not any(ch.isdigit() for ch in address):
                address = ""
            if address and address.lower() != (location.get("name") or "").lower():
                found["address"] = address
        elif isinstance(location, str):
            found["place"] = _text(location, 60)
        price = _price(event.get("offers"))
        if price is not None:
            found["price"] = price
        words = " ".join([name, _text(event.get("description"), 2000)])
        category = _category(event, words, site)
        if category:
            found["category"] = category
        return found

    # No structured event: the title of the page is still better than nothing.
    title = _meta(page or "", "og:title")
    if title:
        found["title"] = _clean_title(title)
    return found


# ----------------------------------------------------------------- one call

def autofill(url):
    """Everything the form needs, as a dict that goes straight out as JSON.

    ok      True when at least one field was read
    site    the name of the ticket site
    fields  the form fields that were read
    reason  why nothing came back: site, blocked, unreachable or empty
    """
    link = clean_url(url)
    if not link:
        return {"ok": False, "reason": "site"}
    site = platform_for_host(urlsplit(link).hostname)
    try:
        status, page = fetch(link)
    except ValueError:
        return {"ok": False, "reason": "site", "site": site}
    except Exception:
        return {"ok": False, "reason": "unreachable", "site": site}
    if looks_blocked(status, page):
        return {"ok": False, "reason": "blocked", "site": site}
    if status != 200:
        return {"ok": False, "reason": "unreachable", "site": site}
    fields = parse_event_page(page, site)

    # The page knew where the place is but not what to call the street.
    # Luma does this with every venue: the street field holds the name of
    # the bar. The coordinates are good, so they are turned into a real
    # address the same way a maps link is.
    point = fields.pop("_point", None)
    said = fields.get("address") or ""
    if point and not maps.POST_CODE.search(said):
        found = maps.address_at(*point)
        if found:
            # What the page said about the street, where it said anything,
            # with the part it left out filled in. See maps.combine.
            fields["address"] = maps.combine(said, found)

    return {"ok": bool(fields), "site": site, "fields": fields,
            "reason": "" if fields else "empty"}
