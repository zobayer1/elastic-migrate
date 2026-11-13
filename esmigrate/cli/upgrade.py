import logging

import click

from esmigrate.cli.common import DB_ERRORS, connect_db, fail, help_option, hold_lock, pass_config, run
from esmigrate.cli.execution import apply_schema, parse_scripts
from esmigrate.commons import Direction, MigVersion
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    Errors,
    InvalidCommandScriptError,
    InvalidConfigurationError,
    InvalidSchemaFileError,
    InvalidSchemaPatternError,
    SchemaVersionSqlDbError,
    error_list,
)
from esmigrate.internals import DBManager, GlobLoader, HTTPHandler

log = logging.getLogger(__name__)


@click.command()
@help_option
@click.option(
    "-s", "--schema-version", default="latest", help="Apply migrations up to this version, e.g. '1.2' or 'latest'"
)
@pass_config
def upgrade(cfg: ContextConfig, schema_version: str = "latest") -> None:
    """Apply pending migrations up to the latest or given version"""
    run(run_upgrade(cfg, schema_version))


async def run_upgrade(cfg: ContextConfig, schema_version: str) -> int:
    log.debug(f"Upgrade: target={schema_version}")
    try:
        requested = None if schema_version == "latest" else MigVersion.parse(schema_version)
    except ValueError as err:
        return fail(err, Errors.ERR_INVALID_SCMVER)
    try:
        async with connect_db(cfg) as db, hold_lock(cfg, db):
            return await upgrade_schema(cfg, db, requested)
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    except InvalidConfigurationError as err:
        return fail(err, Errors.ERR_INVALID_CONFIGURATION)


async def upgrade_schema(cfg: ContextConfig, db: DBManager, requested: MigVersion | None) -> int:
    latest_db_entry = await db.find_latest_schema()
    if latest_db_entry and not latest_db_entry.success:
        state = "failed" if latest_db_entry.success is False else "was interrupted"
        err = SchemaVersionSqlDbError(
            f"Version {latest_db_entry.version} {state}, see `esmigrate status` and resolve it with `esmigrate force`"
        )
        return fail(err, Errors.ERR_DB_IN_ERROR_STATE)
    latest_db_version = latest_db_entry.version if latest_db_entry else MigVersion(0, 0)
    try:
        schema_entries = GlobLoader(cfg).load_migrations(cfg.schema_path)
    except NotADirectoryError as err:
        return fail(err, Errors.ERR_INVALID_SCHEMA_DIRECTORY)
    except (InvalidSchemaPatternError, InvalidSchemaFileError) as err:
        return fail(err, Errors.ERR_INVALID_SCHEMA_FILE)
    if not schema_entries:
        log.info("No migration scripts found, nothing to do")
        return 0
    applied = await db.find_applied_versions()
    skipped = [entry for entry in schema_entries if entry.version < latest_db_version and entry.version not in applied]
    if skipped:
        title = f"Migrations below the latest applied version {latest_db_version} are skipped:"
        files = [
            f"{entry.version}: {', '.join(script.path for script in (entry.up, entry.down) if script)}"
            for entry in skipped
        ]
        log.warning(error_list(title, files))
    target = schema_entries[-1].version if requested is None else requested
    pending = [entry for entry in schema_entries if latest_db_version < entry.version <= target]
    if not pending:
        if requested is None:
            log.info(f"Schema database is up to date at version {latest_db_version}, nothing to do")
        else:
            log.info(
                f"No migrations to apply up to version {requested} (database at {latest_db_version}), nothing to do"
            )
        return 0
    try:
        parsed = parse_scripts(Direction.UP, pending)
    except InvalidCommandScriptError as err:
        return fail(err, Errors.ERR_INVALID_SCHEMA_COMMAND)
    async with HTTPHandler(cfg) as http_handler:
        for entry, commands in parsed:
            code = await apply_schema(db, http_handler, Direction.UP, entry, commands)
            if code:
                return code
    log.info(f"Schema database upgraded to {pending[-1].version}")
    return 0
