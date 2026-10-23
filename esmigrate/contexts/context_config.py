import json
import os
import re
from json.decoder import JSONDecodeError
from typing import Any, Self, cast
from urllib.parse import urlsplit

from sqlalchemy import make_url
from sqlalchemy.exc import ArgumentError

from esmigrate.commons import DEFAULT_NAMESPACE, DEFAULT_PROFILE, local_config_file_path, user_config_file_path
from esmigrate.commons.log_setup import DEFAULT_LOG_BACKUP_COUNT, DEFAULT_LOG_MAX_BYTES, LOG_ROTATIONS
from esmigrate.exceptions import (
    InvalidConfigurationError,
    InvalidSchemaPatternError,
    UserProfileNotFoundError,
)

ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
MASK = "****"


def interpolate(value: Any, field: str) -> Any:
    if isinstance(value, str):

        def resolve(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise InvalidConfigurationError(f"Environment variable {name} referenced by {field} is not set")
            return os.environ[name]

        return ENV_REFERENCE.sub(resolve, value)
    if isinstance(value, dict):
        return {key: interpolate(item, f"{field}.{key}") for key, item in cast(dict[str, Any], value).items()}
    if isinstance(value, list):
        return [interpolate(item, f"{field}[{index}]") for index, item in enumerate(cast(list[Any], value))]
    return value


def parse_timeout(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise InvalidConfigurationError(f"elastic_timeout must be a positive number of seconds or null, got {value!r}")
    return float(value)


def parse_host(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidConfigurationError(f"elastic_host must be a string, got {value!r}")
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError as err:
        raise InvalidConfigurationError(f"elastic_host is not a valid URL: {value!r}, {err}") from err
    if url.scheme not in ("http", "https"):
        raise InvalidConfigurationError(f"elastic_host must use http or https, got {value!r}")
    if not url.hostname:
        raise InvalidConfigurationError(f"elastic_host has no host name: {value!r}")
    if url.username is not None or url.password is not None:
        raise InvalidConfigurationError(
            "elastic_host must not contain credentials, use elastic_username/elastic_password"
        )
    if port == 0:
        raise InvalidConfigurationError(f"elastic_host has an invalid port: {value!r}")
    return value


def optional_str(data: dict[str, Any], field: str) -> str | None:
    value = data.get(field)
    if value is not None and not isinstance(value, str):
        raise InvalidConfigurationError(f"{field} must be a string, got {value!r}")
    return value or None


def optional_file(data: dict[str, Any], field: str) -> str | None:
    path = optional_str(data, field)
    if path is not None and not os.path.isfile(path):
        raise InvalidConfigurationError(f"{field} file does not exist: {path}")
    return path


def parse_int(data: dict[str, Any], field: str, default: int, minimum: int) -> int:
    value = data.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InvalidConfigurationError(f"{field} must be an integer of at least {minimum}, got {value!r}")
    return value


def mask_db_url(db_url: str) -> str:
    try:
        return make_url(db_url).render_as_string(hide_password=True)
    except ArgumentError:
        return db_url


def parse_headers(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise InvalidConfigurationError("elastic_headers must be an object of string values")
    headers = cast(dict[object, object], value)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise InvalidConfigurationError("elastic_headers must be an object of string values")
    return {str(k): str(v) for k, v in headers.items()}


class ContextConfig:
    _named_groups = ("version", "sequence", "name", "extension")
    _default_pattern = "V(?P<version>[\\d]+)_(?P<sequence>[\\d]+)__(?P<name>[\\w]+)\\.(?P<extension>[\\w]+)"
    _default_config_filename = "config.json"

    def __init__(self) -> None:
        self.es_host = "http://localhost:9200"
        self.es_timeout: float | None = 60.0
        self.es_username: str | None = None
        self.es_password: str | None = None
        self.es_api_key: str | None = None
        self.es_ca_certs: str | None = None
        self.es_verify_certs = True
        self.es_client_cert: str | None = None
        self.es_client_key: str | None = None
        self.es_client_key_password: str | None = None
        self.schema_db = "sqlite:///esmigrate.db"
        self.log_file: str | None = None
        self.log_rotation = "size"
        self.log_max_bytes = DEFAULT_LOG_MAX_BYTES
        self.log_backup_count = DEFAULT_LOG_BACKUP_COUNT
        self.profile: str | None = None
        self.headers = {"Connection": "keep-alive"}
        self.schema_dir: str | None = None
        self.schema_ext = ".exm"
        self.schema_namespace = DEFAULT_NAMESPACE
        self.schema_pattern = rf"^{os.getenv('SCHEMA_PATTERN', ContextConfig._default_pattern)}$"
        if not all(p in self.schema_pattern for p in ContextConfig._named_groups):
            raise InvalidSchemaPatternError(f"SCHEMA_PATTERN must have named groups for {ContextConfig._named_groups}")

    def load_for(self, profile: str = DEFAULT_PROFILE) -> Self:
        profile = str(profile).strip()
        merged: dict[str, Any] = {}
        env_config_path = os.getenv("ESMIGRATE_CONFIG")
        for _path in [user_config_file_path, local_config_file_path, env_config_path]:
            if _path and os.path.isfile(str(_path)):
                try:
                    with open(_path, encoding="utf-8") as _file:
                        json_config_data: Any = json.loads(_file.read())
                except (OSError, JSONDecodeError):
                    continue
                if not isinstance(json_config_data, dict):
                    continue
                profiles: list[dict[str, Any]] = cast(dict[str, Any], json_config_data).get("profiles") or []
                for _profile in profiles:
                    if profile in _profile:
                        self.profile = profile
                        merged.update(_profile[profile])
                        break

        if self.profile is None:
            raise UserProfileNotFoundError(f"Requested profile '{profile}' could not be loaded")
        self._apply({field: interpolate(value, field) for field, value in merged.items()})
        if not self.schema_dir:
            raise InvalidConfigurationError(f"schema_dir is required in profile '{profile}'")

        return self

    def _apply(self, data: dict[str, Any]) -> None:
        if "elastic_host" in data:
            self.es_host = parse_host(data["elastic_host"])
        if "elastic_headers" in data:
            self.headers = parse_headers(data["elastic_headers"])
        if "elastic_timeout" in data:
            self.es_timeout = parse_timeout(data["elastic_timeout"])
        self.schema_db = optional_str(data, "schema_db") or self.schema_db
        self.schema_dir = optional_str(data, "schema_dir")
        self.schema_ext = optional_str(data, "schema_ext") or self.schema_ext
        self.schema_namespace = optional_str(data, "schema_namespace") or self.schema_namespace
        self._apply_security(data)
        self._apply_logging(data)

    def _apply_logging(self, data: dict[str, Any]) -> None:
        self.log_file = optional_str(data, "log_file")
        rotation = data.get("log_rotation", "size")
        if rotation not in LOG_ROTATIONS:
            raise InvalidConfigurationError(f"log_rotation must be one of {', '.join(LOG_ROTATIONS)}, got {rotation!r}")
        self.log_rotation = rotation
        self.log_max_bytes = parse_int(data, "log_max_bytes", DEFAULT_LOG_MAX_BYTES, 1)
        self.log_backup_count = parse_int(data, "log_backup_count", DEFAULT_LOG_BACKUP_COUNT, 0)

    def _apply_security(self, data: dict[str, Any]) -> None:
        self.es_username = optional_str(data, "elastic_username")
        self.es_password = optional_str(data, "elastic_password")
        self.es_api_key = optional_str(data, "elastic_api_key")
        self.es_ca_certs = optional_file(data, "elastic_ca_certs")
        self.es_client_cert = optional_file(data, "elastic_client_cert")
        self.es_client_key = optional_file(data, "elastic_client_key")
        self.es_client_key_password = optional_str(data, "elastic_client_key_password")
        verify = data.get("elastic_verify_certs", True)
        if not isinstance(verify, bool):
            raise InvalidConfigurationError(f"elastic_verify_certs must be true or false, got {verify!r}")
        self.es_verify_certs = verify

        if (self.es_username is None) != (self.es_password is None):
            raise InvalidConfigurationError("elastic_username and elastic_password must be set together")
        if self.es_username is not None and self.es_api_key is not None:
            raise InvalidConfigurationError("Use either elastic_username/elastic_password or elastic_api_key, not both")
        if (self.es_client_key or self.es_client_key_password) and not self.es_client_cert:
            raise InvalidConfigurationError(
                "elastic_client_key and elastic_client_key_password need elastic_client_cert"
            )
        has_header_auth = any(key.lower() == "authorization" for key in self.headers)
        if has_header_auth and (self.es_username is not None or self.es_api_key is not None):
            raise InvalidConfigurationError(
                "An Authorization header in elastic_headers conflicts with elastic auth fields"
            )
        if self.es_ca_certs and not self.es_verify_certs:
            raise InvalidConfigurationError("elastic_ca_certs has no effect when elastic_verify_certs is false")

    @property
    def schema_path(self) -> str:
        if not self.schema_dir:
            raise InvalidConfigurationError("schema_dir is not configured")
        return self.schema_dir

    def masked_headers(self) -> dict[str, str]:
        return {key: MASK if key.lower() == "authorization" else value for key, value in self.headers.items()}

    def __repr__(self) -> str:
        def secret(value: str | None) -> str | None:
            return MASK if value else None

        return (
            "Configurations:\n"
            + f"profile: {self.profile}\n"
            + f"elastic_host: {self.es_host}\n"
            + f"elastic_headers: {json.dumps(self.masked_headers())}\n"
            + f"elastic_timeout: {self.es_timeout}\n"
            + f"elastic_username: {self.es_username}\n"
            + f"elastic_password: {secret(self.es_password)}\n"
            + f"elastic_api_key: {secret(self.es_api_key)}\n"
            + f"elastic_ca_certs: {self.es_ca_certs}\n"
            + f"elastic_verify_certs: {self.es_verify_certs}\n"
            + f"elastic_client_cert: {self.es_client_cert}\n"
            + f"elastic_client_key: {self.es_client_key}\n"
            + f"elastic_client_key_password: {secret(self.es_client_key_password)}\n"
            + f"schema_version_db: {mask_db_url(self.schema_db)}\n"
            + f"schema_file_directory: {self.schema_dir}\n"
            + f"schema_file_extension: {self.schema_ext}\n"
            + f"schema_namespace: {self.schema_namespace}\n"
            + f"schema_filename_pattern: {self.schema_pattern}\n"
            + f"log_file: {self.log_file}\n"
            + f"log_rotation: {self.log_rotation}\n"
            + f"log_max_bytes: {self.log_max_bytes}\n"
            + f"log_backup_count: {self.log_backup_count}\n"
        )
