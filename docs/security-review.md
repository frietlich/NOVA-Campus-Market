# Security and verification review

## What changes

- Require a random session secret and verified Nova accounts on protected pages.
- Use Secure, HttpOnly, SameSite=Lax session cookies in production.
- Remove the development account selector at /dev entirely.
- Protect state-changing requests by checking the Origin or Referer.
- Restrict uploaded images to signed-in verified users. Re-encode validated
  JPEG, PNG and WebP uploads, reject images above 5 MB or 20 million pixels.
- Validate prices, quantities, text lengths and group course membership.
- Check participants again before storing a chat message.
- Store keyed code digests with purpose separation. Enforce ten-minute expiry,
  five guesses, atomic one-time use and a sixty-second resend cooldown.
- Limit login attempts by normalized email (20 per ten minutes); keep a generous
  IP ceiling (2,000 per ten minutes per endpoint) on other authentication forms.
- Return a mail-delivery error without SMTP in production. Print terminal codes
  only with explicit local demo mode and no SMTP.
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
hidden in production. Terminal verification codes are available only in explicit
local demo mode without SMTP, which bypasses real mailbox verification.

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
keyed by normalized email for login, with a generous shared-IP ceiling on other
authentication forms. Account code-guess and resend limits apply separately.
Proxy headers are tested with trusted and untrusted clients. Follow the README
proxy configuration and verify the actual public deployment before release.

Earlier dependencies were flagged by pip-audit. The upgraded lock must be
tested against any later changes to main before merge.


## Compatibility with the latest imports and notifications

The branch includes current main's course catalogue, listing editing, ticket
and housing screenshot imports, and push notification features. Runtime locks
include Anthropic 2.12.0, Pillow 13.0.0, pywebpush 2.5.0 and Windows timezone data.

Ticket-link import requires a verified session and a valid request origin,
and is limited to 30 requests per account per ten minutes. Screenshot quotas
are updated atomically so concurrent requests cannot exceed the daily limit.
Push destinations are restricted to browser providers over HTTPS on port 443;
redirects are not followed. Stored legacy destinations are checked again before
sending. Push errors do not log endpoint tokens or message bodies.

The provider list follows official documentation:
- Google: https://firebase.google.com/docs/cloud-messaging/network-configuration
- Mozilla: https://mozilla-services.github.io/autopush-rs/
- Apple: https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
- Microsoft: https://learn.microsoft.com/en-us/windows/apps/develop/notifications/push-notifications/firewall-allowlist-config

All automated email, AI and push tests use test settings and mocks. Developer
.env credentials are explicitly excluded from tests and Git. SMTP login is a
separate manual check; tests do not send real messages or spend API credit.

After merging, set the shared sender credentials in the hosting service's
private environment settings. A Git merge does not copy anyone's local .env.
Set CAMPUS_SECURITY_DEMO=0, keep a stable random session secret, configure only
trusted HTTPS proxy addresses, and test real inbox delivery plus persistent
storage on the public deployment before calling it release-ready.
