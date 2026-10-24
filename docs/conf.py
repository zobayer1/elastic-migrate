from importlib.metadata import version as package_version

project = "ElasticMigrate"
author = "Zobayer Hasan"
copyright = "2020-2026, Zobayer Hasan"
release = package_version("elastic-migrate")
version = release

extensions = ["myst_parser"]
source_suffix = {".md": "markdown"}
exclude_patterns = ["_build"]
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

html_theme = "furo"
html_title = "ElasticMigrate"
html_baseurl = "https://zobayer.net/elastic-migrate/"
html_show_sourcelink = False
html_copy_source = False
