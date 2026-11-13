import json
import logging
import time

from httpx import Response

from esmigrate.cli.common import fail
from esmigrate.commons import Command, Direction, Migration
from esmigrate.exceptions import (
    ElasticsearchConnError,
    ElasticsearchHTTPError,
    Errors,
    InvalidCommandBodyError,
    InvalidCommandPathError,
    InvalidCommandScriptError,
    InvalidCommandVerbError,
    error_list,
)
from esmigrate.internals import DBManager, HTTPHandler, ScriptParser

log = logging.getLogger(__name__)

SCRIPT_ERRORS = (
    InvalidCommandScriptError,
    InvalidCommandVerbError,
    InvalidCommandPathError,
    InvalidCommandBodyError,
)


def query_results_string(command: Command, response: Response) -> str:
    return json.dumps(
        {
            "query": f"{command.verb} {command.path} {command.body}",
            "status": response.status_code,
            "result": response.text,
        }
    )


def query_error_string(command: Command, err: Exception) -> str:
    return json.dumps(
        {
            "query": f"{command.verb} {command.path} {command.body}",
            "status": None,
            "result": f"{type(err).__name__}: {err}",
        }
    )


def parse_scripts(direction: Direction, migrations: list[Migration]) -> list[tuple[Migration, list[Command]]]:
    parser = ScriptParser()
    parsed: list[tuple[Migration, list[Command]]] = []
    errors: list[str] = []
    for migration in migrations:
        script = migration.script_for(direction)
        if script is None:
            parsed.append((migration, []))
            continue
        try:
            parsed.append((migration, list(parser.get_commands(script.content))))
        except SCRIPT_ERRORS as err:
            errors.append(f"{script.path}: {err}")
    if errors:
        raise InvalidCommandScriptError(error_list("Invalid migration scripts:", errors))
    return parsed


async def apply_schema(
    db: DBManager, http_handler: HTTPHandler, direction: Direction, entry: Migration, commands: list[Command]
) -> int:
    log.info(f"Processing schema {entry.description}")
    script = entry.script_for(direction)
    if script:
        log.debug(f"Schema {entry.version} {direction}: script={script.path} checksum={script.checksum.hex()}")
    else:
        log.info(f"Schema {entry.version} has no {direction} script, recording it without requests")
    run = await db.start_run(direction, entry)
    tic = time.perf_counter()
    error_code = 0
    undo = False
    query_results: list[str] = []
    for command in commands:
        try:
            response = await http_handler.make_requests(command)
        except ElasticsearchConnError as err:
            undo = err.never_reached and not query_results
            query_results.append(query_error_string(command, err))
            error_code = fail(err, Errors.ERR_ES_CONNERROR)
            break
        except ElasticsearchHTTPError as err:
            query_results.append(query_results_string(command, err.response))
            error_code = fail(err, Errors.ERR_ES_HTTPERROR)
            break
        query_results.append(query_results_string(command, response))
    duration = int((time.perf_counter() - tic) * 1000)
    results = ";".join(query_results)
    if undo:
        await db.undo_run(run, duration, results)
    else:
        await db.finish_run(run, error_code == 0, duration, results)
    log.debug(f"Schema {entry.version} {direction} {'succeeded' if error_code == 0 else 'failed'} in {duration} ms")
    if error_code == 0:
        log.info(f"Schema {entry.description} executed successfully")
    return error_code
