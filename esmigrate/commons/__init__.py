import os
from importlib.metadata import version as get_version

from platformdirs import user_config_dir

from esmigrate.commons.command import Command
from esmigrate.commons.formatters import old_timestamp_to_utc, query_error_string, query_results_string
from esmigrate.commons.helpers import (
    is_valid_json,
    is_valid_ndjson,
    make_sha1,
)
from esmigrate.commons.mig_version import MAX_VERSION_PART, MigVersion, parse_version
from esmigrate.commons.migration import Migration
from esmigrate.commons.script_data import Direction, Operation, ScriptData

http_verbs = ["GET", "PUT", "POST", "DELETE"]
JSON_HEADER = {"Content-Type": "application/json"}
NDJSON_HEADER = {"Content-Type": "application/x-ndjson"}

appname = "elastic-migrate"
DEFAULT_NAMESPACE = "default"
DEFAULT_PROFILE = "default"
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
    "DEFAULT_NAMESPACE",
    "DEFAULT_PROFILE",
    "JSON_HEADER",
    "MAX_VERSION_PART",
    "NDJSON_HEADER",
    "Command",
    "Direction",
    "MigVersion",
    "Migration",
    "Operation",
    "ScriptData",
    "appname",
    "http_verbs",
    "is_valid_json",
    "is_valid_ndjson",
    "local_config_file_path",
    "make_sha1",
    "old_timestamp_to_utc",
    "parse_version",
    "query_error_string",
    "query_results_string",
    "title",
    "user_config_file_path",
    "version",
]
