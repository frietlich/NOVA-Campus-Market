"""Everything the Housing tab can be asked about.

Housing is the one tab where people arrive knowing what they want, so it is
also the one tab with a real filter panel. Every list in here is used three
times over, by the form that writes a place up, by the panel that searches
for one, and by the check that stops anything we do not know from being
stored. Change a list here and all three follow.
"""

# What kind of place it is. Private room is deliberately not in here. A
# private room is a room in a shared flat, so it would be the same thing
# twice. Whether your room is your own is a feature of the entry instead.
KINDS = [
    ("shared_flat", "Shared flat"),
    ("studio",      "Studio"),
    ("whole_flat",  "Whole flat"),
    ("other",       "Other"),
]
KIND_LABELS = dict(KINDS)

# Where it is. The campus is in Carcavelos, and the list runs roughly by how
# far out it gets from there.
AREAS = [
    ("carcavelos", "Carcavelos"),
    ("parede",     "Parede"),
    ("sao_pedro",  "São Pedro"),
    ("oeiras",     "Oeiras"),
    ("cascais",    "Cascais"),
    ("lisboa",     "Lisboa"),
    ("other",      "Other"),
]
AREA_LABELS = dict(AREAS)

# What the place comes with. Stored as a comma separated list of these keys
# in one column, because a tick box is not worth a table of its own in a
# project this size. The icon is the Tabler name the page draws.
FEATURES = [
    ("furnished",        "Furnished",        "sofa"),
    ("own_bathroom",     "Own bathroom",     "bath"),
    ("own_room",         "Own room",         "door"),
    ("desk",             "Desk",             "device-desktop"),
    ("wifi",             "Wifi included",    "wifi"),
    ("washing_machine",  "Washing machine",  "wash-machine"),
    ("dishwasher",       "Dishwasher",       "dishwasher"),
    ("balcony",          "Balcony",          "building-arch"),
    ("air_conditioning", "Air conditioning", "air-conditioning"),
    ("parking",          "Parking",          "car"),
    ("pets",             "Pets allowed",     "dog"),
    # Added later. Heating is the one nobody thinks to ask about until
    # January, and in a Lisbon flat it is often simply not there. The rest
    # are the things a student carries up the stairs or wishes they had.
    ("heating",          "Heating",          "flame"),
    ("oven",             "Oven",             "cooker"),
    ("dryer",            "Dryer",            "wind"),
    ("elevator",         "Elevator",         "elevator"),
    ("bike_storage",     "Bike storage",     "bike"),
    ("garden",           "Garden",           "plant"),
]
FEATURE_LABELS = {key: name for key, name, _ in FEATURES}
FEATURE_ICONS = {key: icon for key, _, icon in FEATURES}
FEATURE_KEYS = set(FEATURE_LABELS)

# Rent per month. Key, what the button says, floor, ceiling. The steps are
# high because a whole flat for four goes well past a thousand, and because
# a band nobody can reach is a band nobody presses.
# Five, so the row fits on one line of a phone. The step at 1250 went,
# because between a thousand and above there was nothing a student was
# choosing between.
RENT_BANDS = [
    ("",      "Any",      None, None),
    ("450",   "to 450",   None, 450),
    ("750",   "to 750",   None, 750),
    ("1000",  "to 1000",  None, 1000),
    ("1000+", "above",    1000, None),
]
RENT_LABELS = {key: name for key, name, _, _ in RENT_BANDS}
RENT_BY_KEY = {band[0]: band for band in RENT_BANDS}

# How long to the campus. It runs to a full hour because from Lisbon that is
# what it honestly takes.
# Ten minutes went, because the places that close are rare enough to find
# by eye. An hour and a half came in, because half of what gets offered is
# in Lisbon and from Lisbon to Carcavelos that is the honest number.
CAMPUS_BANDS = [
    ("",   "Any",       None),
    ("30", "30 min",    30),
    ("45", "45 min",    45),
    ("60", "1 hour",    60),
    ("90", "1.5 hours", 90),
]
CAMPUS_LABELS = {key: name for key, name, _ in CAMPUS_BANDS}
CAMPUS_BY_KEY = {band[0]: band for band in CAMPUS_BANDS}

