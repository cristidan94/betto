from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any
import sys

from core.vendor import add_vendor_path, load_vendor_package


class MissingPostgresDriverError(RuntimeError):
    """Raised when psycopg is not installed in the active Python environment."""


class PostgresExecutor(AbstractContextManager["PostgresExecutor"]):
    """Small psycopg-backed executor implementing the repository protocol."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._conn: Any | None = None

    def __enter__(self) -> "PostgresExecutor":
        add_vendor_path()
        try:
            import psycopg
        except ImportError as exc:
            try:
                psycopg = load_vendor_package("psycopg")
            except ImportError:
                raise MissingPostgresDriverError(
                    f"psycopg is not installed for Python {sys.version_info.major}.{sys.version_info.minor}. "
                    "Install project dependencies before using Postgres commands."
                ) from exc
        if not hasattr(psycopg, "connect"):
            psycopg = load_vendor_package("psycopg")
        if not hasattr(psycopg, "connect"):
            module_path = getattr(psycopg, "__file__", "unknown")
            raise MissingPostgresDriverError(
                f"Imported psycopg from {module_path}, but it has no connect attribute. "
                f"Install psycopg for Python {sys.version_info.major}.{sys.version_info.minor}."
            )
        self._conn = psycopg.connect(self.database_url)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._conn is None:
            return
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        self._conn = None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        if self._conn is None:
            raise RuntimeError("PostgresExecutor must be used as a context manager")
        with self._conn.cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.description is None:
                return None
            return cursor.fetchall()

    def ping(self) -> bool:
        rows = self.execute("SELECT 1", ())
        return rows == [(1,)]
