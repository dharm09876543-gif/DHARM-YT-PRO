import pytest
from src.database.connection import get_engine, run_migrations


@pytest.fixture
def engine(tmp_path):
    eng = get_engine(f"sqlite:////{tmp_path}/test.db")
    run_migrations(eng)
    return eng
