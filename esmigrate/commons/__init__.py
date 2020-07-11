# -*- coding: utf-8 -*-
import os
import sys

if sys.version_info < (3, 8):  # pragma: no cover
    from importlib_metadata import version as get_version
else:  # pragma: no cover
    from importlib.metadata import version as get_version

import appdirs

from esmigrate.commons.script_data import ScriptData
from esmigrate.commons.command import Command
from esmigrate.commons.helpers import (
    is_valid_json,
    is_valid_ndjson,
    parse_file_path,
)

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
user_config_file_path = os.path.join(appdirs.user_config_dir(appname=appname), "config.json")

__all__ = [
    "http_verbs",
    "JSON_HEADER",
    "NDJSON_HEADER",
    "appname",
    "version",
    "title",
    "local_config_file_path",
    "user_config_file_path",
    "Command",
    "ScriptData",
    "is_valid_json",
    "is_valid_ndjson",
    "parse_file_path",
]
