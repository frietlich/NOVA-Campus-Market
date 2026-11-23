"""The day turns over at six in the morning, not at midnight.

An entry whose date is the 23rd is still live through the night and closes
on the 24th at six. The sweep that closes it and the list that shows it have
to agree on that, or a ticket sits open for six hours while nobody can find
it any more.
"""
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from app import db


def at(day, hour, run):
    """Run something as if it were that day at half past that hour."""
    fake = datetime.fromisoformat(f"{day} {hour:02d}:30:00").astimezone()
    with mock.patch("app.db.datetime") as stand_in:
        stand_in.now.return_value = fake
        stand_in.fromisoformat = datetime.fromisoformat
        stand_in.strptime = datetime.strptime
        return run()


class ClosingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "test.db")
        db.setup()
        self.owner = db.create_user("77777@novasbe.pt", "Owner O.")

    def tearDown(self):
        db.DB_PATH = self.original
        self.temp.cleanup()

    def entries(self):
        """One ticket and one group, both for the 23rd."""
        ticket = db.create_listing(self.owner, "ticket", "Party", price=10,
                                   event_date="2026-11-23", event_time="23:00",
                                   place="Urban Beach")
        group = db.create_listing(self.owner, "group", "Team", course_id=1,
                                  group_size=4, hand_in="2026-11-23")
        return ticket, group

    def test_the_day_still_says_yesterday_until_six(self):
        for hour, expected in ((0, "2026-11-23"), (5, "2026-11-23"),
                               (6, "2026-11-24"), (14, "2026-11-24")):
            with self.subTest(hour=hour):
                self.assertEqual(at("2026-11-24", hour, db.active_day), expected)

    def test_nothing_closes_in_the_night(self):
        for hour in (0, 3, 5):
            with self.subTest(hour=hour):
                ticket, group = self.entries()
                at("2026-11-24", hour, lambda: db.close_past_dates(force=True))
                self.assertEqual(db.get_listing(ticket)["status"], "open")
                self.assertEqual(db.get_listing(group)["status"], "open")

    def test_both_close_at_six_the_next_morning(self):
        ticket, group = self.entries()
        at("2026-11-24", 6, lambda: db.close_past_dates(force=True))
        self.assertEqual(db.get_listing(ticket)["status"], "closed")
        self.assertEqual(db.get_listing(group)["status"], "closed")

    def test_the_list_hides_it_at_the_same_moment_it_closes(self):
        """Otherwise an entry is open for six hours but nowhere to be seen."""
        ticket, _ = self.entries()
        shown = at("2026-11-24", 5,
                   lambda: [r["id"] for r in db.listings_of_type("ticket")])
        self.assertIn(ticket, shown)
        shown = at("2026-11-24", 6,
                   lambda: [r["id"] for r in db.listings_of_type("ticket")])
        self.assertNotIn(ticket, shown)


if __name__ == "__main__":
    unittest.main()
