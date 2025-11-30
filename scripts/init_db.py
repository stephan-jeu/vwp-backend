from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncConnection

# Ensure the backend root (parent of this file's directory) is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.logging import logger  # noqa: E402
from db.session import engine  # noqa: E402
from scripts.create_admin_user import _ensure_admin  # noqa: E402


SQL_DIR = BACKEND_ROOT / "db" / "sql"
SQL_LAST = "update_maternity_pvws.sql"


async def _run_sql_seeds() -> None:
    async with engine.begin() as conn:
        await _run_sql_files_in_order(conn)


async def _run_sql_files_in_order(conn: AsyncConnection) -> None:
    if not SQL_DIR.is_dir():
        logger.error("SQL directory does not exist: %s", SQL_DIR)
        return

    sql_files = sorted(SQL_DIR.glob("*.sql"))

    last_path: Path | None = None
    ordered: list[Path] = []
    for path in sql_files:
        if path.name == SQL_LAST:
            last_path = path
        else:
            ordered.append(path)
    if last_path is not None:
        ordered.append(last_path)

    for path in ordered:
        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            continue
        logger.info("Running SQL script: %s", path.name)
        statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
        for statement in statements:
            await conn.exec_driver_sql(statement)


async def _init_db_async() -> None:
    await _run_sql_seeds()
    await _ensure_admin("stephan@nextaimove.com")


def main() -> NoReturn:
    """Initialize database data and create the default admin user."""
    asyncio.run(_init_db_async())
    raise SystemExit(0)


if __name__ == "__main__":
    main()
