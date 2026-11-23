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
                                       category=category, event_date="2030-10-31",
                                       place="Lux Frágil")
        return db.get_listing(listing_id)

    def test_every_area_is_on_until_switched_off(self):
        prefs = db.prefs_of(self.buyer)
        self.assertEqual({area: p["on"] for area, p in prefs.items()},
                         {"all": True, "messages": True, "ticket": True,
                          "housing": True, "item": True, "group": True})

    def test_the_main_switch_silences_everything_but_the_test(self):
        self.save(self.buyer, "ticket", "")
        db.set_pref(self.buyer, "all", False)
        self.announce(self.ticket()["id"])
        listing = self.ticket()
        conv = db.get_conversation(db.open_conversation(listing["id"], self.seller))
        push.new_message(conv, self.seller, "Hello")
        self.assertNotIn(self.buyer, self.receivers())
        push.send(self.buyer, "Campus Market", "test", "/", test=True)
        self.assertIn(self.buyer, self.receivers())
        db.set_pref(self.buyer, "all", True)
        self.assertTrue(db.prefs_of(self.buyer)["ticket"]["on"])   # kept as it was

    def save(self, user, kind, query):
        from app.main import search_label, search_of
        params = search_of(kind, query)
        db.watch_search(user, kind, params, search_label(kind, params))
        return params

    def announce(self, listing_id):
        from app.main import event_key, search_finds
        push.new_listing(db.get_listing(listing_id), event_key, search_finds)

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

    def test_nobody_hears_anything_without_a_saved_search(self):
        self.announce(self.ticket()["id"])
        self.assertEqual(self.sent, [])

    def test_several_ticket_searches_and_only_what_fits(self):
        self.save(self.buyer, "ticket", "q=halloween")
        self.save(self.buyer, "ticket", "cat=concert")
        self.save(self.other, "ticket", "q=football")
        self.save(self.seller, "ticket", "")                 # the seller is never told
        self.announce(self.ticket()["id"])
        self.assertEqual(self.receivers(), [self.buyer])     # once, though two searches
        self.assertTrue(self.sent[0][1]["title"].startswith("New ticket: Halloween"))

    def test_a_housing_search_keeps_every_filter(self):
        self.save(self.buyer, "housing", "area=carcavelos&rmax=600&has=wifi&cat=shared_flat")
        self.save(self.other, "housing", "area=lisboa")
        cheap = db.create_listing(self.seller, "housing", "Room near the beach", price=550,
                                  category="shared_flat", place="carcavelos",
                                  available_from="2030-01-01", features="wifi,desk")
        self.announce(cheap)
        self.assertEqual(self.receivers(), [self.buyer])
        self.sent.clear()
        dear = db.create_listing(self.seller, "housing", "Room near the beach", price=900,
                                 category="shared_flat", place="carcavelos",
                                 available_from="2030-01-01", features="wifi")
        no_wifi = db.create_listing(self.seller, "housing", "Room", price=500,
                                    category="shared_flat", place="carcavelos",
                                    available_from="2030-01-01", features="desk")
        self.announce(dear)
        self.announce(no_wifi)
        self.assertEqual(self.sent, [])

    def test_a_market_search_keeps_price_and_condition(self):
        self.save(self.buyer, "item", "q=bike&price=50&cond=used")
        fits = db.create_listing(self.seller, "item", "City bike", price=40,
                                 category="sports", condition="used")
        too_dear = db.create_listing(self.seller, "item", "Road bike", price=200,
                                     category="sports", condition="used")
        self.announce(too_dear)
        self.assertEqual(self.sent, [])
        self.announce(fits)
        self.assertEqual(self.receivers(), [self.buyer])

    def test_the_same_search_is_saved_once_however_it_was_written(self):
        from app.main import search_of
        self.assertEqual(search_of("housing", "has=wifi&area=parede&has=desk&sort=low&q="),
                         search_of("housing", "area=parede&has=desk&has=wifi"))
        self.save(self.buyer, "ticket", "q=party")
        self.save(self.buyer, "ticket", "q=party&day=2030-01-01")
        self.assertEqual(len(db.searches_watched(self.buyer)), 1)

    def test_a_search_has_a_label_in_words(self):
        from app.main import search_label, search_of
        label = search_label("housing", search_of("housing", "q=sea&area=cascais&rmax=800&has=wifi"))
        self.assertIn("Cascais", label)
        self.assertIn("€800", label)
        self.assertIn("wifi", label.lower())
        self.assertEqual(search_label("item", search_of("item", "")), "Everything new")

    def test_switching_an_area_off_keeps_the_searches(self):
        self.save(self.buyer, "ticket", "q=halloween")
        db.set_pref(self.buyer, "ticket", False)
        self.announce(self.ticket()["id"])
        self.assertEqual(self.sent, [])
        self.assertEqual(len(db.searches_watched(self.buyer)), 1)

    def test_a_device_that_is_gone_is_forgotten(self):
        with mock.patch.object(push, "_webpush", return_value=False):
            push.send(self.buyer, "x", "y", "/")
        self.assertEqual(db.devices_of(self.buyer), [])

    def test_without_keys_nothing_is_sent(self):
        with mock.patch.dict(os.environ, {"VAPID_PRIVATE_KEY": ""}):
            self.assertEqual(push.send(self.buyer, "x", "y", "/"), 0)
        self.assertEqual(self.sent, [])

    def event(self, title, date_, time_, place, owner=None):
        listing_id = db.create_listing(owner or self.seller, "ticket", title, price=20,
                                       category="party", event_date=date_,
                                       event_time=time_, place=place)
        return db.get_listing(listing_id)

    def test_several_events_can_be_watched_and_only_that_one_rings(self):
        from app.main import event_key
        brunch = self.event("Brunch Electronik", "2030-06-07", "14:00", "Tapada da Ajuda")
        lux = self.event("Lux night", "2030-06-08", "23:00", "Lux Frágil")
        db.watch_event(self.buyer, event_key(brunch), brunch["title"], brunch["place"])
        db.watch_event(self.buyer, event_key(lux), lux["title"], lux["place"])
        self.assertEqual(len(db.events_watched(self.buyer)), 2)

        # Somebody else sells for the brunch, with another name and spelling.
        again = self.event("2x brunch sunday!!", "2030-06-07", "14:00", "tapada da ajuda",
                           owner=self.other)
        push.new_listing(again, event_key)
        self.assertEqual(self.receivers(), [self.buyer])
        self.assertTrue(self.sent[0][1]["title"].startswith("Another ticket"))

        self.sent.clear()
        push.new_listing(self.event("Other party", "2030-06-07", "22:00", "Tapada da Ajuda",
                                    owner=self.other), event_key)
        self.assertEqual(self.sent, [])

    def test_an_event_watcher_who_also_watches_the_tab_hears_it_once(self):
        from app.main import event_key
        brunch = self.event("Brunch Electronik", "2030-06-07", "14:00", "Tapada da Ajuda")
        db.watch_event(self.buyer, event_key(brunch), brunch["title"], brunch["place"])
        self.save(self.buyer, "ticket", "")
        self.announce(self.event("Brunch", "2030-06-07", "14:00", "Tapada da Ajuda",
                                 owner=self.other)["id"])
        self.assertEqual(self.receivers(), [self.buyer])

    def test_an_event_can_be_removed_and_past_ones_go_by_themselves(self):
        from app.main import event_key
        soon = self.event("Soon", "2030-06-07", "14:00", "Somewhere")
        past = self.event("Past", "2020-01-01", "14:00", "Somewhere")
        db.watch_event(self.buyer, event_key(soon), "Soon", "Somewhere")
        db.watch_event(self.buyer, event_key(past), "Past", "Somewhere")
        watched = db.events_watched(self.buyer)
        self.assertEqual([w["title"] for w in watched], ["Soon"])
        db.unwatch_event(self.other, watch_id=watched[0]["id"])   # not theirs
        self.assertEqual(len(db.events_watched(self.buyer)), 1)
        db.unwatch_event(self.buyer, watch_id=watched[0]["id"])
        self.assertEqual(db.events_watched(self.buyer), [])

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
        self.client = TestClient(main.app, headers={"origin": "http://testserver"})
        self.client.__enter__()
        from app import passwords
        self.user = db.create_user("44444@novasbe.pt", "Page P.", "finance",
                                   passwords.hash_password("TestPassword1!"))
        with db.connect() as conn:
            conn.execute("UPDATE users SET verified = 1 WHERE id = ?", (self.user,))
        conn.close()
        self.client.post("/login", data={"email": "44444@novasbe.pt",
                                         "password": "TestPassword1!"})

    def tearDown(self):
        self.client.__exit__(None, None, None)
        db.DB_PATH = self.original
        self.temp.cleanup()

    def test_the_bell_saves_the_search_and_forgets_it_again(self):
        answer = self.client.post("/notify/watch", data={
            "kind": "housing", "back": "/housing?area=parede&rmax=700"}, follow_redirects=False)
        self.assertEqual(answer.headers["location"], "/housing?area=parede&rmax=700&done=search-on")
        self.assertEqual(len(db.searches_watched(self.user)), 1)
        page = self.client.get("/housing?area=parede&rmax=700").text
        self.assertIn("bell--on", page)
        self.assertNotIn("bell--on", self.client.get("/housing?area=lisboa").text)
        settings = self.client.get("/profile/notifications").text
        self.assertIn("Parede", settings)
        self.client.post("/notify/watch", data={"kind": "housing",
                                                "back": "/housing?rmax=700&area=parede"})
        self.assertEqual(db.searches_watched(self.user), [])

    def test_a_search_can_be_removed_in_the_settings(self):
        self.client.post("/notify/watch", data={"kind": "item", "back": "/market?q=bike"})
        watch_id = db.searches_watched(self.user)[0]["id"]
        self.client.post("/notify/search/remove", data={"watch_id": watch_id})
        self.assertEqual(db.searches_watched(self.user), [])

    def test_the_bell_never_sends_you_off_the_site(self):
        answer = self.client.post("/notify/watch", data={
            "kind": "ticket", "back": "//evil.example"}, follow_redirects=False)
        self.assertTrue(answer.headers["location"].startswith("/tickets"))

    def test_the_settings_page_switches_each_area(self):
        self.client.post("/profile/notifications", data={"on": ["all", "housing", "item"]})
        prefs = db.prefs_of(self.user)
        self.assertEqual({area: p["on"] for area, p in prefs.items()},
                         {"all": True, "messages": False, "ticket": False,
                          "housing": True, "item": True, "group": False})
        page = self.client.get("/profile/notifications").text
        self.assertIn('value="housing" checked', page)

    def test_a_device_is_saved_and_checked(self):
        good = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "k", "auth": "a"}}
        self.assertEqual(self.client.post("/push/device", json=good).status_code, 200)
        self.assertEqual(len(db.devices_of(self.user)), 1)
        bad = dict(good, endpoint="http://127.0.0.1/steal")
        self.assertEqual(self.client.post("/push/device", json=bad).status_code, 400)

    def test_the_bell_on_a_ticket_and_the_list_in_the_settings(self):
        seller = db.create_user("55555@novasbe.pt", "Seller S.")
        listing_id = db.create_listing(seller, "ticket", "Brunch Electronik", price=40,
                                       event_date="2030-06-07", event_time="14:00",
                                       place="Tapada da Ajuda")
        # The bell moved up beside the heart, so what it says is now its
        # label rather than a line of text on the page.
        self.assertIn("Tell me about more tickets for this event",
                      self.client.get(f"/listing/{listing_id}").text)
        self.client.post("/notify/event", data={"listing_id": listing_id, "on": "1"})
        on = self.client.get(f"/listing/{listing_id}").text
        self.assertIn("Stop hearing about this event", on)
        self.assertIn("watch--on", on)
        settings = self.client.get("/profile/notifications").text
        self.assertIn("Brunch Electronik", settings)
        watch_id = db.events_watched(self.user)[0]["id"]
        self.client.post("/notify/event/remove", data={"watch_id": watch_id})
        self.assertEqual(db.events_watched(self.user), [])

    def test_the_bell_on_a_group_watches_the_course(self):
        """The same bell on a group, keyed on the course rather than a day.

        Somebody needing a team hears about the next group for that course,
        whatever its owner calls the entry, which is the whole point of
        hanging it on the course and not on the title.
        """
        owner = db.create_user("66666@novasbe.pt", "Owner O.")
        course_id = db.connect().execute("SELECT id FROM courses LIMIT 1").fetchone()["id"]
        listing_id = db.create_listing(owner, "group", "Final project, panel data",
                                       course_id=course_id, group_size=4,
                                       hand_in="2030-06-07")
        self.assertIn("Tell me about more groups for this course",
                      self.client.get(f"/listing/{listing_id}").text)

        self.client.post("/notify/course", data={"listing_id": listing_id, "on": "1"})
        on = self.client.get(f"/listing/{listing_id}").text
        self.assertIn("Stop hearing about this course", on)
        self.assertIn("watch--on", on)
        self.assertEqual(db.course_watchers(course_id), [self.user])

        # A second group for the same course, called something else, still
        # reaches the same person.
        other = db.create_listing(owner, "group", "Econometrics, need two",
                                  course_id=course_id, group_size=3,
                                  hand_in="2030-06-08")
        self.assertIn(self.user, db.course_watchers(db.get_listing(other)["course_id"]))

        # And the course itself is in the settings, by name, to switch off.
        watched = db.courses_watched(self.user)
        self.assertEqual(len(watched), 1)
        self.assertIn(watched[0]["name"], self.client.get("/profile/notifications").text)

        watch_id = watched[0]["id"]
        self.client.post("/notify/course/remove", data={"watch_id": watch_id})
        self.assertEqual(db.courses_watched(self.user), [])

    def test_the_service_worker_is_served_from_the_top(self):
        answer = self.client.get("/sw.js")
        self.assertEqual(answer.status_code, 200)
        self.assertIn("javascript", answer.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
