# -*- coding: utf-8 -*-
import json
import os

from esmigrate.exceptions import InvalidSchemaPatternError


class ContextConfig(object):
    _named_groups = ["version", "sequence", "name", "extension"]
    _default_pattern = "V(?P<version>[\\d]+)_(?P<sequence>[\\d]+)__(?P<name>[\\w]+)\\.(?P<extension>[\\w]+)"

    def __init__(self):
        self.es_host = "http://localhost:9200"
        self.schema_db = "sqlite:///esmigrate.db"
        self.profile = "dev"
        self.headers = {}
        self.schema_dir = None
        self.schema_ext = ".exm"
        self.schema_pattern = (
            rf"^{os.getenv('SCHEMA_PATTERN', ContextConfig._default_pattern)}$"
        )
        if not all(p in self.schema_pattern for p in ContextConfig._named_groups):
            raise InvalidSchemaPatternError(
                f"SCHEMA_PATTERN must have named groups for {ContextConfig._named_groups}"
            )

    def load_for(self, profile):
        self.profile = profile
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
