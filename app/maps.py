"""Turning a link to a map into a street address.

Somebody putting up a ticket or a room has the place open in maps already.
Copying the link is one tap; typing out a Portuguese address is not. So the
address box takes the link.

The catch is that a maps link almost never contains the address. Google
writes whatever was searched for after /place/, so searching an address
gives you the address but tapping a bar gives you "K Urban Beach Club".
The short link a phone makes when you press Share is an id and nothing
else. What they all carry, one way or another, is a pair of coordinates,
and a coordinate can be looked up.

So this does two things the page itself cannot. It follows a short link far
enough to see the real one, and it asks a lookup service what is at those
coordinates. The page tries first and only comes here when it has to, so a
link that already spells the address out costs nobody a request.

Only the hosts below are ever fetched and every redirect is checked again,
the same way the ticket import does it, so a pasted link can never make the
server open something else.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

# Where a maps link may point. A subdomain counts, so www.google.com and
# maps.google.de are both Google.
HOSTS = (
    "google.com", "google.pt", "google.de", "google.co.uk", "google.es",
    "google.fr", "google.it", "google.nl", "google.ie",
    "goo.gl", "app.goo.gl", "page.link",
    "apple.com",
    # Apple's own short domain, which is what an iPhone shares now. It is
    # not under apple.com, it is a top level domain of its own.
    "maps.apple",
)

# The lookup service. OpenStreetMap's own, free, and asks for one request a
# second and a user agent that says who is calling. It is told a pair of
# coordinates and nothing about who wants them.
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
AGENT = "CampusMarket/1.0 (university project, student marketplace)"

LINK_LIMIT = 500
TIMEOUT = 8
MAX_REDIRECTS = 4
BODY_LIMIT = 200_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are followed by hand, so each one is checked against HOSTS."""
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def host_allowed(host):
    host = (host or "").lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in HOSTS)


def clean_url(text):
    """A pasted maps link made safe, or None when we do not take it."""
    text = (text or "").strip()
    if not text or len(text) > LINK_LIMIT or any(c.isspace() for c in text):
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urllib.parse.urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.username or parts.password:
        return None
    if port not in (None, 80, 443):
        return None
    if not host_allowed(parts.hostname):
        return None
    return urllib.parse.urlunsplit(("https", parts.hostname.lower(),
                                    parts.path or "/", parts.query, ""))


# ------------------------------------------------------------ the short link

def follow(url):
    """Where a short link really points. Raises ValueError when it leaves HOSTS.

    Only the headers are wanted, so the body is read and thrown away rather
    than parsed. A short link answers with a redirect; anything else means
    there was nothing to follow and the link we started with is the one.
    """
    for _ in range(MAX_REDIRECTS + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": AGENT,
            "Accept": "text/html,application/xhtml+xml",
        })
        try:
            res = _opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as error:
            where = error.headers.get("Location") if error.headers else None
            if error.code in (301, 302, 303, 307, 308) and where:
                nxt = clean_url(urllib.parse.urljoin(url, where))
                if not nxt:
                    raise ValueError("redirect off the list")
                url = nxt
                continue
            return url
        with res:
            res.read(BODY_LIMIT)
            return url
    raise ValueError("too many redirects")


# ----------------------------------------------------------- the coordinates

