# -*- coding: utf-8 -*-


class ContextConfig(object):
    def __init__(self):
        self.es_host = 'http://localhost:9200'
        self.schema_versions_db = 'sqlite:///esmigrate.db'
        self.profile = 'dev'

    def load_for(self, profile):
        self.profile = profile
        return self
