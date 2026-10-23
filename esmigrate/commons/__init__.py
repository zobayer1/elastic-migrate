import os
from importlib.metadata import version as get_version

from platformdirs import user_config_dir

from esmigrate.commons.command import Command
from esmigrate.commons.formatters import query_results_string
from esmigrate.commons.helpers import (
    is_valid_json,
    is_valid_ndjson,
    parse_file_path,
)
from esmigrate.commons.script_data import ScriptData

http_verbs = ["GET", "PUT", "POST", "DELETE"]
JSON_HEADER = {"Content-Type": "application/json"}
NDJSON_HEADER = {"Content-Type": "application/x-ndjson"}

appname = "elastic-migrate"
version = get_version(appname)

title = f"""
  ███████╗███████╗    ███╗   ███╗██╗ ██████╗ ██████╗  █████╗ ████████╗███████╗
  ██╔════╝██╔════╝    ████╗ ████║██║██╔════╝ ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝
  █████╗  ███████╗    ██╔████╔██║██║██║  ███╗██████╔╝███████║   ██║   █████╗
  ██╔══╝  ╚════██║    ██║╚██╔╝██║██║██║   ██║██╔══██╗██╔══██║   ██║   ██╔══╝
  ███████╗███████║    ██║ ╚═╝ ██║██║╚██████╔╝██║  ██║██║  ██║   ██║   ███████╗
  ╚══════╝╚══════╝    ╚═╝     ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚══════╝  {version}
  Elasticsearch migrations made easy!
"""

local_config_file_path = os.path.join(os.getcwd(), "config.json")
user_config_file_path = os.path.join(user_config_dir(appname=appname), "config.json")

__all__ = [
    "JSON_HEADER",
    "NDJSON_HEADER",
    "Command",
    "ScriptData",
    "appname",
    "http_verbs",
    "is_valid_json",
    "is_valid_ndjson",
    "local_config_file_path",
    "parse_file_path",
    "query_results_string",
    "title",
    "user_config_file_path",
    "version",
]