# !3d38.7038144!4d-9.1554334 is the place itself, which is the one to use.
PLACE_AT = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
# @38.7040241,-9.1613882,16.42z is where the map happens to be centred, which
# is near the place but not on it. Second choice.
CENTRE_AT = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
PAIR = re.compile(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$")


def coordinates_in(url):
    """The (lat, lng) a maps link carries, or None.

    The place beats the centre of the map, and both beat a coordinate sitting
    in the query, which is usually the centre again.
    """
    for pattern in (PLACE_AT, CENTRE_AT):
        found = pattern.search(url)
        if found:
            return _sane(found.group(1), found.group(2))
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    except ValueError:
        return None
    for key in ("ll", "q", "daddr", "center", "sll", "coordinate"):
        for value in query.get(key, []):
            pair = PAIR.match(value)
            if pair:
                point = _sane(pair.group(1), pair.group(2))
                if point:
                    return point
    return None


def _sane(lat, lng):
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng
    return None


# ------------------------------------------------- the address in the link

HAS_NUMBER = re.compile(r"\d")
# A Portuguese post code, 1200-109. The same shape the entry form insists
# on, kept here so the readers can ask whether what they have is a whole
# address or only part of one.
POST_CODE = re.compile(r"\b\d{4}-\d{3}\b")
# The country at the end, which the form never asks for. Sites write it in
# whatever language they served the page in.
TRAILING_COUNTRY = re.compile(
    r",\s*(portugal|espanha|spain|ee\.?\s*uu\.?|usa|united states|"
    r"estados unidos|france|frança|españa|deutschland|germany|"
    r"italia|italy|nederland|netherlands|united kingdom|reino unido)\.?\s*$",
    re.I)


def address_in(url):
    """The address a link spells out, or None.

    Worth asking before the coordinates, because it is the address the
    place itself gave rather than whatever stands at that spot. An Apple
    short link lands on exactly this: ?address=R. de Sao Pedro de Alcantara
    35, 1250-237 Lisboa&coordinate=...

    What sits after /place/ in a Google link is only the address when the
    search was for one, so it has to carry a number to be believed. A name
    in the address box is the thing this whole business is meant to stop.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parts.query)
    except ValueError:
        return None
    for key in ("address", "q", "daddr", "destination"):
        for value in query.get(key, []):
            value = value.strip()
            if value and not PAIR.match(value) and HAS_NUMBER.search(value):
                return _tidy(value)
    found = re.search(r"/maps/place/([^/]+)", parts.path)
    if found:
        value = urllib.parse.unquote(found.group(1).replace("+", " ")).strip()
        if value and not value.startswith("@") and not PAIR.match(value) \
                and HAS_NUMBER.search(value):
            return _tidy(value)
    return None


# Rua, Avenida and the rest, as people shorten them.
SHORT_FOR = {"r": "rua", "av": "avenida", "avda": "avenida", "trav": "travessa",
             "tv": "travessa", "lg": "largo", "pc": "praca", "pç": "praca",
             "praça": "praca", "est": "estrada", "cc": "cc"}


def _road_words(line):
    """The name of a street, boiled down so two spellings of it match.

    "19 R. do Prior" and "Rua do Prior 46" are the same street written two
    ways, and the only way to see that is to throw away the numbers, the
    dots and the difference between R. and Rua.
    """
    words = []
    for word in re.split(r"[^0-9A-Za-zÀ-ÿ]+", (line or "").split(",")[0].lower()):
        if not word or word.isdigit():
            continue
        words.append(SHORT_FOR.get(word, word))
    return [w for w in words if w not in ("de", "do", "da", "dos", "das")]


def combine(said, found):
    """The street a page gave, with the post code a lookup found.

    A page knows the door number of its own venue. The lookup knows which
    post code that corner of town has, but its number is whatever building
    the pin sits nearest, which for a club in Faro came back as 46 for a
    door the page itself calls 19. So when both mean the same street, the
    street line is the page's and only the tail is borrowed. When they
    mean different streets there is nothing to combine and the lookup
    wins, because it at least belongs to the coordinates.
    """
    if not said or not found:
        return found
    mine, theirs = _road_words(said), _road_words(found)
    if not mine or not theirs:
        return found
    if not (set(mine) <= set(theirs) or set(theirs) <= set(mine)):
        return found
    tail = found.split(",")[-1].strip()
    if not POST_CODE.search(tail):
        return found
    street = said.split(",")[0].strip()
    return plain_address(f"{street}, {tail}")


# What a Portuguese street is called before it is named. Only a line that
# begins with a number and then one of these is turned around, so a street
# that is genuinely named after a number, Avenida 25 de Abril and its like,
# is left exactly as it stands.
STREET_WORDS = (
    "rua", "r", "avenida", "av", "avda", "travessa", "tv", "trav", "largo",
    "lg", "praca", "praça", "pc", "pç", "estrada", "est", "calcada",
    "calçada", "beco", "alameda", "campo", "rotunda", "caminho", "quinta",
    "azinhaga", "escadinhas", "praceta", "bairro", "zona", "edificio",
    "edifício", "parque", "mercado", "cais", "doca", "terreiro", "pateo",
    "pátio", "rossio",
)
# 19, 112 A, 60-64, 7B. The door, however it is written.
DOOR = re.compile(
    r"^(\d+\s*[A-Za-z]?(?:\s*[-–/]\s*\d+\s*[A-Za-z]?)?)\s+(.+)$")


def street_order(street):
    """Rua do Prior 19, out of 19 R. do Prior.

    Some sites write the door first, which is how it is done in English.
    In Portugal the street comes first and the number follows it, and an
    address in the wrong order reads as a foreign one even when every part
    of it is right.
    """
    found = DOOR.match((street or "").strip())
    if not found:
        return street
    door, rest = found.group(1).strip(), found.group(2).strip()
    first = re.split(r"[^0-9A-Za-zÀ-ÿ]+", rest.lower())[0]
    if first not in STREET_WORDS:
        return street
    return f"{rest} {door}"


def plain_address(line):
    """An address line in the Portuguese order, without the country.

    Shared with the ticket import, because a street from a maps link and a
    street from an event page should look the same in the box.
    """
    line = (line or "").strip()
    # Twice, for "Lisbon, Portugal, Portugal" and the like.
    for _ in range(2):
        line = TRAILING_COUNTRY.sub("", line).strip().rstrip(",").strip()
    # Only the street part. What follows the first comma is the post code
    # and the town, which never carry a door.
    head, sep, tail = line.partition(",")
    line = street_order(head.strip()) + sep + tail
    return line.strip()[:120]


def _tidy(line):
    return plain_address(line)


# --------------------------------------------------------------- the lookup

def address_at(lat, lng):
    """What is at these coordinates, as one line, or None.

    Written the Portuguese way, street and number first, then the post code
    and the town, because that is the shape the form asks for.
    """
    query = urllib.parse.urlencode({
        "lat": f"{lat:.7f}", "lon": f"{lng:.7f}",
        "format": "jsonv2", "zoom": "18", "addressdetails": "1",
        "accept-language": "pt",
    })
    req = urllib.request.Request(f"{NOMINATIM}?{query}",
                                 headers={"User-Agent": AGENT,
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            answer = json.loads(res.read(BODY_LIMIT).decode("utf-8", "replace"))
    except Exception:
        return None
    return one_line(answer.get("address") or {})


def one_line(parts):
    """Rua Alto da Loba 5, 2780-176 Oeiras, out of what the service returns."""
    road = (parts.get("road") or parts.get("pedestrian") or parts.get("footway")
            or parts.get("neighbourhood") or "").strip()
    number = (parts.get("house_number") or "").strip()
    # A door that spans several numbers comes back as "60,62,64". One is
    # enough to find it, and a list of numbers inside a line that already
    # separates its parts with commas reads as nonsense.
    number = re.split(r"[,;/]", number)[0].strip()
    code = (parts.get("postcode") or "").strip()
    town = (parts.get("town") or parts.get("city") or parts.get("village")
            or parts.get("municipality") or parts.get("county") or "").strip()

    street = " ".join(bit for bit in (road, number) if bit)
    tail = " ".join(bit for bit in (code, town) if bit)
    line = ", ".join(bit for bit in (street, tail) if bit)
    # Without a street or without a post code it is not the address the form
    # wants, and half of one in the box is worse than an empty box.
    if not street or not code:
        return None
    return line[:120]


# ------------------------------------------------------------------ the whole

def address_from_link(text):
    """A pasted maps link turned into an address.

    Gives back {"ok": True, "address": ...} or {"ok": False, "reason": ...}
    with a reason the form can turn into one sentence.
    """
    url = clean_url(text)
    if not url:
        return {"ok": False, "reason": "not_maps"}
    try:
        url = follow(url)
    except ValueError:
        return {"ok": False, "reason": "off_list"}
    except OSError:
        return {"ok": False, "reason": "unreachable"}
    # The link may say it outright once it has been followed, and then
    # there is nothing to look up.
    spelled = address_in(url)
    if spelled:
        return {"ok": True, "address": spelled}
    point = coordinates_in(url)
    if not point:
        return {"ok": False, "reason": "no_point"}
    address = address_at(*point)
    if not address:
        return {"ok": False, "reason": "nothing_there"}
    return {"ok": True, "address": address}
