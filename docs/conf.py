import sys
from importlib.metadata import version as package_version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_ext"))

project = "ElasticMigrate"
author = "Zobayer Hasan"
copyright = "2020-2026, Zobayer Hasan"
release = package_version("elastic-migrate")
version = release

extensions = ["myst_parser", "latest_release"]
source_suffix = {".md": "markdown"}
exclude_patterns = ["_build", "_generated"]
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

html_theme = "furo"
html_title = "ElasticMigrate"
html_baseurl = "https://zobayer.net/elastic-migrate/"
html_static_path = ["_static"]
html_show_sourcelink = False
html_copy_source = False
