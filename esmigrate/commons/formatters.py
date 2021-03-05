# -*- coding: utf-8 -*-
import json

from requests import Response

from .command import Command


def query_results_string(command: Command, response: Response) -> str:
    return json.dumps(
        {
            "query": f"{command.verb} {command.path} {command.body}",
            "status": response.status_code,
            "result": response.text,
        }
    )
