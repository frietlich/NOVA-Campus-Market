"""The link to another housing site, and the queue of who asked first."""
import os
import tempfile
import unittest

from app import db, housing


class HousingLinkTests(unittest.TestCase):
    def test_links_from_known_sites_are_kept_and_made_https(self):
        self.assertEqual(housing.clean_listing_url("idealista.pt/imovel/123/"),
                         "https://idealista.pt/imovel/123/")
        self.assertEqual(
            housing.clean_listing_url("http://www.uniplaces.com/accommodation/lisbon/1#top"),
            "https://www.uniplaces.com/accommodation/lisbon/1")

    def test_links_anywhere_else_are_refused(self):
        for bad in ("https://evil.com/idealista.pt",      # the name in the path
                    "https://idealista.pt.evil.com/",     # the name as a prefix
                    "https://fakeidealista.pt/",          # a look-alike
                    "https://me:secret@idealista.pt/",    # a password in it
                    "https://www.olx.pt:8080/",           # a strange port
                    "javascript:alert(1)",
                    "idealista.pt/a b",                   # spaces
                    ""):
            with self.subTest(link=bad):
                self.assertIsNone(housing.clean_listing_url(bad))

    def test_the_button_names_the_site(self):
        other = housing.platform_of("https://www.idealista.pt/imovel/1/")
        self.assertEqual(other["name"], "Idealista")
        self.assertEqual(other["domain"], "idealista.pt")
        self.assertIsNone(housing.platform_of(None))


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "test.db")
        db.setup()
        conn = db.connect()
        self.ids = {}
        for name in ("Owner", "Ana", "Ben", "Cleo"):
            cur = conn.execute(
                "INSERT INTO users (email, name, created_at) VALUES (?, ?, ?)",
                (f"{name.lower()}@novasbe.pt", name, db.now()))
            self.ids[name] = cur.lastrowid
        conn.commit()
        conn.close()
        self.listing = db.create_listing(self.ids["Owner"], "ticket", "Concert",
                                         price=20)

    def tearDown(self):
        db.DB_PATH = self.original_path
        self.temp.cleanup()

    def write(self, who, at):
        conv = db.open_conversation(self.listing, self.ids[who])
        conn = db.connect()
        conn.execute("INSERT INTO messages (conversation_id, sender_id, body, created_at)"
                     " VALUES (?, ?, 'Still available?', ?)", (conv, self.ids[who], at))
        conn.commit()
        conn.close()
        return conv

    def test_order_is_who_wrote_first_not_who_opened_first(self):
        db.open_conversation(self.listing, self.ids["Ana"])   # opens, says nothing yet
        self.write("Ben", "2026-11-18T10:00:00+00:00")
        self.write("Ana", "2026-11-18T10:05:00+00:00")
        queue = db.interest_in(self.listing)
        self.assertEqual([q["name"] for q in queue], ["Ben", "Ana"])
        self.assertEqual(db.place_in_queue(queue, self.ids["Ana"]), 2)

    def test_opening_a_chat_without_writing_is_not_a_place(self):
        db.open_conversation(self.listing, self.ids["Cleo"])
        queue = db.interest_in(self.listing)
        self.assertEqual(queue, [])
        self.assertIsNone(db.place_in_queue(queue, self.ids["Cleo"]))

    def test_writing_again_does_not_move_you(self):
        self.write("Ana", "2026-11-18T09:00:00+00:00")
        self.write("Ben", "2026-11-18T09:30:00+00:00")
        self.write("Ana", "2026-11-18T11:00:00+00:00")   # a second message later
        queue = db.interest_in(self.listing)
        self.assertEqual([q["name"] for q in queue], ["Ana", "Ben"])


if __name__ == "__main__":
    unittest.main()


class AutofillTests(unittest.TestCase):
    def test_idealista_text(self):
        f = housing.parse_listing_text(
            "T3 flat for rent in Rua das Amoras, 271, Carcavelos e Parede\n"
            "1,500 €/month\n95 m² T3\nBalcony\nAvailable from January 1st.")
        self.assertEqual(f["price"], 1500)
        self.assertEqual(f["category"], "whole_flat")
        self.assertEqual(f["place"], "carcavelos")
        self.assertEqual(f["address"], "Rua das Amoras, 271")
        self.assertTrue(f["available_from"].endswith("-01-01"))
        self.assertIn("balcony", f["features"])

    def test_uniplaces_text(self):
        f = housing.parse_listing_text(
            "Large Double bed Bedroom close to Nova\nR. Flora, Carcavelos, Lisbon\n"
            "This is a Private bedroom\nAvailable from: December 2026\n"
            "Min stay: 30 nights\n€600 /month Bills included\nPets allowed")
        self.assertEqual(f["price"], 600)
        self.assertEqual(f["category"], "shared_flat")
        self.assertEqual(f["bills_included"], "1")
        self.assertEqual(f["available_from"], "2026-12-01")
        self.assertEqual(f["months_min"], "1")
        self.assertIn("pets", f["features"])

    def test_portuguese_and_missing_features(self):
        f = housing.parse_listing_text(
            "Estúdio na Avenida Marginal 118, Oeiras. 720 €/mês. "
            "Disponível a partir de 1 de fevereiro. Mobilado, sem estacionamento.")
        self.assertEqual(f["category"], "studio")
        self.assertEqual(f["place"], "oeiras")
        self.assertIn("furnished", f["features"])
        self.assertNotIn("parking", f["features"])   # "sem" means without

    def test_a_blocked_page_is_recognised(self):
        self.assertTrue(housing.looks_blocked(403, ""))
        self.assertTrue(housing.looks_blocked(200, "<html>captcha-delivery.com datadome</html>"))
        self.assertFalse(housing.looks_blocked(200, "<html><title>Room</title></html>"))


class SafeFetchTests(unittest.TestCase):
    def test_redirects_only_to_listed_sites(self):
        from urllib.request import Request
        handler = housing._CheckedRedirects()
        req = Request("https://www.uniplaces.com/accommodation/lisbon/1")
        for bad in ("http://169.254.169.254/latest/meta-data/",
                    "http://localhost:8000/admin", "https://evil.com/"):
            with self.subTest(target=bad):
                with self.assertRaises(ValueError):
                    handler.redirect_request(req, None, 302, "Found", {}, bad)
        ok = handler.redirect_request(req, None, 302, "Found", {},
                                      "https://www.uniplaces.com/accommodation/lisbon/2")
        self.assertIn("uniplaces.com", ok.full_url)

    def test_sites_that_block_apps_are_known(self):
        self.assertTrue(housing.blocks_apps("https://www.idealista.pt/imovel/1/"))
        self.assertTrue(housing.blocks_apps("https://www.imovirtual.com/pt/anuncio/x"))
        self.assertFalse(housing.blocks_apps("https://www.uniplaces.com/x"))

    def test_each_student_has_a_limit(self):
        housing._fetches.clear()
        for _ in range(housing.FETCH_LIMIT):
            self.assertTrue(housing.may_fetch(1, now=1000))
        self.assertFalse(housing.may_fetch(1, now=1000))
        self.assertTrue(housing.may_fetch(2, now=1000))          # someone else
        self.assertTrue(housing.may_fetch(1, now=1000 + housing.FETCH_WINDOW + 1))
