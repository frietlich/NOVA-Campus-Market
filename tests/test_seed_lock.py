"""The demo loader must never delete a database nobody offered up.

This project lost a day of real entries to seed.py once. The lock in
seed.main() is what stops that happening again, so it has a test of its
own: not to prove the demo data is right, but to prove the refusal works.
"""
import os
import sqlite3

import pytest

from app import db, seed


def test_it_refuses_a_database_it_was_not_given(tmp_path, monkeypatch):
    """The plain call, the one a careless test makes, must not delete.

    The file has to look like it lives somewhere real, so the temp folder
    the guard waves through is moved out of the way for the length of this
    test. If the guard ever stops working, what gets deleted here is a file
    this test made two lines above, and nothing else.
    """
    kept = tmp_path / "looks-real" / "campus.db"
    kept.parent.mkdir()
    sqlite3.connect(kept).close()
    before = kept.read_bytes()
    monkeypatch.setattr(db, "DB_PATH", str(kept))
    monkeypatch.setattr(seed.tempfile, "gettempdir", lambda: "/nowhere-near-here")

    with pytest.raises(seed.SeedRefused):
        seed.main()

    assert kept.exists()
    assert kept.read_bytes() == before


def test_a_temporary_path_needs_no_permission(tmp_path, monkeypatch):
    """Somewhere under the system temp folder it may go ahead on its own."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "demo.sqlite3"))
    seed.main()
    conn = db.connect()
    try:
        assert conn.execute("SELECT count(*) FROM listings").fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM users WHERE verified=1"
                            ).fetchone()[0] == len(seed.STUDENTS)
    finally:
        conn.close()


def test_the_demo_photos_stay_out_of_the_project(tmp_path, monkeypatch):
    """They used to be copied into app/static/uploads on every single run."""
    real = os.path.join(os.path.dirname(os.path.abspath(seed.__file__)),
                        "static", "uploads")
    before = set(os.listdir(real)) if os.path.isdir(real) else set()

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "demo.sqlite3"))
    seed.main()

    after = set(os.listdir(real)) if os.path.isdir(real) else set()
    assert after == before
    assert os.listdir(tmp_path / "static" / "uploads")


def test_a_deposit_without_months_stays_unknown(tmp_path, monkeypatch):
    """rent * None used to stop the whole loader. Mikkel found this one."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "demo.sqlite3"))
    seed.main()
    conn = db.connect()
    try:
        for _, title, _, _, rent, _, _, months, *_ in seed.HOUSING:
            row = conn.execute("SELECT deposit FROM listings WHERE title=?",
                               (title,)).fetchone()
            assert row is not None
            assert row["deposit"] == (None if months is None else rent * months)
    finally:
        conn.close()
