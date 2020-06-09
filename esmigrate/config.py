# -*- coding: utf-8 -*-


class Config(object):
    def __init__(self):
        self.es_host = 'http://localhost:9200'
        self.schema_versions_db = 'sqlite:///esmigrate.db'

    def load_for(self, profile):
        return self