# How long you want to stay. It filters on the minimum the place asks for,
# so wanting a semester hides everything that insists on a year. This is the
# one that catches people on exchange out.
STAY_BANDS = [
    ("",     "Any",        None),
    ("5",    "A semester", 5),
    ("12",   "A year",     12),
    ("24",   "Longer",     24),
]
STAY_LABELS = {key: name for key, name, _ in STAY_BANDS}
STAY_BY_KEY = {band[0]: band for band in STAY_BANDS}

# Who else lives there. Nobody counts flatmates one by one when they are
# looking, they decide between living alone, a small flat and a big one.
MATES_BANDS = [
    ("",  "Any",      None),
    ("0", "Alone",    0),
    ("2", "1 or 2",   2),
    ("3", "3 or more", None),
]
MATES_LABELS = {key: name for key, name, _ in MATES_BANDS}
MATES_BY_KEY = {band[0]: band for band in MATES_BANDS}

SORTS = [
    ("",     "Move in soonest"),
    ("low",  "Rent low to high"),
    ("high", "Rent high to low"),
]
SORT_KEYS = {key for key, _ in SORTS}
SORT_LABELS = dict(SORTS)


def clean_kind(key):
    key = (key or "").strip().lower()
    return key if key in KIND_LABELS else None


def clean_area(key):
    key = (key or "").strip().lower()
    return key if key in AREA_LABELS else None


def clean_features(values):
    """Take what the form ticked and give back a string we can store.

    The order is the order of the list above and not the order they arrived
    in, so two entries with the same ticks store the same string.
    """
    chosen = set()
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip().lower()
            if part in FEATURE_KEYS:
                chosen.add(part)
    return ",".join(key for key, _, _ in FEATURES if key in chosen)


def feature_list(stored):
    """The stored string back as a list of key and label and icon."""
    have = {p.strip() for p in (stored or "").split(",") if p.strip()}
    return [(key, name, icon) for key, name, icon in FEATURES if key in have]


def whole_number(text, limit):
    """A number somebody typed, or None. Anything silly is thrown away."""
    text = (text or "").strip()
    if not text.isdigit():
        return None
    value = int(text)
    return value if 0 < value <= limit else None


# ------------------------------------------------------------- other sites

# Many places are already up on a housing site. Instead of typing everything
# twice, the owner can add the link to the same place there, and the entry
# shows a button that opens it. Only these sites are accepted, so a link on
# our page can never send a student somewhere we do not know.
# The domain we check against, and the name we show.
PLATFORMS = [
    ("idealista.pt",       "Idealista"),
    ("idealista.com",      "Idealista"),
    ("uniplaces.com",      "Uniplaces"),
    ("spotahome.com",      "Spotahome"),
    ("housinganywhere.com", "HousingAnywhere"),
    ("imovirtual.com",     "Imovirtual"),
    ("olx.pt",             "OLX"),
    ("badi.com",           "Badi"),
    ("erasmusu.com",       "Erasmusu"),
]
PLATFORM_NAMES = sorted({name for _, name in PLATFORMS})
LINK_LIMIT = 500


def _platform_for_host(host):
    host = (host or "").lower().rstrip(".")
    for domain, name in PLATFORMS:
        if host == domain or host.endswith("." + domain):
            return domain, name
    return None


def clean_listing_url(text):
    """A link somebody pasted, made safe, or None when we do not take it.

    It has to be on one of the sites above. People paste links without the
    https part, so that is added, and http is turned into https. Anything
    with a password in it, a strange port or odd characters is refused.
    """
    from urllib.parse import urlsplit, urlunsplit

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
    if not _platform_for_host(parts.hostname):
        return None
    return urlunsplit(("https", parts.hostname.lower(), parts.path or "/",
                       parts.query, ""))


def platform_of(url):
    """The site a stored link is on, as a dict, or None.

    domain is what the button shows under the name, so a student always sees
    where the link goes before tapping it.
    """
    from urllib.parse import urlsplit

    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower()
    found = _platform_for_host(host)
    if not found:
        return None
    domain, name = found
    return {"name": name, "domain": domain, "url": url}


# ---------------------------------------------------------------- autofill

# Filling the form from an advert. Two ways in, one parser:
#   1. the link: the server fetches the page and reads it. Some sites
#      (Idealista above all) block that, then we say so honestly;
#   2. the text: the student copies the whole advert page and pastes it.
#      Nothing is downloaded, so this always works.
# Either way the student sees the filled form and checks it before publishing.

