"""Turning a maps link into an address.

The live lookup is stood in for everywhere below, so these say nothing
about whether OpenStreetMap is up. What they pin down is ours: which links
we take, which we refuse to fetch, where the coordinates come from, and
what a half an answer turns into.
"""
import io
import unittest
import urllib.error
from email.message import Message
from unittest import mock

from app import maps

PLACE = ("https://www.google.com/maps/place/K+Urban+Beach+Club/"
         "@38.7040241,-9.1613882,16.42z/data=!4m6!3m5!1s0xd19349b2b877d4b:"
         "0x67efdbd6bce7e90b!8m2!3d38.7038144!4d-9.1554334!16s%2Fg%2F11b62x292v")


class LinkTests(unittest.TestCase):
    def test_only_google_and_apple_are_taken(self):
        for good in ("https://maps.app.goo.gl/x7Qd", "google.com/maps/place/x",
                     "https://maps.apple.com/?ll=38.7,-9.1", "https://google.pt/maps",
                     # Apple's own short domain, what an iPhone shares now.
                     "https://maps.apple/p/8RBSJnjIyLPD3Y"):
            with self.subTest(link=good):
                self.assertIsNotNone(maps.clean_url(good))
        for bad in ("https://evil.com/maps.google.com", "https://google.com.evil.com/",
                    "https://maps.google.com:8080/x", "http://user:pw@google.com/maps",
                    "https://openstreetmap.org/x", "not a link at all"):
            with self.subTest(link=bad):
                self.assertIsNone(maps.clean_url(bad))

    def test_the_place_beats_the_centre_of_the_map(self):
        """!3d/!4d is the place itself, @ is wherever the map happened to sit."""
        self.assertEqual(maps.coordinates_in(PLACE), (38.7038144, -9.1554334))

    def test_the_centre_will_do_when_there_is_nothing_better(self):
        self.assertEqual(maps.coordinates_in("https://www.google.com/maps/@38.69,-9.31,17z"),
                         (38.69, -9.31))

    def test_a_coordinate_in_the_query_counts(self):
        self.assertEqual(maps.coordinates_in("https://maps.apple.com/?ll=38.7,-9.15"),
                         (38.7, -9.15))

    def test_a_link_with_no_place_in_it_gives_nothing(self):
        self.assertIsNone(maps.coordinates_in("https://maps.app.goo.gl/x7Qd"))

    def test_nonsense_coordinates_are_thrown_away(self):
        self.assertIsNone(maps.coordinates_in("https://maps.apple.com/?ll=999.0,-9.15"))

    def test_a_redirect_off_the_list_is_not_followed(self):
        """A short link is only followed while it stays on maps."""
        headers = Message()
        headers["Location"] = "http://169.254.169.254/latest/meta-data/"
        jump = urllib.error.HTTPError("https://maps.app.goo.gl/x", 302, "Found",
                                      headers, io.BytesIO())
        with mock.patch.object(maps._opener, "open", side_effect=jump) as opened:
            with self.assertRaises(ValueError):
                maps.follow("https://maps.app.goo.gl/x")
        self.assertEqual(opened.call_count, 1)

    def test_a_short_link_is_followed_to_the_real_one(self):
        headers = Message()
        headers["Location"] = PLACE
        jump = urllib.error.HTTPError("https://maps.app.goo.gl/x", 302, "Found",
                                      headers, io.BytesIO())
        answer = mock.MagicMock()
        answer.read.return_value = b""
        answer.__enter__.return_value = answer
        with mock.patch.object(maps._opener, "open", side_effect=[jump, answer]):
            landed = maps.follow("https://maps.app.goo.gl/x")
        self.assertEqual(maps.coordinates_in(landed), (38.7038144, -9.1554334))


class SpelledOutTests(unittest.TestCase):
    """What a link says outright, which beats looking a coordinate up."""

    APPLE = ("https://maps.apple.com/place?address=R.%20de%20S%C3%A3o%20Pedro"
             "%20de%20Alc%C3%A2ntara%2035,%201250-237%20Lisboa,%20Portugal"
             "&coordinate=38.713882,-9.144010&name=Lumi%20Rooftop")

    def test_the_address_an_apple_link_carries(self):
        self.assertEqual(maps.address_in(self.APPLE),
                         "R. de São Pedro de Alcântara 35, 1250-237 Lisboa")

    def test_a_name_is_not_an_address(self):
        """K Urban Beach Club is what Google writes when a place was tapped."""
        self.assertIsNone(maps.address_in(PLACE))

    def test_a_searched_address_in_a_google_link(self):
        self.assertEqual(
            maps.address_in("https://www.google.com/maps/place/"
                            "Cais+da+Viscondessa,+1200-109+Lisboa/@38.70,-9.15,17z"),
            "Cais da Viscondessa, 1200-109 Lisboa")

    def test_the_link_wins_over_the_coordinates(self):
        """The place said its own address; the spot nearby may say another."""
        with mock.patch.object(maps, "follow", side_effect=lambda u: u), \
             mock.patch.object(maps, "address_at", return_value="Somewhere else 1, 1000-000 X"):
            self.assertEqual(maps.address_from_link(self.APPLE)["address"],
                             "R. de São Pedro de Alcântara 35, 1250-237 Lisboa")


