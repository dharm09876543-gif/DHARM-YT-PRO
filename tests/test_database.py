import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.database.connection import run_migrations

TABLES = {"channels", "oauth_credentials", "videos", "upload_sessions", "upload_history",
          "quota_usage", "schedules", "analytics_snapshots"}


def _chan(conn, cid="UC" + "a" * 22):
    conn.execute(text("INSERT INTO channels(channel_id, channel_name, drive_folder_id) VALUES (:c,'T','f')"), {"c": cid})


def test_all_tables_created(engine):
    with engine.connect() as c:
        names = {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert TABLES <= names


def test_migrations_idempotent(engine):
    assert run_migrations(engine) == []


def test_duplicate_video_blocked(engine):
    with engine.begin() as c:
        _chan(c)
        c.execute(text("INSERT INTO videos(channel_id, drive_file_id, filename) VALUES ('UC%s','d1','a.mp4')" % ("a" * 22)))
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("INSERT INTO videos(channel_id, drive_file_id, filename) VALUES ('UC%s','d1','a.mp4')" % ("a" * 22)))


def test_foreign_key_enforced(engine):
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("INSERT INTO videos(channel_id, drive_file_id, filename) VALUES ('UCnope','d1','a.mp4')"))


def test_invalid_status_rejected(engine):
    with engine.begin() as c:
        _chan(c)
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("INSERT INTO videos(channel_id, drive_file_id, filename, upload_status) VALUES ('UC%s','d2','b.mp4','DONE')" % ("a" * 22)))


def test_transaction_rollback(engine):
    try:
        with engine.begin() as c:
            _chan(c, "UC" + "b" * 22)
            raise RuntimeError
    except RuntimeError:
        pass
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM channels")).scalar() == 0


def test_one_active_session_per_video(engine):
    with engine.begin() as c:
        _chan(c)
        c.execute(text("INSERT INTO videos(channel_id, drive_file_id, filename) VALUES ('UC%s','d3','c.mp4')" % ("a" * 22)))
        c.execute(text("INSERT INTO upload_sessions(video_id) VALUES (1)"))
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("INSERT INTO upload_sessions(video_id) VALUES (1)"))
