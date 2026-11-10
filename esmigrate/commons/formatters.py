import json

from httpx import Response

from esmigrate.commons.command import Command


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
