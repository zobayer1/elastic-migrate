from importlib.metadata import version as get_version

appname = "elastic-migrate"
DEFAULT_NAMESPACE = "default"
DEFAULT_PROFILE = "default"
version = get_version(appname)
