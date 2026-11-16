"""Sending the 6-digit code by e-mail.

The settings come from the file .env in the project folder, which is never
put into git. Copy .env.example to .env and fill it in. For a Gmail account
that means an app password, not the normal one. See the README.

When no mail account is set up, nothing is sent and the code is printed in
the terminal where the server runs, exactly as before. That keeps the app
working for everybody who builds on it without a mail account.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")


def load_env(path=ENV_PATH):
    """Read KEY=value lines from .env into the environment.

    Something already set in the environment wins, so a server can set its
    own values without touching the file.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)


def settings():
    """The mail settings, read fresh so a changed .env needs only a restart."""
    user = os.environ.get("SMTP_USER", "").strip()
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com").strip(),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "user": user,
        # Gmail shows an app password in groups of four, with spaces. Those
        # spaces are not part of it.
        "password": os.environ.get("SMTP_PASSWORD", "").replace(" ", ""),
        "sender": os.environ.get("MAIL_FROM", "").strip() or user,
    }


def is_set_up():
    s = settings()
    return bool(s["user"] and s["password"])


SUBJECTS = {
    "join": "Your Campus Market code",
    "login": "Your Campus Market code",
    "reset": "Set a new Campus Market password",
}

LINES = {
    "join": "Welcome to Campus Market. Put this code in to confirm your address:",
    "login": "Put this code in to confirm your address and log in:",
    "reset": "Put this code in to set a new password:",
}


def send_code(to, code, why="join"):
    """Send the code to one address. True when it went out.

    why is "join", "login" or "reset" and only changes the wording.
    """
    if not is_set_up():
        print(f"\n  no mail account set up, the {why} code for {to} is {code}\n",
              flush=True)
        return True

    s = settings()
    msg = EmailMessage()
    msg["Subject"] = SUBJECTS.get(why, SUBJECTS["join"])
    msg["From"] = f"Campus Market <{s['sender']}>"
    msg["To"] = to
    msg.set_content(
        f"{LINES.get(why, LINES['join'])}\n\n"
        f"    {code}\n\n"
        "It works for 15 minutes.\n\n"
        "If you did not ask for this, ignore this e-mail. Nobody can get in\n"
        "without the code.\n"
    )

    try:
        context = ssl.create_default_context()
        if s["port"] == 465:
            server = smtplib.SMTP_SSL(s["host"], s["port"], context=context, timeout=15)
        else:
            server = smtplib.SMTP(s["host"], s["port"], timeout=15)
            server.starttls(context=context)
        with server:
            server.login(s["user"], s["password"])
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as err:
        # The code itself is not printed here. Whoever reads the server log
        # should not be able to log in as somebody else.
        print(f"\n  could not send the code to {to}: {err}\n", flush=True)
        return False
    return True
