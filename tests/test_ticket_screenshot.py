"""Filling a ticket from a screenshot. Claude is never really called here."""
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
from app import ticket_screenshot as shot


def png(width=1200, height=2600):
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, "PNG")
    return out.getvalue()


GOOD = {"is_event": True, "title": "Halloween Club Party", "category": "party",
        "event_date": "2026-10-31", "event_time": "22:00",
        "place": "Praça Luís de Camões", "address": "", "price": "25,00"}


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
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


class ReadTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def read_with(self, answer, data=None, stop="end_turn"):
        client = FakeClient(answer, stop)
        with mock.patch.object(shot, "_client", return_value=client):
            return shot.read(png() if data is None else data, date(2026, 10, 1)), client

    def test_a_screenshot_fills_the_form(self):
        result, _ = self.read_with(GOOD)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["fields"], {
            "title": "Halloween Club Party", "category": "party",
            "event_date": "2026-10-31", "event_time": "22:00",
            "place": "Praça Luís de Camões", "price": 25})

    def test_what_is_sent_to_claude(self):
        _, client = self.read_with(GOOD)
        asked = client.asked
        self.assertEqual(asked["model"], "claude-opus-5-5")
        self.assertEqual(asked["output_config"]["format"]["schema"], shot.SCHEMA)
        self.assertEqual(asked["fallbacks"], "default")
        picture = asked["messages"][0]["content"][0]
        self.assertEqual(picture["source"]["media_type"], "image/jpeg")
        self.assertIn("Today is 2026-10-01", asked["messages"][0]["content"][1]["text"])
        self.assertIn("never copy QR codes", asked["system"])

    def test_the_picture_is_shrunk_before_it_goes_out(self):
        jpeg = shot.shrink(png(3000, 6000))
        with Image.open(io.BytesIO(jpeg)) as picture:
            self.assertLessEqual(max(picture.size), shot.LONG_EDGE)
            self.assertEqual(picture.format, "JPEG")

    def test_wrong_values_are_left_out(self):
        answer = dict(GOOD, event_date="31 Oct", event_time="10pm",
                      category="nightlife", price="free entry", title="x" * 90)
        result, _ = self.read_with(answer)
        self.assertEqual(set(result["fields"]), {"title", "place"})
        self.assertEqual(len(result["fields"]["title"]), 60)

    def test_a_picture_that_is_no_event(self):
        result, _ = self.read_with(dict(GOOD, is_event=False))
        self.assertEqual((result["ok"], result["reason"]), (False, "empty"))

    def test_a_file_that_is_no_picture(self):
        result, client = self.read_with(GOOD, data=b"%PDF-1.7 not a picture")
        self.assertEqual(result["reason"], "picture")
        self.assertIsNone(client.asked)

    def test_a_refusal_or_failure_is_said_so(self):
        result, _ = self.read_with(GOOD, stop="refusal")
        self.assertEqual(result["reason"], "claude")

    def test_without_a_key_nothing_is_sent(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertEqual(shot.read(png())["reason"], "setup")


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

    def test_each_student_has_a_daily_limit(self):
        for _ in range(3):
            self.assertTrue(db.take_ai_read(self.user, 3))
        self.assertFalse(db.take_ai_read(self.user, 3))
        other = db.create_user("54321@novasbe.pt", "Other O.")
        self.assertTrue(db.take_ai_read(other, 3))


if __name__ == "__main__":
    unittest.main()
