"""Reading .env and sending the code. No real mail server is ever contacted."""
import os
import smtplib

import pytest

from app import mailer


def test_env_file_lines_are_read_the_way_people_write_them(tmp_path, monkeypatch):
    for key in ("PLAIN", "DOUBLE", "SINGLE", "WITH_EQUALS", "EMPTY", "SPACED"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "PLAIN=value\n"
        'DOUBLE="quoted value"\n'
        "SINGLE='single'\n"
        "WITH_EQUALS=a=b=c\n"
        "EMPTY=\n"
        "  SPACED  =  around  \n"
        "no equals sign on this line\n",
        encoding="utf-8")
    mailer.load_env(str(env))
    assert os.environ["PLAIN"] == "value"
    assert os.environ["DOUBLE"] == "quoted value"
    assert os.environ["SINGLE"] == "single"
    assert os.environ["WITH_EQUALS"] == "a=b=c"
    assert os.environ["EMPTY"] == ""
    assert os.environ["SPACED"] == "around"


def test_a_value_already_set_on_the_server_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "from-the-server")
    env = tmp_path / ".env"
    env.write_text("SMTP_HOST=from-the-file\n", encoding="utf-8")
    mailer.load_env(str(env))
    assert os.environ["SMTP_HOST"] == "from-the-server"


def test_a_missing_env_file_is_fine(tmp_path):
    mailer.load_env(str(tmp_path / "nothing-here"))


class FakeServer:
    """Stands in for smtplib.SMTP and SMTP_SSL and remembers what it was asked."""
    calls = []

    def __init__(self, host, port, **kwargs):
        FakeServer.calls.append(("connect", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        FakeServer.calls.append(("starttls",))

    def login(self, user, password):
        FakeServer.calls.append(("login", user, password))

    def send_message(self, msg):
        FakeServer.calls.append(("send", msg))


@pytest.fixture
def smtp(monkeypatch):
    FakeServer.calls = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeServer)
    monkeypatch.setattr(smtplib, "SMTP", FakeServer)
    monkeypatch.setenv("SMTP_USER", "sender@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    return FakeServer.calls


def test_nothing_is_sent_without_settings(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "")
    assert mailer.send_code("12345@novasbe.pt", "123456") is False
    assert smtp == []


def test_the_code_goes_to_the_student_with_the_wording_for_why(smtp):
    assert mailer.send_code("12345@novasbe.pt", "481516", "reset") is True
    sent = [c[1] for c in smtp if c[0] == "send"][0]
    assert sent["To"] == "12345@novasbe.pt"
    assert sent["Subject"] == mailer.SUBJECTS["reset"]
    assert "481516" in sent.get_content()
    assert mailer.LINES["reset"] in sent.get_content()


def test_the_spaces_gmail_shows_in_an_app_password_are_dropped(smtp):
    mailer.send_code("12345@novasbe.pt", "481516")
    assert ("login", "sender@gmail.com", "abcdefghijklmnop") in smtp


def test_port_587_upgrades_to_tls_before_logging_in(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "587")
    mailer.send_code("12345@novasbe.pt", "481516")
    steps = [c[0] for c in smtp]
    assert steps.index("starttls") < steps.index("login")


def test_a_failing_server_is_reported_and_the_code_is_not_logged(smtp, monkeypatch, capsys):
    class Broken(FakeServer):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
    monkeypatch.setattr(smtplib, "SMTP_SSL", Broken)
    assert mailer.send_code("12345@novasbe.pt", "481516") is False
    assert "481516" not in capsys.readouterr().out