import html as _html
import json as _json
import re as _re
from datetime import date as _date

_MONTHS = {
    "jan": 1, "january": 1, "janeiro": 1, "feb": 2, "february": 2, "fevereiro": 2,
    "mar": 3, "march": 3, "março": 3, "marco": 3, "apr": 4, "april": 4, "abril": 4,
    "may": 5, "maio": 5, "jun": 6, "june": 6, "junho": 6, "jul": 7, "july": 7,
    "julho": 7, "aug": 8, "august": 8, "agosto": 8, "sep": 9, "sept": 9,
    "september": 9, "setembro": 9, "oct": 10, "october": 10, "outubro": 10,
    "nov": 11, "november": 11, "novembro": 11, "dec": 12, "december": 12,
    "dezembro": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

# Words in English and Portuguese, for each feature box on the form.
_FEATURE_WORDS = {
    "furnished": [r"\bfurnished\b", r"\bmobilad[oa]\b"],
    "own_bathroom": [r"private bathroom", r"en-?suite", r"own bathroom",
                     r"casa de banho privad", r"wc privativ"],
    "own_room": [r"private (bed)?room", r"single (bed)?room", r"quarto individual",
                 r"quarto privad", r"won't have to share the bedroom"],
    "desk": [r"\bdesk\b", r"secret[aá]ria"],
    "wifi": [r"\bwi-?fi\b", r"\binternet\b"],
    "washing_machine": [r"washing machine", r"m[aá]quina de lavar roupa", r"lavandaria"],
    "dishwasher": [r"dishwasher", r"m[aá]quina de lavar lou[cç]a"],
    "balcony": [r"\bbalcony\b", r"\bvaranda\b", r"\bterrace\b", r"\bterra[cç]o\b"],
    "air_conditioning": [r"air[- ]condition", r"ar condicionado"],
    "parking": [r"\bparking\b", r"\bgaragem\b", r"estacionamento"],
    "pets": [r"pets allowed", r"animais (de estima[cç][aã]o )?(s[aã]o )?permitidos",
             r"aceita animais"],
}
# Words that say a feature is NOT there, checked right before the match.
_NOT = r"(no|not|without|sem|n[aã]o)\s+(\w+\s+){0,2}$"

_AREA_WORDS = [
    ("carcavelos", r"carcavelos"), ("parede", r"\bparede\b"),
    ("sao_pedro", r"s[aã]o pedro( do estoril)?"), ("oeiras", r"oeiras"),
    ("cascais", r"cascais"), ("lisboa", r"\blisbo[an]\b"),
]

_STREET = (r"\b(Rua|R\.|Avenida|Av\.|Praceta|Largo|Travessa|Estrada|Alameda|Praça)"
           r"\s+(?:(?:d[aoe]s?|de)\s+)?[A-ZÀ-Ý0-9][^,\n|•·]{2,50}(,\s*\d{1,4}[A-Za-z]?)?")


def _money(text):
    """'1,500' or '1.500' or '1500,50' as a number of euros."""
    text = text.strip()
    if _re.fullmatch(r"\d{1,3}([.,]\d{3})+", text):
        return float(_re.sub(r"[.,]", "", text))
    return float(text.replace(",", "."))


def _next_date(day, month, year=None):
    today = _date.today()
    if year is None:
        year = today.year if (month, day) >= (today.month, today.day) else today.year + 1
    try:
        return _date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_listing_text(text):
    """Everything we can read off an advert, as form field names and values.

    Only what is found comes back; the student fills in the rest. It reads
    English and Portuguese, which is what Idealista, Uniplaces, Imovirtual
    and OLX show around here.
    """
    raw = _html.unescape(text or "")
    t = raw.lower()
    found = {}

    # Rent: "1,500 €/month", "€600 /month", "750 €/mês", "Preço 450 €"
    m = (_re.search(r"(\d{1,3}(?:[.,]\d{3})*|\d+)(?:[.,]\d{2})?\s*€\s*/\s*(month|mês|mes|m[eê]s|monat)", t)
         or _re.search(r"€\s*(\d{1,3}(?:[.,]\d{3})*|\d+)\s*/\s*(month|mês|mes|monat)", t)
         or _re.search(r"(?:rent|renda|pre[cç]o)\D{0,12}(\d{1,3}(?:[.,]\d{3})*|\d{3,4})\s*€", t))
    if m:
        value = _money(m.group(1))
        if 50 <= value <= 20000:
            found["price"] = int(value) if value == int(value) else value

    # Kind of place
    if _re.search(r"\b(studio|est[uú]dio)\b|\bt0\b", t):
        found["category"] = "studio"
    elif _re.search(r"\b(bedroom|room|quarto)\b", t) and not _re.search(
            r"\b(t[2-6]|whole (flat|apartment)|apartamento inteiro)\b.{0,40}(for rent|para arrendar|arrendar)", t):
        found["category"] = "shared_flat"
    elif _re.search(r"\bt[1-6]\b|\b(flat|apartment|apartamento|moradia|house)\b", t):
        found["category"] = "whole_flat"

    # Area: the first of our areas the advert mentions
    best = None
    for key, pattern in _AREA_WORDS:
        hit = _re.search(pattern, t)
        if hit and (best is None or hit.start() < best[0]):
            best = (hit.start(), key)
    if best:
        found["place"] = best[1]

    # Street address
    m = _re.search(_STREET, raw)
    if m:
        found["address"] = m.group(0).strip(" ,.")[:120]

    # Bills
    if _re.search(r"bills included|despesas inclu[ií]das|contas inclu[ií]das"
                  r"|utilities included|tudo inclu[ií]do", t):
        found["bills_included"] = "1"

    # Available from: "Available from January 1st", "From 24 Dec 2026",
    # "Available from: December 2026", "disponível a partir de 1 de janeiro"
    m = _re.search(r"(available|dispon[ií]vel|from|a partir de)\D{0,20}?"
                   r"(\d{1,2})(?!\d)(?:st|nd|rd|th)?\s+(?:de\s+)?(" + _MONTH_RE + r")\.?"
                   r"(?:\s+(?:de\s+)?(\d{4}))?", t)
    if m:
        when = _next_date(int(m.group(2)), _MONTHS[m.group(3)],
                          int(m.group(4)) if m.group(4) else None)
    else:
        m = _re.search(r"(available|dispon[ií]vel|from|a partir de)\D{0,20}?"
                       r"(" + _MONTH_RE + r")\.?(?:\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?)?"
                       r"(?:,?\s+(?:de\s+)?(\d{4}))?", t)
        when = (_next_date(int(m.group(3)) if m.group(3) else 1, _MONTHS[m.group(2)],
                           int(m.group(4)) if m.group(4) else None) if m else None)
    if when:
        found["available_from"] = when

    # Minimum stay: "Min stay: 30 nights", "estadia mínima de 6 meses"
    m = _re.search(r"(min(imum)?\.? stay|estadia m[ií]nima)\D{0,15}(\d{1,3})\s*"
                   r"(night|noite|day|dia|month|m[eê]s|mes|week|semana)", t)
    if m:
        n, unit = int(m.group(3)), m.group(4)
        months = (n if unit.startswith(("month", "mê", "me", "mes"))
                  else max(1, round(n / 30)) if unit.startswith(("night", "noite", "day", "dia"))
                  else max(1, round(n / 4)))
        if 1 <= months <= 36:
            found["months_min"] = str(months)

    # Features: only when the word is there and is not said to be missing
    feats = []
    for key, patterns in _FEATURE_WORDS.items():
        for pattern in patterns:
            hit = _re.search(pattern, t)
            if hit and not _re.search(_NOT, t[max(0, hit.start() - 25):hit.start()]):
                feats.append(key)
                break
    if feats:
        found["features"] = feats
    return found


def _meta(page, name):
    m = _re.search(r'<meta[^>]+(?:property|name)=["\']' + _re.escape(name)
                   + r'["\'][^>]*content=["\']([^"\']*)', page, _re.I)
    if not m:
        m = _re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']'
                       + _re.escape(name), page, _re.I)
    return _html.unescape(m.group(1)).strip() if m else ""


