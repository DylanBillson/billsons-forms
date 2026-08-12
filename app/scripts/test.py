from __future__ import annotations

import os
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url


def require_test_database_url() -> tuple[str, URL]:
    value = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not value:
        raise SystemExit("TEST_DATABASE_URL is required.")
    try:
        url = make_url(value)
    except Exception as exc:
        raise SystemExit("TEST_DATABASE_URL is not a valid database URL.") from exc
    if url.get_backend_name() != "postgresql":
        raise SystemExit("TEST_DATABASE_URL must use PostgreSQL.")
    database = url.database or ""
    if "test" not in database.lower():
        raise SystemExit("Refusing to recreate a database whose name does not contain 'test'.")
    return value, url


def recreate_database(url) -> None:
    database = url.database
    connection_args = {
        "dbname": os.environ.get("TEST_DATABASE_ADMIN_DB", "postgres"),
        "user": url.username,
        "password": url.password,
        "host": url.host,
        "port": url.port,
        **dict(url.query),
    }
    with psycopg.connect(**{key: value for key, value in connection_args.items() if value is not None}, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (database,),
            )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
            )
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))


def main() -> int:
    test_url, parsed_url = require_test_database_url()
    recreate_database(parsed_url)
    environment = os.environ.copy()
    environment["DATABASE_URL"] = test_url
    environment["TEST_DATABASE_URL"] = test_url

    migration = subprocess.run(["alembic", "upgrade", "head"], env=environment, check=False)
    if migration.returncode:
        return migration.returncode
    tests = subprocess.run([sys.executable, "-m", "pytest"], env=environment, check=False)
    return tests.returncode


if __name__ == "__main__":
    raise SystemExit(main())
