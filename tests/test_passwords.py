"""The password rules and how passwords are stored. Pure functions, no database."""
import pytest

from app import passwords


@pytest.mark.parametrize("password, broken_rule", [
    (None,              "at least 8"),
    ("Ab1!xyz",         "at least 8"),        # 7 characters, one short
    ("Ab1!" + "x" * 27, "at most 30"),        # 31 characters, one too many
    ("abcdefg1!",       "capital"),
    ("Abcdefgh!",       "number"),
    ("Abcdefgh1",       "special"),
])
def test_each_rule_is_named_when_it_is_broken(password, broken_rule):
    assert broken_rule in passwords.problem(password)


@pytest.mark.parametrize("password", [
    "Ab1!xyzw",            # exactly the minimum
    "Ab1!" + "x" * 26,     # exactly the maximum
    "Passwort1 ",          # a space counts as special
    "Ação-Fácil1",         # accents and Portuguese letters are fine
])
def test_passwords_on_the_edges_are_accepted(password):
    assert passwords.problem(password) is None


def test_the_same_password_is_never_stored_the_same_way_twice():
    first = passwords.hash_password("TestPassword1!")
    second = passwords.hash_password("TestPassword1!")
    assert first != second
    assert "TestPassword1!" not in first
    assert passwords.verify_password(first, "TestPassword1!")
    assert passwords.verify_password(second, "TestPassword1!")


def test_a_password_that_differs_in_one_letter_or_case_is_refused():
    stored = passwords.hash_password("TestPassword1!")
    for guess in ("TestPassword1?", "testpassword1!", "TestPassword1! ", ""):
        assert not passwords.verify_password(stored, guess)


@pytest.mark.parametrize("stored", [
    None,
    "",
    "not a hash at all",
    "md5$1$00$00",                          # a scheme we never wrote
    "pbkdf2_sha256$many$00$00",             # rounds that are not a number
    "pbkdf2_sha256$1000$zz$00",             # salt that is not hex
])
def test_a_broken_or_foreign_stored_value_never_lets_anybody_in(stored):
    assert passwords.verify_password(stored, "TestPassword1!") is False


def test_an_enormous_password_is_refused_before_any_work_is_done():
    stored = passwords.hash_password("TestPassword1!")
    assert passwords.verify_password(stored, "A1!" + "x" * 200) is False
