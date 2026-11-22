"""Filling a ticket from the link to the event. No test here goes online."""
import io
import json
import unittest
import urllib.error
from email.message import Message
from unittest import mock

from app import ticket_import as t


def page_with(event):
    return ('<html><head><meta property="og:title" content="Fallback | DICE">'
            '<script type="application/ld+json">' + json.dumps(event)
            + '</script></head><body></body></html>')


DICE_LIKE = {
    "@context": "https://schema.org", "@type": "MusicEvent",
    "name": "Dinis Mota",
    "startDate": "2026-12-09T21:30:00+00:00",
    "location": {"@type": "Place", "name": "Casa Capitão",
                 "address": {"@type": "PostalAddress",
                             "streetAddress": "Rua Do Grilo 119, 1950-142 Lisbon, Lisbon, Portugal",
                             "addressLocality": "Lisbon"}},
    "offers": [{"@type": "Offer", "price": "11.00", "priceCurrency": "EUR"}],
}


class LinkTests(unittest.TestCase):
    def test_known_sites_are_kept_and_made_https(self):
        self.assertEqual(t.clean_url("luma.com/np2zn91k"), "https://luma.com/np2zn91k")
        self.assertEqual(t.clean_url("http://www.eventbrite.pt/e/x-1#tickets"),
                         "https://www.eventbrite.pt/e/x-1")

    def test_anything_else_is_refused(self):
        for bad in ("https://evil.com/luma.com", "https://luma.com.evil.com/",
                    "https://notdice.fm/", "https://me:pw@dice.fm/",
                    "https://dice.fm:8443/", "javascript:alert(1)", "dice.fm/a b", ""):
            with self.subTest(link=bad):
                self.assertIsNone(t.clean_url(bad))

    def test_a_redirect_off_the_list_is_not_followed(self):
        headers = Message()
        headers["Location"] = "http://169.254.169.254/latest/meta-data/"
        jump = urllib.error.HTTPError("https://dice.fm/x", 302, "Found", headers, io.BytesIO())
        with mock.patch.object(t._opener, "open", side_effect=jump) as opened:
            self.assertEqual(t.autofill("https://dice.fm/x")["reason"], "site")
        self.assertEqual(opened.call_count, 1)

    def test_a_blocked_site_is_said_so(self):
        refused = urllib.error.HTTPError("https://shotgun.live/x", 429, "Too many",
                                         Message(), io.BytesIO())
        with mock.patch.object(t._opener, "open", side_effect=refused):
            result = t.autofill("shotgun.live/en/events/x")
        self.assertEqual((result["ok"], result["reason"], result["site"]),
                         (False, "blocked", "Shotgun"))


