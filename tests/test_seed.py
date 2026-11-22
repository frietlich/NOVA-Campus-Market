"""A new developer can load the complete fictional demo without a crash."""
from app import db, seed


def test_seed_keeps_unknown_deposit_and_converts_known_months(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "demo.sqlite3"))
    seed.main()
    connection = db.connect()
    try:
        for _, title, _, _, rent, _, _, months, *_ in seed.HOUSING:
            row = connection.execute("SELECT deposit FROM listings WHERE title=?", (title,)).fetchone()
            assert row is not None
            assert row["deposit"] == (None if months is None else rent * months)
        assert connection.execute("SELECT COUNT(*) FROM users WHERE verified=1").fetchone()[0] == len(seed.STUDENTS)
        assert connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] > 0
    finally:
        connection.close()
