from contextlib import contextmanager
import re
import sqlite3
from typing import Any, Generator, Iterable, List, Sequence
import threading
from qcodes.parameters import Parameter
from typing import List

class DataSaver:
    def __init__(self, path: str) -> None:
        self.path = path
        self.local = threading.local()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection."""
        if not hasattr(self.local, 'connection'):
            conn = sqlite3.connect(self.path)
            self.local.connection = conn
        return self.local.connection

    @contextmanager
    def ds_connection(self) -> Generator[Any, Any, Any]:
        """Provides a connection to use with the "with" statement."""
        conn = self.get_connection()
        try:
            yield conn 
        finally:
            pass

    @contextmanager
    def ds_cursor(self) -> Generator[Any, Any, Any]:
        """Provides a cursor to use with the "with" statement."""
        cursor = self.get_connection().cursor()
        try:
            yield cursor 
        finally:
            pass

    def get_tables(self) -> List[str]:
        """Grab all of the tables in the opened db.

        Useful for auto-creating a new table to work on.
        """

        query = f"""
        SELECT 
            name
        FROM 
            sqlite_schema
        WHERE 
            type ='table' AND 
            name NOT LIKE 'sqlite_%';
        """

        with self.ds_connection() as conn:
            res = conn.execute(query)
            tables = [row[0] for row in res.fetchall()]

        return tables

    def get_columns(self, table_name):
        """Returns column names from a table"""

        query = f"""SELECT name FROM PRAGMA_TABLE_INFO("{table_name}");"""

        with self.ds_connection() as conn:
            res = conn.execute(query)
            names = [col[0] for col in res.fetchall()]

        return names

    def register_table(self, name) -> str:
        """Create a table/experiment in the database. If table exists, registers with name_# for duplicates."""

        tables = self.get_tables()
        pattern = re.compile(rf"^{re.escape(name)}(?:_(\d+))?$")
        indices = []

        for table_name in tables:
            match = pattern.match(table_name)
            if match:
                # If there is an index, parse it, else treat it as index 0
                index = int(match.group(1)) if match.group(1) else 0
                indices.append(index)

        next_index = max(indices) + 1 if indices else 0

        if next_index == 0:
            new_table_name = name
        else:
            new_table_name = f"{name}_{next_index}"

        create_table = f"""
        CREATE TABLE IF NOT EXISTS "{new_table_name}" (
            `id` INTEGER PRIMARY KEY,
            `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """

        with self.ds_connection() as conn:
            conn.execute(create_table)
            conn.commit()

        return new_table_name

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in the specified table."""

        try:
            with self.ds_connection() as conn:
                cursor = conn.execute(f'PRAGMA table_info("{table_name}");')
                columns = [row[1] for row in cursor.fetchall()]  # row[1] is the column name
            return column_name in columns
        except sqlite3.Error:
            return False

    def _ensure_column_exists(self, table_name: str, column_name: str, column_type: str = "NUMERIC") -> None:
        """Ensure a column exists in the table, create it if it doesn't."""

        if not self._column_exists(table_name, column_name):
            try:
                query = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type};'
                with self.ds_connection() as conn:
                    conn.execute(query)
                    conn.commit()
                print(f"Added column '{column_name}' to table '{table_name}'")
            except sqlite3.Error as e:
                print(f"Error adding column '{column_name}': {e}")
                raise

    def _ensure_table_exists(self, table_name: str) -> None:
        """Ensure the table exists with proper param/value structure."""

        query = f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            param TEXT NOT NULL,
            value NUMERIC NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        with self.ds_connection() as conn:
            conn.execute(query)
            conn.commit()

    def add_result(self, table_name: str, param_value_pair: tuple[Parameter, float] | list[tuple[Parameter, float]]) -> None:
        """Add a set of values to a table. Automatically creates columns for the parameters if they do not exist."""

        if not param_value_pair:
            return

        self._ensure_table_exists(table_name)

        # Normalize input to a list of tuples
        if isinstance(param_value_pair, tuple):
            param_value_pair = [param_value_pair]  # Wrap single tuple in a list

        # Ensure all columns exist
        for parameter, _ in param_value_pair:
            self._ensure_column_exists(table_name, f"{parameter.full_name}", "NUMERIC")

        # Prepare and execute insert
        column_names = [f'"{param.full_name}"' for param, _ in param_value_pair]
        values = [value for _, value in param_value_pair]
        
        columns_str = ", ".join(column_names)
        placeholders = ", ".join(["?" for _ in values])
        
        query = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders});'

        with self.ds_cursor() as cursor:
            cursor.execute(query, values)

        with self.ds_connection() as conn:
            conn.commit()

    def get_column_values(self, table_name: str, column_name: str) -> List[Any] | None:
        """Grab all of the data from a column. Should only really be used to query a few rows, use streaming otherwise."""

        if not self._column_exists(table_name, column_name):
            return None

        query = f'SELECT "{column_name}" FROM "{table_name}"'
        with self.ds_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            rows = [row[0] for row in rows]

        return rows

    def get_table_values(self, table_name: str) -> dict | None:
        """Returns the entire table as a dict[column_name: List[values]]."""
        query = f'SELECT * FROM "{table_name}"'

        with self.ds_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        columns = rows[0].keys() if rows else []
        data = {col: [] for col in columns}

        for row in rows:
            for col in columns:
                data[col].append(row[col])

        return data

    def get_tail_values(self, table_name: str, tail: int) -> dict[str, Sequence[Any]]:
        """Returns dict[column: list_of_values] containing the last number of entries determined by tail."""

        query = f'SELECT * FROM "{table_name}" ORDER BY ID DESC LIMIT ?'

        with self.ds_cursor() as cursor:
            cursor.execute(query, (tail,))
            rows = cursor.fetchall()

            columns = [desc[0] for desc in cursor.description]

        # Transpose rows to column-wise data
        data = {col: [] for col in columns}
        for row in rows:
            for col, val in zip(columns, row):
                data[col].append(val)

        return dict(data)