class ReadingTests(unittest.TestCase):
    def test_a_dice_page_fills_every_field(self):
        found = t.parse_event_page(page_with(DICE_LIKE), "DICE")
        self.assertEqual(found, {
            "title": "Dinis Mota", "event_date": "2026-12-09", "event_time": "21:30",
            "place": "Casa Capitão",
            # The country comes off the end, the form never asks for it.
            "address": "Rua Do Grilo 119, 1950-142 Lisbon",
            "price": 11, "category": "concert",
        })

    def test_the_coordinates_come_through_for_the_caller(self):
        """Luma's shape: the venue's name in the street field, plus a point."""
        event = dict(DICE_LIKE, location={
            "@type": "Place", "name": "Damas",
            "address": {"streetAddress": "Damas", "addressLocality": "Lisboa"},
            "geo": {"latitude": 38.7164888, "longitude": -9.129402}})
        found = t.parse_event_page(page_with(event))
        self.assertEqual(found["place"], "Damas")
        self.assertNotIn("address", found)
        self.assertEqual(found["_point"], (38.7164888, -9.129402))

    def test_a_name_in_the_address_is_left_out(self):
        """A page that writes the venue, or the event, where the street goes.

        The venue still comes through as the venue. The address box stays
        empty so it asks to be filled, rather than quietly holding a line
        that would send somebody to the wrong place.
        """
        event = dict(DICE_LIKE, location={"@type": "Place", "name": "Casa Capitão",
                                          "address": "World Read Lisboa"})
        found = t.parse_event_page(page_with(event))
        self.assertEqual(found["place"], "Casa Capitão")
        self.assertNotIn("address", found)

    def test_an_address_without_a_number_but_with_a_post_code_stays(self):
        event = dict(DICE_LIKE, location={
            "@type": "Place", "name": "Casa Capitão",
            "address": {"streetAddress": "Praça do Comércio",
                        "postalCode": "1100-148", "addressLocality": "Lisbon"}})
        # The post code and the town are one thing, not two items in a list.
        self.assertEqual(t.parse_event_page(page_with(event))["address"],
                         "Praça do Comércio, 1100-148 Lisbon")

    def test_summer_time_is_lisbon_time(self):
        event = dict(DICE_LIKE, startDate="2026-07-04T21:00:00Z")
        self.assertEqual(t.parse_event_page(page_with(event))["event_time"], "22:00")

    def test_a_time_without_a_zone_stays_as_written(self):
        event = dict(DICE_LIKE, startDate="2026-12-01T20:00:00.0000000")
        found = t.parse_event_page(page_with(event))
        self.assertEqual((found["event_date"], found["event_time"]), ("2026-12-01", "20:00"))

    def test_a_club_night_is_a_party_even_as_music_event(self):
        event = dict(DICE_LIKE, name="Techno night with DJ Someone")
        self.assertEqual(t.parse_event_page(page_with(event))["category"], "party")

    def test_the_event_can_sit_inside_a_graph(self):
        page = page_with({"@graph": [{"@type": "WebPage"}, DICE_LIKE]})
        self.assertEqual(t.parse_event_page(page)["title"], "Dinis Mota")

    def test_without_an_event_only_the_title_comes_back(self):
        page = '<meta property="og:title" content="Big Night | Tickets | DICE">'
        self.assertEqual(t.parse_event_page(page), {"title": "Big Night"})

    def test_a_title_with_a_bar_in_it_stays_whole(self):
        event = dict(DICE_LIKE, name="THE GIFT | CORAL EXPANDED")
        self.assertEqual(t.parse_event_page(page_with(event))["title"],
                         "THE GIFT | CORAL EXPANDED")

    def test_prices_in_other_currencies_are_left_out(self):
        event = dict(DICE_LIKE, offers={"price": "30", "priceCurrency": "GBP"})
        self.assertNotIn("price", t.parse_event_page(page_with(event)))


class LookupTests(unittest.TestCase):
    """The point a page carries, turned into a street by the maps lookup."""

    LUMA = {"@context": "https://schema.org", "@type": "Event",
            "name": "Freequencies", "startDate": "2026-11-25T17:00:00+00:00",
            "location": {"@type": "Place", "name": "Damas",
                         "address": {"streetAddress": "Damas",
                                     "addressLocality": "Lisboa"},
                         "geo": {"latitude": 38.7164888,
                                 "longitude": -9.129402}}}

    def run_with(self, looked_up):
        with mock.patch.object(t, "fetch", return_value=(200, page_with(self.LUMA))), \
             mock.patch.object(t.maps, "address_at", return_value=looked_up) as asked:
            answer = t.autofill("https://luma.com/logos-gcp2")
        return answer, asked

    def test_the_street_is_looked_up_and_the_point_does_not_leak(self):
        answer, asked = self.run_with("Rua da Voz do Operário 60, 1100-395 Lisboa")
        asked.assert_called_once_with(38.7164888, -9.129402)
        self.assertEqual(answer["fields"]["address"],
                         "Rua da Voz do Operário 60, 1100-395 Lisboa")
        self.assertNotIn("_point", answer["fields"])

    def test_a_lookup_that_finds_nothing_leaves_the_box_empty(self):
        answer, _ = self.run_with(None)
        self.assertNotIn("address", answer["fields"])
        self.assertNotIn("_point", answer["fields"])
        self.assertEqual(answer["fields"]["place"], "Damas")


class PageTests(unittest.TestCase):
    def test_the_form_fills_only_for_someone_logged_in(self):
        from fastapi.testclient import TestClient
        from app import main
        with TestClient(main.app, headers={"origin": "http://testserver"}) as client:
            answer = client.post("/new/ticket-autofill", data={"url": "dice.fm/x"})
        self.assertEqual(answer.status_code, 401)


if __name__ == "__main__":
    unittest.main()
