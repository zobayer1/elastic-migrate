# -*- coding: utf-8 -*-


class ContextConfig(object):
    def __init__(self):
        self.es_host = 'http://localhost:9200'
        self.schema_versions_db = 'sqlite:///esmigrate.db'
        self.profile = 'dev'
        self.headers = {}
        self.schema_dir = None
        self.schema_ext = '.exm'

    def load_for(self, profile):
        self.profile = profile
        return self
