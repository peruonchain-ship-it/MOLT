"""Small connection adapter; application SQL stays parameterized on both databases."""

from urllib.parse import urlparse

import certifi
import psycopg


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def row_factory(cursor):
    columns = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Row(zip(columns, values, strict=True))


def connect(url):
    # Cloud connections always verify the server identity, even if a provider URL says sslmode=require.
    local = urlparse(url).hostname in ("localhost", "127.0.0.1", "::1")
    options = {} if local else {"sslmode": "verify-full", "sslrootcert": certifi.where()}
    return psycopg.connect(url, connect_timeout=15, row_factory=row_factory, **options)


class Connection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        # All callers use static SQL. Values remain bound parameters, never interpolated.
        return self.connection.execute(sql.replace("?", "%s"), params)

    def executescript(self, script):
        for statement in script.split(";"):
            statement = statement.strip()
            if statement and not statement.startswith("PRAGMA"):
                statement = statement.replace("id INTEGER PRIMARY KEY,", "id BIGSERIAL PRIMARY KEY,")
                statement = statement.replace(" REAL", " DOUBLE PRECISION")
                self.connection.execute(statement)
