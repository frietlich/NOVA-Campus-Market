"""Filling a form from screenshots. Claude is never really called here."""
import io
import json
import os
import tempfile
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from app import db
from app import screenshots as shot


def png(width=1200, height=2600):
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, "PNG")
    return out.getvalue()


TICKET = {"is_match": True, "title": "Halloween Club Party", "category": "party",
          "event_date": "2026-10-31", "event_time": "22:00",
          "place": "Praça Luís de Camões", "address": "", "price": "25,00"}

FLAT = {"is_match": True, "title": "Bright room in a 3-bed flat", "kind": "shared_flat",
        "area": "carcavelos", "address": "Rua de Lisboa 12, Carcavelos",
        "price": "550", "bills_included": "no", "bills_estimate": "40",
        "deposit_months": "2", "available_from": "2027-01-15", "months_min": "5",
        "flatmates": "2", "features": ["furnished", "wifi", "jacuzzi"],
        "description": "Furnished room, 10 minutes walk to the beach."}


class FakeClient:
    """Stands in for anthropic.Anthropic and remembers what it was asked."""
    def __init__(self, answer, stop="end_turn"):
        self.asked = None
        reply = SimpleNamespace(
            stop_reason=stop,
            content=[SimpleNamespace(type="thinking", thinking=""),
                     SimpleNamespace(type="text", text=json.dumps(answer))])

        def create(**kwargs):
            self.asked = kwargs
            return reply
        self.messages = SimpleNamespace(create=create)


class ReadTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def read_with(self, kind, answer, pictures=None, stop="end_turn"):
        client = FakeClient(answer, stop)
        with mock.patch.object(shot, "_client", return_value=client):
            pictures = [png()] if pictures is None else pictures
            return shot.read(kind, pictures, date(2026, 10, 1)), client

    def test_a_ticket_screenshot_fills_the_form(self):
        result, _ = self.read_with("ticket", TICKET)
        self.assertEqual(result["fields"], {
            "title": "Halloween Club Party", "category": "party",
            "event_date": "2026-10-31", "event_time": "22:00",
            "place": "Praça Luís de Camões", "price": 25})

    def test_housing_screenshots_fill_the_housing_form(self):
        result, client = self.read_with("housing", FLAT, [png(), png()])
        self.assertEqual(result["site"], "your screenshots")
        self.assertEqual(result["fields"], {
            "title": "Bright room in a 3-bed flat", "category": "shared_flat",
            "place": "carcavelos", "address": "Rua de Lisboa 12, Carcavelos",
            "price": 550, "bills_included": "0", "bills_estimate": 40,
            "deposit_months": "2", "available_from": "2027-01-15",
            "months_min": "5", "flatmates": "2",
            "features": ["furnished", "wifi"],
            "description": "Furnished room, 10 minutes walk to the beach."})
        content = client.asked["messages"][0]["content"]
        self.assertEqual([c["type"] for c in content], ["image", "image", "text"])
        self.assertIn("these 2 screenshots", content[-1]["text"])
        self.assertIn("phone numbers", client.asked["system"])

    def test_what_is_sent_to_claude(self):
        _, client = self.read_with("ticket", TICKET)
        asked = client.asked
        self.assertEqual(asked["model"], "claude-opus-5-5")
        self.assertEqual(asked["output_config"]["effort"], "medium")
        self.assertNotIn("fallbacks", asked)
        self.assertEqual(asked["output_config"]["format"]["schema"], shot.SCHEMA["ticket"])
        self.assertIn("Today is 2026-10-01", asked["messages"][0]["content"][-1]["text"])
        self.assertIn("never copy QR codes", asked["system"])

    def test_the_picture_is_shrunk_before_it_goes_out(self):
        jpeg = shot.shrink(png(3000, 6000))
        with Image.open(io.BytesIO(jpeg)) as picture:
            self.assertLessEqual(max(picture.size), shot.LONG_EDGE)
            self.assertEqual(picture.format, "JPEG")

    def test_wrong_values_are_left_out(self):
        answer = dict(TICKET, event_date="31 Oct", event_time="10pm",
                      category="nightlife", price="free entry", title="x" * 90)
        result, _ = self.read_with("ticket", answer)
        self.assertEqual(set(result["fields"]), {"title", "place"})
        self.assertEqual(len(result["fields"]["title"]), 60)

    def test_wrong_housing_values_are_left_out(self):
        answer = dict(FLAT, kind="castle", area="porto", months_min="99",
                      available_from="soon", price="-5")
        fields = self.read_with("housing", answer)[0]["fields"]
        for name in ("category", "place", "months_min", "available_from", "price"):
            self.assertNotIn(name, fields)

    def test_too_many_pictures(self):
        result, client = self.read_with("ticket", TICKET, [png()] * (shot.MAX_IMAGES + 1))
        self.assertEqual(result["reason"], "many")
        self.assertIsNone(client.asked)

    def test_a_picture_that_shows_nothing_useful(self):
        result, _ = self.read_with("ticket", dict(TICKET, is_match=False))
        self.assertEqual((result["ok"], result["reason"]), (False, "empty"))

    def test_a_file_that_is_no_picture(self):
        result, client = self.read_with("ticket", TICKET, [png(), b"%PDF-1.7"])
        self.assertEqual(result["reason"], "picture")
        self.assertIsNone(client.asked)

    def test_a_refusal_or_failure_is_said_so(self):
        result, _ = self.read_with("ticket", TICKET, stop="refusal")
        self.assertEqual(result["reason"], "claude")

    def test_without_a_key_nothing_is_sent(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertEqual(shot.read("ticket", [png()])["reason"], "setup")


class LimitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "test.db")
        db.setup()
        self.user = db.create_user("12345@novasbe.pt", "Test T.")

    def tearDown(self):
        db.DB_PATH = self.original
        self.temp.cleanup()

    def test_each_student_has_a_daily_limit_per_picture(self):
        self.assertTrue(db.take_ai_read(self.user, 5, 4))
        self.assertFalse(db.take_ai_read(self.user, 5, 2))
        self.assertTrue(db.take_ai_read(self.user, 5, 1))
        self.assertFalse(db.take_ai_read(self.user, 5, 1))
        other = db.create_user("54321@novasbe.pt", "Other O.")
        self.assertTrue(db.take_ai_read(other, 5))


if __name__ == "__main__":
    unittest.main()
