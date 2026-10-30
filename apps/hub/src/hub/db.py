"""Postgres for team mode: the one place that imports the driver, and the migrations.

The hub has no dependencies and starts in a second without a database. Team mode is the exception:
set VISHAP_HUB_DATABASE_URL and the driver (`pip install "vishap-hub[postgres]"`) is imported here, nowhere
else. Without the variable none of this is loaded.
"""
from __future__ import annotations

from pathlib import Path

APP_ROLE = "vishap_hub_app"
MIGRATIONS = Path(__file__).parent / "migrations"


def driver():
    try:
        import psycopg
    except ImportError as exc:                                    # pragma: no cover - environment
        raise RuntimeError('team mode needs the Postgres driver: pip install "vishap-hub[postgres]"') from exc
    return psycopg


def connect(url: str, **kwargs):
    """A libpq URL (postgresql://...), with a short connect timeout so a dead database fails fast."""
    return driver().connect(url, connect_timeout=5, **kwargs)


def migrate(admin_url: str, app_password: str | None = None) -> list[str]:
    """Apply the migrations that are not applied yet, as the database owner. Returns their names.

    `app_password` gives the server's role a login; without it the role stays NOLOGIN, as the migration
    made it, and the operator sets the password themselves.
    """
    from psycopg import sql

    applied: list[str] = []
    with connect(admin_url, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                     "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            applied.append(path.name)
        if app_password is not None:
            conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(APP_ROLE), sql.Literal(app_password)))
    return applied