def _clean_title(title):
    title = _re.split(r"\s+[—|–-]\s+(idealista|https?://|uniplaces|imovirtual|olx|spotahome|"
                      r"housinganywhere|badi|erasmusu)", title, flags=_re.I)[0]
    return title.strip()[:90]


def _offer_price(page):
    """The rent the page itself states for search engines, or None.

    Most housing sites write the advert a second time as schema.org data
    (JSON-LD), with the price in offers.price. That number is the advert's
    own. The visible text is not safe: Uniplaces lists other flats under the
    advert, each with "1.000 €/month", while its own price stands without
    "/month", so reading the text took the price of a recommendation.
    """
    import json as _json
    for block in _re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
                             page, _re.S | _re.I):
        try:
            data = _json.loads(block)
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict) or item.get("@type") in ("Organization", "BreadcrumbList", "WebSite"):
                continue
            offers = item.get("offers")
            offer = offers[0] if isinstance(offers, list) and offers else offers
            if not isinstance(offer, dict):
                continue
            if str(offer.get("priceCurrency", "EUR")).upper() != "EUR":
                continue
            try:
                value = float(str(offer.get("price")).replace(",", "."))
            except (TypeError, ValueError):
                continue
            if 50 <= value <= 20000:
                return int(value) if value == int(value) else value
    return None


