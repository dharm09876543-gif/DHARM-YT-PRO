"""Create database tables: python scripts/initialize_db.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.database.connection import get_engine, run_migrations  # noqa: E402

eng = get_engine()
done = run_migrations(eng)
print(f"Database: {eng.dialect.name}. New migrations: {done or 'none (all already applied)'}")
