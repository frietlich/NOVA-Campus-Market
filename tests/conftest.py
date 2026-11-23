"""Tests always use isolated settings, never a developer's real email/API keys."""
import os

os.environ["CAMPUS_SECRET"] = "isolated-test-session-secret-" * 3
os.environ["CAMPUS_SECURITY_DEMO"] = "1"
for key in ("SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "ANTHROPIC_API_KEY",
            "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"):
    os.environ[key] = ""
