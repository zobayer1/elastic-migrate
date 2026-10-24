from enum import IntEnum

from httpx import Response


class Errors(IntEnum):
    # Profile errors
    ERR_PROFILE_NOT_FOUND = 10
    ERR_INVALID_CONFIGURATION = 11

    # Database errors
    ERR_DB_CONNECTION_FAILED = 20
    ERR_DB_IN_ERROR_STATE = 21
    ERR_DB_LEGACY_TABLE = 22
    ERR_DB_LOCKED = 23

    # Directory errors
    ERR_INVALID_SCHEMA_DIRECTORY = 30
    ERR_INVALID_SCHEMA_FILE = 31
    ERR_INVALID_SCHEMA_COMMAND = 32

    # Parameter errors
    ERR_INVALID_SCMVER = 40

    # HTTP errors
    ERR_ES_HTTPERROR = 50
    ERR_ES_CONNERROR = 51


class ContextObjectNotSetError(RuntimeError):
    """Raised when a context dependency is not met"""

    pass


class InvalidCommandBodyError(RuntimeError):
    """Raised when command body is not a valid JSON or NDJSON object"""

    pass


class InvalidCommandPathError(RuntimeError):
    """Raised when command path is not a valid URL path"""

    pass


class InvalidCommandScriptError(RuntimeError):
    """Raised when command script does not have or start with a command"""

    pass


class InvalidCommandVerbError(RuntimeError):
    """Raised when command verb is an unsupported HTTP verb"""

    pass


class InvalidConfigurationError(RuntimeError):
    """Raised when a profile field has an invalid value"""

    pass


class InvalidDBConnectionError(RuntimeError):
    """Raised when database connection URL is invalid"""

    pass


class InvalidSchemaFileError(RuntimeError):
    """Raised when schema file cannot be read"""

    pass


class InvalidSchemaPatternError(RuntimeError):
    """Raised when schema pattern is invalid or does not match with filename"""

    pass


class LegacySchemaTableError(RuntimeError):
    """Raised when the schema version table uses the v1 layout and must be upgraded with `esmigrate init`"""

    pass


class MigrationLockedError(RuntimeError):
    """Raised when another esmigrate run holds the migration lock for the namespace"""

    pass


class SchemaVersionSqlDbError(RuntimeError):
    """Raised when schema version entity is invalid or conflicting"""

    pass


class UserProfileNotFoundError(RuntimeError):
    """Raised when requested user profile could not be loaded from configuration files"""

    pass


class ElasticsearchConnError(RuntimeError):
    """Raised when elasticsearch cannot be reached or does not respond in time"""

    pass


class ElasticsearchHTTPError(RuntimeError):
    """Raised when elasticsearch responds with a non-success HTTP status"""

    def __init__(self, response: Response) -> None:
        request = response.request
        super().__init__(f"{response.status_code} {response.reason_phrase} for {request.method} {request.url.path}")
        self.response = response


__all__ = [
    "ContextObjectNotSetError",
    "ElasticsearchConnError",
    "ElasticsearchHTTPError",
    "Errors",
    "InvalidCommandBodyError",
    "InvalidCommandPathError",
    "InvalidCommandScriptError",
    "InvalidCommandVerbError",
    "InvalidConfigurationError",
    "InvalidDBConnectionError",
    "InvalidSchemaFileError",
    "InvalidSchemaPatternError",
    "LegacySchemaTableError",
    "MigrationLockedError",
    "SchemaVersionSqlDbError",
    "UserProfileNotFoundError",
]
