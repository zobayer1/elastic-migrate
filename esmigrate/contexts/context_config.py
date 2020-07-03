# -*- coding: utf-8 -*-
import json
import os
from json.decoder import JSONDecodeError

from validator_collection import checkers

from esmigrate.commons import local_config_file_path, user_config_file_path
from esmigrate.exceptions import (
    InvalidSchemaPatternError,
    ConfigurationFileReadError,
    InvalidElasticHostUrlError,
)


class ContextConfig(object):
    _named_groups = ["version", "sequence", "name", "extension"]
    _default_pattern = "V(?P<version>[\\d]+)_(?P<sequence>[\\d]+)__(?P<name>[\\w]+)\\.(?P<extension>[\\w]+)"
    _default_config_filename = "config.json"

    def __init__(self):
        self.es_host = "http://localhost:9200"
        self.schema_db = "sqlite:///esmigrate.db"
        self.profile = "dev"
        self.headers = {"Connection": "keep-alive"}
        self.schema_dir = None
        self.schema_ext = ".exm"
        self.schema_pattern = (
            rf"^{os.getenv('SCHEMA_PATTERN', ContextConfig._default_pattern)}$"
        )
        if not all(p in self.schema_pattern for p in ContextConfig._named_groups):
            raise InvalidSchemaPatternError(
                f"SCHEMA_PATTERN must have named groups for {ContextConfig._named_groups}"
            )

    def load_for(self, profile: str = "dev"):
        profile = str(profile).strip()
        env_config_path = os.getenv("ESMIGRATE_CONFIG")
        selected_profile = None
        for _path in [env_config_path, local_config_file_path, user_config_file_path]:
            if os.path.isfile(str(_path)):
                try:
                    with open(_path, "r", encoding="utf-8") as _file:
                        json_config_data = json.loads(_file.read())
                        json_profiles = json_config_data.get("profiles")

                        for _profile in json_profiles:
                            if profile in _profile:
                                selected_profile = profile
                                json_profile_data = _profile[profile]
                                self.es_host = json_profile_data.get(
                                    "elastic_host", self.es_host
                                )
                                self.headers = json_profile_data.get(
                                    "elastic_headers", self.headers
                                )
                                self.schema_db = json_profile_data.get(
                                    "schema_db", self.schema_db
                                )
                                self.schema_dir = json_profile_data.get(
                                    "schema_dir", self.schema_dir
                                )
                                self.schema_ext = json_profile_data.get(
                                    "schema_ext", self.schema_ext
                                )

                                if not checkers.is_url(
                                    self.es_host, allow_special_ips=True
                                ):
                                    raise InvalidElasticHostUrlError(
                                        f"Invalid URL: {self.es_host}"
                                    )

                                break

                except (OSError, IOError, JSONDecodeError) as e:
                    raise ConfigurationFileReadError(str(e))

        if selected_profile:
            self.profile = selected_profile

        return self

    def __repr__(self):
        return (
            "Configurations:\n"
            + f"profile: {self.profile}\n"
            + f"elastic_host: {self.es_host}\n"
            + f"elastic_headers: {json.dumps(self.headers)}\n"
            + f"schema_version_db: {self.schema_db}\n"
            + f"schema_file_directory: {self.schema_dir if self.schema_dir else os.getcwd()}\n"
            + f"schema_file_extension: {self.schema_ext}\n"
            + f"schema_filename_pattern: {self.schema_pattern}\n"
        )
