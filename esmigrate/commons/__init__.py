# -*- coding: utf-8 -*-
from setuptools_scm import get_version

from esmigrate.commons.command import Command
from esmigrate.commons.header import Header
from esmigrate.commons.helpers import is_valid_json, is_valid_ndjson, is_valid_path

JSON_HEADER = Header({'Content-Type': 'application/json'})
NDJSON_HEADER = Header({'Content-Type': 'application/x-ndjson'})

version = get_version(root='../../', relative_to=__file__)
version_short = version.split('+')[0]
title = f"""
  ███████╗███████╗    ███╗   ███╗██╗ ██████╗ ██████╗  █████╗ ████████╗███████╗
  ██╔════╝██╔════╝    ████╗ ████║██║██╔════╝ ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝
  █████╗  ███████╗    ██╔████╔██║██║██║  ███╗██████╔╝███████║   ██║   █████╗
  ██╔══╝  ╚════██║    ██║╚██╔╝██║██║██║   ██║██╔══██╗██╔══██║   ██║   ██╔══╝
  ███████╗███████║    ██║ ╚═╝ ██║██║╚██████╔╝██║  ██║██║  ██║   ██║   ███████╗
  ╚══════╝╚══════╝    ╚═╝     ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚══════╝  {version_short}
  Elasticsearch migrations made easy!
"""

__all__ = ['Command', 'Header', 'JSON_HEADER', 'NDJSON_HEADER',
           'is_valid_json', 'is_valid_ndjson', 'is_valid_path',
           'version', 'version_short', 'title', ]
