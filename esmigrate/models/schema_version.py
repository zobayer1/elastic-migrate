# -*- coding: utf-8 -*-
import getpass
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, LargeBinary

from esmigrate.commons import ScriptData
from esmigrate.models.base import Base


class SchemaVersion(Base):
    __tablename__ = "esm_schema_version"

    version = Column(String, primary_key=True)
    version_base = Column(Integer)
    version_rank = Column(Integer)
    installed_rank = Column(Integer, unique=True)
    description = Column(String)
    type = Column(String)
    script = Column(String)
    checksum = Column(LargeBinary)
    installed_by = Column(String)
    installed_on = Column(DateTime)
    execution_time = Column(Integer)
    success = Column(Boolean)
    query_results = Column(String)

    def __init__(self, version: str):
        self.version = version
        self.installed_by = getpass.getuser()
        self.installed_on = datetime.now()
        self.type = "NOSQL"

    @classmethod
    def from_script_data(cls, script_data: ScriptData):
        scmver = cls(script_data.version)
        scmver.version_base = script_data.version_base
        scmver.version_rank = script_data.version_rank
        scmver.description = script_data.description
        scmver.script = script_data.path
        scmver.checksum = script_data.checksum
        return scmver
