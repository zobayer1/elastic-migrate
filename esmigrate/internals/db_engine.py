from sqlalchemy import URL, Connection, MetaData, inspect, make_url
from sqlalchemy.exc import ArgumentError, InvalidRequestError, NoSuchModuleError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.schema import CreateIndex, CreateTable

from esmigrate.exceptions import InvalidDBConnectionError, InvalidSchemaTableError, error_list
from esmigrate.models import HISTORY_TABLE, STATE_TABLE

ASYNC_DRIVERS = {
    "sqlite": "sqlite+aiosqlite",
    "postgres": "postgresql+asyncpg",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+asyncmy",
    "mariadb": "mysql+asyncmy",
}

DRIVER_EXTRAS = {
    "asyncpg": "postgres",
    "asyncmy": "mysql",
}


def to_async_url(db_url: str) -> URL:
    try:
        url = make_url(db_url)
    except ArgumentError as err:
        raise InvalidDBConnectionError(f"schema_db is not a valid database URL: {err}") from err
    if "+" in url.drivername:
        return url
    if url.drivername not in ASYNC_DRIVERS:
        raise InvalidDBConnectionError(f"Unsupported database {url.drivername!r}, use sqlite, postgresql or mysql")
    return url.set(drivername=ASYNC_DRIVERS[url.drivername])


def create_engine(db_url: str, echo: bool = False) -> AsyncEngine:
    url = to_async_url(db_url)
    try:
        return create_async_engine(url, echo=echo, hide_parameters=True)
    except ModuleNotFoundError as err:
        extra = DRIVER_EXTRAS.get(err.name or "")
        hint = f", install elastic-migrate[{extra}]" if extra else ""
        raise InvalidDBConnectionError(f"Database driver {err.name!r} is not installed{hint}") from err
    except (InvalidRequestError, NoSuchModuleError) as err:
        raise InvalidDBConnectionError(f"Unsupported database driver {url.drivername!r}: {err}") from err


def create_tables_sql(db_url: str, schema: str | None = None) -> str:
    dialect = create_engine(db_url).dialect
    statements: list[str] = []
    for source in (STATE_TABLE, HISTORY_TABLE):
        table = source.to_metadata(MetaData(), schema=schema) if schema else source
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        for index in sorted(table.indexes, key=lambda item: str(item.name)):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)))
    return ";\n\n".join(statements) + ";"


def check_schema_exists(conn: Connection, schema: str | None) -> None:
    if schema is not None and schema not in inspect(conn).get_schema_names():
        raise InvalidDBConnectionError(f"Database schema {schema!r} does not exist")


def verify_schema_columns(conn: Connection, schema: str | None = None) -> None:
    inspector = inspect(conn)
    errors: list[str] = []
    for expected in (STATE_TABLE, HISTORY_TABLE):
        found = {col["name"].lower() for col in inspector.get_columns(expected.name, schema=schema)}
        missing = {col.name for col in expected.columns} - found
        if missing:
            errors.append(f"{expected.name}: {', '.join(sorted(missing))}")
    if errors:
        raise InvalidSchemaTableError(error_list("Schema tables are missing columns:", errors))