class CombineTests(unittest.TestCase):
    """A page knows its own door number, a lookup knows the post code."""

    def test_the_same_street_keeps_the_page_number(self):
        """And comes out the Portuguese way round, door behind the street."""
        self.assertEqual(
            maps.combine("19 R. do Prior, Faro", "Rua do Prior 46, 8000-301 Faro"),
            "R. do Prior 19, 8000-301 Faro")

    def test_a_different_street_leaves_the_lookup_alone(self):
        """Luma writes the venue's name where the street goes."""
        self.assertEqual(
            maps.combine("Damas, Lisboa", "Rua da Voz do Operário 60, 1100-395 Lisboa"),
            "Rua da Voz do Operário 60, 1100-395 Lisboa")

    def test_nothing_from_the_page_means_the_lookup(self):
        self.assertEqual(maps.combine("", "Rua X 1, 1000-000 Lisboa"),
                         "Rua X 1, 1000-000 Lisboa")

    def test_a_lookup_without_a_post_code_is_not_borrowed_from(self):
        self.assertEqual(maps.combine("19 R. do Prior, Faro", "Rua do Prior 46, Faro"),
                         "Rua do Prior 46, Faro")


class LineTests(unittest.TestCase):
    def test_the_portuguese_order(self):
        self.assertEqual(maps.one_line({
            "road": "Rua Alto da Loba", "house_number": "5",
            "postcode": "2780-176", "town": "Oeiras"}),
            "Rua Alto da Loba 5, 2780-176 Oeiras")

    def test_a_street_with_no_number_is_still_an_address(self):
        self.assertEqual(maps.one_line({
            "road": "Avenida de Brasília", "postcode": "1399-036", "city": "Lisboa"}),
            "Avenida de Brasília, 1399-036 Lisboa")

    def test_a_door_spanning_several_numbers_keeps_the_first(self):
        """Damas in Lisbon is 60, 62 and 64. One of them is enough."""
        self.assertEqual(maps.one_line({
            "road": "Rua da Voz do Operário", "house_number": "60,62,64",
            "postcode": "1100-395", "city": "Lisboa"}),
            "Rua da Voz do Operário 60, 1100-395 Lisboa")

    def test_the_country_comes_off_the_end(self):
        for line, want in (
                ("Rua Do Grilo 119, 1950-142 Lisbon, Portugal",
                 "Rua Do Grilo 119, 1950-142 Lisbon"),
                ("63 Grand Street, NY 11249, EE. UU.", "63 Grand Street, NY 11249"),
                ("Rua X 1, 1000-000 Lisboa", "Rua X 1, 1000-000 Lisboa")):
            with self.subTest(line=line):
                self.assertEqual(maps.plain_address(line), want)

    def test_the_door_goes_behind_the_street(self):
        """Some sites write it the English way round. Portugal does not."""
        for line, want in (
                ("19 R. do Prior, 8000-301 Faro", "R. do Prior 19, 8000-301 Faro"),
                ("112 A Rua Luís de Camões, 1300-361 Lisboa",
                 "Rua Luís de Camões 112 A, 1300-361 Lisboa"),
                ("60-64 Rua da Voz do Operário, 1100-395 Lisboa",
                 "Rua da Voz do Operário 60-64, 1100-395 Lisboa"),
                # Already right, and left alone.
                ("Rua Do Grilo 119, 1950-142 Lisbon", "Rua Do Grilo 119, 1950-142 Lisbon"),
                # A street named after a date is not a door number.
                ("Avenida 25 de Abril, 2750-642 Cascais",
                 "Avenida 25 de Abril, 2750-642 Cascais"),
                ("25 de Abril 14, 2750-642 Cascais", "25 de Abril 14, 2750-642 Cascais")):
            with self.subTest(line=line):
                self.assertEqual(maps.plain_address(line), want)

    def test_without_a_post_code_nothing_comes_back(self):
        """Half an address in the box is worse than an empty box."""
        self.assertIsNone(maps.one_line({"road": "Avenida de Brasília", "city": "Lisboa"}))

    def test_without_a_street_nothing_comes_back(self):
        self.assertIsNone(maps.one_line({"postcode": "1399-036", "city": "Lisboa"}))


class WholeTests(unittest.TestCase):
    def test_a_link_we_do_not_take_is_refused_before_anything_is_fetched(self):
        with mock.patch.object(maps, "follow") as followed:
            self.assertEqual(maps.address_from_link("https://evil.com/x"),
                             {"ok": False, "reason": "not_maps"})
        followed.assert_not_called()

    def test_the_place_link_all_the_way_through(self):
        with mock.patch.object(maps, "follow", side_effect=lambda u: u), \
             mock.patch.object(maps, "address_at",
                               return_value="Avenida de Brasília, 1399-036 Lisboa"):
            self.assertEqual(maps.address_from_link(PLACE),
                             {"ok": True, "address": "Avenida de Brasília, 1399-036 Lisboa"})

    def test_a_spot_with_nothing_on_it_says_so(self):
        with mock.patch.object(maps, "follow", side_effect=lambda u: u), \
             mock.patch.object(maps, "address_at", return_value=None):
            self.assertEqual(maps.address_from_link(PLACE)["reason"], "nothing_there")


if __name__ == "__main__":
    unittest.main()
