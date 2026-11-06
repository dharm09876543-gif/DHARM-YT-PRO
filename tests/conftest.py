import os

import pytest
from src.database.connection import get_engine, run_migrations


@pytest.fixture
def engine(tmp_path):
    pg = os.getenv("TEST_DATABASE_URL")       # CI: real PostgreSQL par bhi same tests (opt-in)
    if pg:
        from sqlalchemy import text
        eng = get_engine(pg)
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
    else:
        eng = get_engine(f"sqlite:////{tmp_path}/test.db")
    run_migrations(eng)
    return eng


CHAN = "UC" + "c" * 22


@pytest.fixture
def cipher():
    from src.auth.encryption import TokenCipher, generate_key
    return TokenCipher(generate_key())


@pytest.fixture
def chsvc(engine, cipher):
    from src.services.channel_service import ChannelService
    return ChannelService(engine, cipher)


@pytest.fixture
def channel(chsvc):
    chsvc.add(CHAN, "Dharm Test", "root", "Asia/Kolkata")
    chsvc.save_tokens(CHAN, "1//refresh-x", "ya29.access-x")
    return chsvc.get(CHAN)