def parse_listing_page(page):
    """Read a whole advert page (its HTML) into form fields."""
    title = _meta(page, "og:title") or (
        _re.search(r"<title[^>]*>(.*?)</title>", page, _re.S | _re.I) or [None, ""])[1]
    about = _meta(page, "og:description") or _meta(page, "description")
    body = _re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page, flags=_re.S | _re.I)
    body = _re.sub(r"<[^>]+>", "\n", body)
    body = _re.sub(r"\n\s*\n+", "\n", _html.unescape(body))
    found = parse_listing_text(" \n".join([title, about, body]))
    own = _offer_price(page)
    if own is not None:
        found["price"] = own
    if title:
        found["title"] = _clean_title(_html.unescape(title))
    if about:
        found["description"] = about[:600]
    return found


def looks_blocked(status, page):
    """A site that refuses robots sends 403, or a puzzle page instead of the ad."""
    if status in (401, 403, 405, 429, 503):
        return True
    small = (page or "")[:20000].lower()
    return any(w in small for w in ("datadome", "captcha", "are you a robot",
                                    "access denied", "pardon our interruption"))


# Sites that refuse to be read by an app (tested November 2026): Idealista
# answers 403, Imovirtual a robot check. For them the form goes straight to
# the paste box instead of promising something that will not work.
BLOCKS_APPS = {"idealista.pt", "idealista.com", "imovirtual.com"}


def blocks_apps(url):
    found = platform_of(url)
    return bool(found) and found["domain"] in BLOCKS_APPS


class _CheckedRedirects(__import__("urllib.request").request.HTTPRedirectHandler):
    """Follow a redirect only to another page on one of our housing sites.

    Without this an allowed site could send our server on to any address,
    including machines inside the hosting network. Every hop is checked
    with the same rule as the link the student pasted.
    """
    max_redirections = 4

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not clean_listing_url(newurl):
            raise ValueError("redirect to a site that is not on the list")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_listing(link, timeout=8, limit=3_000_000):
    """Download one advert page. Returns (status, html). Raises on failure.

    link must already have passed clean_listing_url.
    """
    import urllib.error
    import urllib.request

    opener = urllib.request.build_opener(_CheckedRedirects)
    req = urllib.request.Request(link, headers={
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en,pt;q=0.8",
    })
    try:
        with opener.open(req, timeout=timeout) as res:
            charset = res.headers.get_content_charset() or "utf-8"
            return res.status, res.read(limit).decode(charset, "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


# How often one student may ask the server to read a link: enough to try a
# few adverts, not enough to turn our server into somebody's robot.
FETCH_LIMIT = 10
FETCH_WINDOW = 60 * 60          # seconds
_fetches = {}


def may_fetch(user_id, now=None):
    """True, and counts it, if this student is still under the limit."""
    import time
    now = time.time() if now is None else now
    recent = [t for t in _fetches.get(user_id, []) if now - t < FETCH_WINDOW]
    if len(recent) >= FETCH_LIMIT:
        _fetches[user_id] = recent
        return False
    recent.append(now)
    _fetches[user_id] = recent
    return True
