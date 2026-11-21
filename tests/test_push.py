"""Who gets a notification, and that the settings hold. Nothing is really sent."""
import os
import tempfile
import unittest
from unittest import mock

from app import db, push


class PushTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "test.db")
        db.setup()
        env = mock.patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "pub", "VAPID_PRIVATE_KEY": "priv",
                                           "VAPID_SUBJECT": "mailto:test@example.com"})
        env.start()
        self.addCleanup(env.stop)
        self.seller = db.create_user("11111@novasbe.pt", "Seller S.")
        self.buyer = db.create_user("22222@novasbe.pt", "Buyer B.")
        self.other = db.create_user("33333@novasbe.pt", "Other O.")
        for user in (self.seller, self.buyer, self.other):
            db.save_device(user, f"https://push.example/{user}", "key", "auth")
        self.sent = []

        def fake(device, payload):
            self.sent.append((device["user_id"], payload))
            return True
        patcher = mock.patch.object(push, "_webpush", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        db.DB_PATH = self.original
        self.temp.cleanup()

    def receivers(self):
        return sorted(user for user, _ in self.sent)

    def ticket(self, title="Halloween Club Party", category="party"):
        listing_id = db.create_listing(self.seller, "ticket", title, price=25,
                                       category=category, event_date="2026-10-31",
                                       place="Lux Frágil")
        return db.get_listing(listing_id)

    def test_messages_are_on_and_the_rest_off_by_default(self):
        prefs = db.prefs_of(self.buyer)
        self.assertEqual({area: p["on"] for area, p in prefs.items()},
                         {"messages": True, "ticket": False, "housing": False, "item": False})

    def test_a_new_message_reaches_the_other_person_only(self):
        listing = self.ticket()
        conv = db.get_conversation(db.open_conversation(listing["id"], self.buyer))
        push.new_message(conv, self.buyer, "Is it still there?")
        self.assertEqual(self.receivers(), [self.seller])
        self.assertEqual(self.sent[0][1]["url"], f"/chat/{conv['id']}")
        self.assertIn("Buyer B.", self.sent[0][1]["title"])

    def test_messages_can_be_turned_off(self):
        db.set_pref(self.seller, "messages", False)
        listing = self.ticket()
        conv = db.get_conversation(db.open_conversation(listing["id"], self.buyer))
        push.new_message(conv, self.buyer, "Hello")
        self.assertEqual(self.sent, [])

    def test_a_new_ticket_reaches_whoever_watches_tickets(self):
        db.set_pref(self.buyer, "ticket", True, "", "")
        db.set_pref(self.other, "housing", True, "", "")
        db.set_pref(self.seller, "ticket", True, "", "")     # the seller is never told
        push.new_listing(self.ticket())
        self.assertEqual(self.receivers(), [self.buyer])
        self.assertTrue(self.sent[0][1]["title"].startswith("New ticket: Halloween"))

    def test_only_what_matches_the_search(self):
        db.set_pref(self.buyer, "ticket", True, "halloween lux", "")
        db.set_pref(self.other, "ticket", True, "", "concert")
        push.new_listing(self.ticket())
        self.assertEqual(self.receivers(), [self.buyer])

    def test_turning_an_area_off_keeps_the_search_for_later(self):
        db.set_pref(self.buyer, "ticket", True, "party", "")
        db.set_pref(self.buyer, "ticket", False)
        push.new_listing(self.ticket())
        self.assertEqual(self.sent, [])
        self.assertEqual(db.prefs_of(self.buyer)["ticket"]["q"], "party")

    def test_a_device_that_is_gone_is_forgotten(self):
        with mock.patch.object(push, "_webpush", return_value=False):
            push.send(self.buyer, "x", "y", "/")
        self.assertEqual(db.devices_of(self.buyer), [])

    def test_without_keys_nothing_is_sent(self):
        with mock.patch.dict(os.environ, {"VAPID_PRIVATE_KEY": ""}):
            self.assertEqual(push.send(self.buyer, "x", "y", "/"), 0)
        self.assertEqual(self.sent, [])

    def test_keys_have_the_shape_browsers_expect(self):
        public, private = push.make_keys()
        self.assertEqual(len(public), 87)    # 65 bytes, base64 without padding
        self.assertEqual(len(private), 43)   # 32 bytes


class PageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "test.db")
        env = mock.patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "pub", "VAPID_PRIVATE_KEY": "priv",
                                           "VAPID_SUBJECT": "mailto:test@example.com"})
        env.start()
        self.addCleanup(env.stop)
        from fastapi.testclient import TestClient
        from app import main
        self.client = TestClient(main.app)
        self.client.__enter__()
        self.user = db.create_user("44444@novasbe.pt", "Page P.")
        with db.connect() as conn:
            conn.execute("UPDATE users SET verified = 1 WHERE id = ?", (self.user,))
        self.client.post("/dev", data={"user_id": self.user})

    def tearDown(self):
        self.client.__exit__(None, None, None)
        db.DB_PATH = self.original
        self.temp.cleanup()

    def test_the_bell_saves_the_search(self):
        answer = self.client.post("/notify/watch", data={
            "kind": "ticket", "on": "1", "q": "party", "cat": "concert",
            "back": "/tickets?q=party"}, follow_redirects=False)
        self.assertEqual(answer.headers["location"], "/tickets?q=party")
        self.assertEqual(db.prefs_of(self.user)["ticket"],
                         {"on": True, "q": "party", "cat": "concert"})

    def test_the_bell_never_sends_you_off_the_site(self):
        answer = self.client.post("/notify/watch", data={
            "kind": "ticket", "on": "1", "back": "//evil.example"}, follow_redirects=False)
        self.assertEqual(answer.headers["location"], "/tickets")

    def test_the_settings_page_switches_each_area(self):
        self.client.post("/profile/notifications", data={"on": ["housing", "item"]})
        prefs = db.prefs_of(self.user)
        self.assertEqual({area: p["on"] for area, p in prefs.items()},
                         {"messages": False, "ticket": False, "housing": True, "item": True})
        page = self.client.get("/profile/notifications").text
        self.assertIn('value="housing" checked', page)

    def test_a_device_is_saved_and_checked(self):
        good = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
        self.assertEqual(self.client.post("/push/device", json=good).status_code, 200)
        self.assertEqual(len(db.devices_of(self.user)), 1)
        bad = dict(good, endpoint="http://127.0.0.1/steal")
        self.assertEqual(self.client.post("/push/device", json=bad).status_code, 400)

    def test_the_service_worker_is_served_from_the_top(self):
        answer = self.client.get("/sw.js")
        self.assertEqual(answer.status_code, 200)
        self.assertIn("javascript", answer.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
