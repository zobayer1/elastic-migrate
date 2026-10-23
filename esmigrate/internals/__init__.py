from esmigrate.internals.db_manager import DBManager
from esmigrate.internals.glob_loader import GlobLoader
from esmigrate.internals.http_handler import HTTPHandler
from esmigrate.internals.script_parser import ScriptParser

db_managers: dict[str, DBManager] = {}


def get_db_manager(db_url: str, echo: bool = False) -> DBManager:
    global db_managers
    if db_url not in db_managers:
        db_managers[db_url] = DBManager(db_url, echo)
    return db_managers[db_url]


__all__ = [
    "GlobLoader",
    "HTTPHandler",
    "ScriptParser",
    "get_db_manager",
]
