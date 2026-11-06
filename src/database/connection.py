"""Database connection. PostgreSQL production, SQLite local testing."""
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import ROOT, Env

MIGRATIONS = ROOT / "migrations"


def get_engine(url: str | None = None) -> Engine:
    url = url or Env().database_url
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        Path(ROOT / url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        url = "sqlite:///" + str(ROOT / url.removeprefix("sqlite:///"))
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url, future=True, pool_pre_ping=True)
    if eng.dialect.name == "sqlite":
        import sqlite3
        from datetime import date, datetime

        from sqlalchemy import event
        # Python 3.12 default adapter deprecated: ISO format khud set (string compare bhi sahi rehta hai)
        sqlite3.register_adapter(datetime, lambda d: d.isoformat(" "))
        sqlite3.register_adapter(date, lambda d: d.isoformat())

        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return eng


def _to_sqlite(sql: str) -> str:
    """Postgres SQL ko SQLite-compatible banata hai (sirf local testing)."""
    return (sql.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
               .replace("TIMESTAMPTZ", "TIMESTAMP")
               .replace("DEFAULT NOW()", "DEFAULT CURRENT_TIMESTAMP")
               .replace("JSONB", "TEXT"))


def run_migrations(engine: Engine) -> list[str]:
    applied = []
    files = sorted(MIGRATIONS.glob("*.sql"))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)"))
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))}
        for f in files:
            if f.stem in done:
                continue
            sql = f.read_text(encoding="utf-8")
            if engine.dialect.name == "sqlite":
                sql = _to_sqlite(sql)
            for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
                if body:
                    conn.execute(text(body))
            conn.execute(text("INSERT INTO schema_migrations(version) VALUES (:v)"), {"v": f.stem})
            applied.append(f.stem)
    return applied
