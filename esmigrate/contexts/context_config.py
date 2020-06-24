# -*- coding: utf-8 -*-
import json
import os


class ContextConfig(object):
    def __init__(self):
        self.es_host = 'http://localhost:9200'
        self.schema_db = 'sqlite:///esmigrate.db'
        self.profile = 'dev'
        self.headers = {}
        self.schema_dir = None
        self.schema_ext = '.exm'
        self._default_pattern = r'^V(?P<version>[\d]+)_(?P<sequence>[\d]+)__(?P<name>[\w]+)\.(?P<extension>[\w]+)$'
        self.schema_pattern = os.getenv('SCHEMA_PATTERN', self._default_pattern)

    def load_for(self, profile):
        self.profile = profile
        return self

    def __repr__(self):
        return 'Configurations:\n'\
               + f'profile: {self.profile}\n'\
               + f'elastic_host: {self.es_host}\n'\
               + f'elastic_headers: {json.dumps(self.headers)}\n'\
               + f'schema_version_db: {self.schema_db}\n'\
               + f'schema_file_directory: {self.schema_dir if self.schema_dir else os.getcwd()}\n'\
               + f'schema_file_extension: {self.schema_ext}\n'\
               + f'schema_filename_pattern: {self.schema_pattern}\n'
