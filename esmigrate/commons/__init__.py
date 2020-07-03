# -*- coding: utf-8 -*-
import os

import appdirs
from setuptools_scm import get_version

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
version = get_version(root="../../", relative_to=__file__)
version_short = version.split("+")[0]

title = f"""
  ███████╗███████╗    ███╗   ███╗██╗ ██████╗ ██████╗  █████╗ ████████╗███████╗
  ██╔════╝██╔════╝    ████╗ ████║██║██╔════╝ ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝
  █████╗  ███████╗    ██╔████╔██║██║██║  ███╗██████╔╝███████║   ██║   █████╗
  ██╔══╝  ╚════██║    ██║╚██╔╝██║██║██║   ██║██╔══██╗██╔══██║   ██║   ██╔══╝
  ███████╗███████║    ██║ ╚═╝ ██║██║╚██████╔╝██║  ██║██║  ██║   ██║   ███████╗
  ╚══════╝╚══════╝    ╚═╝     ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚══════╝  {version_short}
  Elasticsearch migrations made easy!
"""

local_config_file_path = os.path.join(os.getcwd(), "config.json")
user_config_file_path = os.path.join(
    appdirs.user_config_dir(appname=appname), "config.json"
)

__all__ = [
    "http_verbs",
    "JSON_HEADER",
    "NDJSON_HEADER",
    "appname",
    "version",
    "version_short",
    "title",
    "local_config_file_path",
    "user_config_file_path",
    "Command",
    "is_valid_json",
    "is_valid_ndjson",
    "parse_file_path",
]
