# -*- coding: utf-8 -*-
import os
import pwd
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, LargeBinary

from esmigrate.models.base import Base


class SchemaVersion(Base):
    __tablename__ = 'schema_version'

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

    def __init__(self):
        self.installed_by = pwd.getpwuid(os.getuid()).pw_name
        self.installed_on = datetime.now()
