# -*- coding: utf-8 -*-
import getpass
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from esmigrate.commons import ScriptData
from esmigrate.models.base import Base


class SchemaVersion(Base):
    __tablename__ = "esm_schema_version"

    version: Mapped[str] = mapped_column(primary_key=True)
    version_base: Mapped[int | None]
    version_rank: Mapped[int | None]
    installed_rank: Mapped[int | None] = mapped_column(unique=True)
    description: Mapped[str | None]
    type: Mapped[str | None]
    script: Mapped[str | None]
    checksum: Mapped[bytes | None]
    installed_by: Mapped[str | None]
    installed_on: Mapped[datetime | None]
    execution_time: Mapped[int | None]
    success: Mapped[bool | None]
    query_results: Mapped[str | None]

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
