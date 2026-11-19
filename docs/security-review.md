# Security and verification review

## What changes

- Require a random session secret and verified Nova accounts on protected pages.
- Use Secure, HttpOnly, SameSite=Lax session cookies in production.
- Disable the development account selector unless CAMPUS_SECURITY_DEMO=1.
- Protect state-changing requests by checking the Origin or Referer.
- Restrict uploaded images to signed-in verified users. Re-encode validated
  JPEG, PNG and WebP uploads, reject images above 5 MB or 20 million pixels.
- Validate prices, quantities, text lengths and group course membership.
- Check participants again before storing a chat message.
- Store keyed code digests with purpose separation. Enforce ten-minute expiry,
  five guesses, atomic one-time use and a sixty-second resend cooldown.
- Rate-limit authentication POST requests by client address and endpoint.
- Return a mail-delivery error when SMTP is absent. Never print codes.
- Pin runtime dependencies with hashes and run tests and pip-audit in CI.

## Developer setup

Use Python 3.12. Copy .env.example to .env, generate a random CAMPUS_SECRET and
set CAMPUS_SECURITY_DEMO=1 only for local development. Install:

    python -m pip install --require-hashes -r requirements.txt
    python -m pip install -r requirements-test.txt
    python -m pytest tests -q
    python -m pip_audit -r requirements.txt

The tests use temporary databases, isolated uploads and mocked SMTP. Real
sender credentials are unnecessary. Hash-pinned runtime dependencies include
transitive packages. requirements.in records the direct runtime packages.
To regenerate the lock, use uv pip compile requirements.in --generate-hashes
--output-file requirements.txt, then rerun both commands.

Development account selection requires verified Nova demo accounts and is
hidden in production. The old terminal-code fallback is removed.

## Deployment acceptance

- Set a stable random CAMPUS_SECRET, actual SMTP credentials and
  CAMPUS_SECURITY_DEMO=0. Register with an approved Nova inbox.
- Confirm the public URL uses HTTPS and correct trusted reverse-proxy settings.
  The origin check compares against the actual request scheme and host.
- Confirm encrypted persistent storage, backups, upload persistence and database
  access with the hosting provider. These depend on the chosen deployment.
- Agree on retention, deletion and privacy contact information.
- Check repository history for leaked credentials and rotate any exposed key.
- Run tests on the final combined main, then rehearse with three users on
  separate devices. CI will also run on every PR and push to main.

## Limits

These changes are a reviewable application hardening step. They do not
establish end-to-end encryption or GDPR compliance. Verified Nova email proves
mailbox access, which also includes some alumni and staff. Production hosting
and actual inbox delivery must be checked separately.

The SQLite throttle shares state between workers and survives restart. It is
keyed by client address and endpoint, so the team must test proxy handling and
tune limits for shared campus networks.

Earlier dependencies were flagged by pip-audit. The upgraded lock must be
tested against any later changes to main before merge.
