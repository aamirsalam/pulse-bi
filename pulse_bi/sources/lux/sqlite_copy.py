"""Read a copy of a LUX database away from Windows.

pyodbc and the Microsoft Access ODBC driver only exist on Windows. On Linux
(a server, a CI job) copy the tables LuxSource reads into SQLite with
mdbtools, and set [source] sqlite (or LUX_SQLITE) to the copy.

connect() returns a connection that behaves like pyodbc as far as
LuxSource needs: rows with attribute access by column name (any case),
dates as datetime, and Access's IIF function. The Access SQL in
source.py runs unchanged on SQLite.

    python -m pulse_bi.sources.lux.sqlite_copy <database.mdb> <copy.sqlite>
"""

import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime

# Tables read by source.py. Add a table here when it queries a new one.
TABLES = (
    "ItemMaster",
    "InvoiceMaster",
    "InvoiceChild",
    "InvoiceReturnMaster",
    "InvoiceReturnChild",
    "purchasemaster",
    "PurchaseChild",
    "PurchaseReturnMaster",
    "PurchaseReturnChild",
    "Account",
    "AccTransMast",
    "AccTransChld",
)

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def mdbtools(*args):
    result = subprocess.run(
        list(args), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout


def convert(mdb_path, sqlite_path):
    """Copy TABLES from the .mdb into a new SQLite file."""
    temporary = sqlite_path + ".tmp"
    if os.path.exists(temporary):
        os.remove(temporary)

    connection = sqlite3.connect(temporary)
    try:
        for table in TABLES:
            connection.executescript(mdbtools("mdb-schema", "-T", table, mdb_path, "sqlite"))
            rows = mdbtools("mdb-export", "-I", "sqlite", "-D", DATE_FORMAT, mdb_path, table)
            connection.executescript("BEGIN;\n" + rows + "\nCOMMIT;")
            count = connection.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            print(f"  {table}: {count} rows")
    finally:
        connection.close()

    os.replace(temporary, sqlite_path)


class Row(tuple):
    """A result row: by index like a tuple, or by column name like pyodbc."""

    def __new__(cls, names, values):
        values = [
            datetime.strptime(value, DATE_FORMAT)
            if isinstance(value, str) and DATE_PATTERN.match(value)
            else value
            for value in values
        ]
        row = super().__new__(cls, values)
        row._names = names
        return row

    def __getattr__(self, name):
        try:
            return self[self._names[name.lower()]]
        except KeyError:
            raise AttributeError(name) from None


class Cursor:
    def __init__(self, connection):
        self._cursor = connection.cursor()

    def execute(self, sql, *params):
        self._cursor.execute(sql, params)
        return self

    def _names(self):
        return {
            column[0].split(".")[-1].lower(): index
            for index, column in enumerate(self._cursor.description)
        }

    def fetchall(self):
        names = self._names()
        return [Row(names, values) for values in self._cursor.fetchall()]

    def fetchone(self):
        values = self._cursor.fetchone()
        return None if values is None else Row(self._names(), values)


class Connection:
    def __init__(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"SQLite copy of the LUX database not found: {path}")
        self._connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self._connection.create_function("IIF", 3, lambda test, yes, no: yes if test else no)

    def cursor(self):
        return Cursor(self._connection)

    def close(self):
        self._connection.close()


def connect(path):
    return Connection(path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python -m pulse_bi.sources.lux.sqlite_copy <database.mdb> <copy.sqlite>")
    print(f"Copying {sys.argv[1]} to {sys.argv[2]}")
    convert(sys.argv[1], sys.argv[2])
