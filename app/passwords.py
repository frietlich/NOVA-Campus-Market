"""Everything about passwords. The rules, and how they are stored.

A password is never saved. What goes into the database is the result of a
one way calculation that cannot be turned back, together with a random
addition called the salt, so that two students with the same password do not
end up with the same entry.

We use PBKDF2, which comes with Python and is there on every machine. It is
slow on purpose, because it repeats the calculation hundreds of thousands of
times. A fast method like plain md5 or sha256 would let an attacker try
millions of guesses a second, which is exactly what you do not want here.
"""

import hashlib
import hmac
import os
import re

MIN_LENGTH = 8
MAX_LENGTH = 30

SPECIAL = r"[^A-Za-z0-9]"

RULES = (
    f"At least {MIN_LENGTH} characters, at most {MAX_LENGTH}, "
    "with one capital letter, one number and one special character."
)

# How often the calculation is repeated. Higher is safer and slower. This
# takes about a tenth of a second, which nobody notices when logging in and
# which makes guessing hopeless.
ROUNDS = 240_000
SALT_BYTES = 16


def problem(password):
    """Give back what is wrong with a password, or None when it is fine."""
    if password is None:
        password = ""
    if len(password) < MIN_LENGTH:
        return f"The password needs at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"The password can be at most {MAX_LENGTH} characters."
    if not re.search(r"[A-Z]", password):
        return "The password needs at least one capital letter."
    if not re.search(r"[0-9]", password):
        return "The password needs at least one number."
    if not re.search(SPECIAL, password):
        return "The password needs at least one special character."
    return None


def hash_password(password):
    """salt and hash, written as one piece of text for the database."""
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ROUNDS)
    return f"pbkdf2_sha256${ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(stored, password):
    """True only if the password matches what was stored.

    The comparison uses compare_digest and not ==, because a normal comparison
    stops at the first wrong character and the time it takes would tell an
    attacker how much of the guess was right.
    """
    if not stored or not password:
        return False
    try:
        kind, rounds, salt_hex, digest_hex = stored.split("$")
        if kind != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)
