# -*- coding: utf-8 -*-
import getpass
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, LargeBinary

from esmigrate.models.base import Base


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    version = Column(String, primary_key=True)
    version_rank = Column(Integer)
    installed_rank = Column(Integer)
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
