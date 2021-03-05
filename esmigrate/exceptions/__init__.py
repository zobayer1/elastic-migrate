# -*- coding: utf-8 -*-
from requests.exceptions import ConnectionError


class Errors(object):
    # Profile errors
    ERR_PROFILE_NOT_FOUND = -101

    # Database errors
    ERR_DB_CONNECTION_FAILED = -201
    ERR_DB_IN_ERROR_STATE = -202

    # Directory errors
    ERR_INVALID_SCHEMA_DIRECTORY = -301
    ERR_INVALID_SCHEMA_FILE = -302
    ERR_INVALID_SCHEMA_COMMAND = -303

    # Parameter errors
    ERR_INVALID_SCMVER = -401

    # HTTP errors
    ERR_ES_HTTPERROR = -501
    ERR_ES_CONNERROR = -502


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


class InvalidDBConnectionError(RuntimeError):
    """Raised when database connection URL is invalid"""

    pass


class InvalidSchemaFileError(RuntimeError):
    """Raised when schema file cannot be read"""

    pass


class InvalidSchemaPatternError(RuntimeError):
    """Raised when schema pattern is invalid or does not match with filename"""

    pass


class SchemaVersionSqlDbError(RuntimeError):
    """Raised when schema version entity is invalid or conflicting"""

    pass


class UserProfileNotFoundError(RuntimeError):
    """Raised when requested user profile could not be loaded from configuration files"""

    pass


class ElasticsearchConnError(ConnectionError):
    """Raised when connection error occurs from elasticsearch server"""

    pass


__all__ = [
    "ContextObjectNotSetError",
    "ElasticsearchConnError",
    "InvalidCommandBodyError",
    "InvalidCommandPathError",
    "InvalidCommandScriptError",
    "InvalidCommandVerbError",
    "InvalidDBConnectionError",
    "InvalidSchemaFileError",
    "InvalidSchemaPatternError",
    "SchemaVersionSqlDbError",
    "UserProfileNotFoundError",
    "Errors",
]
