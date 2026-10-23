import getpass
from datetime import datetime
from typing import Self

from sqlalchemy import LargeBinary, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from esmigrate.commons import ScriptData
from esmigrate.models.base import Base


class SchemaVersion(Base):
    __tablename__ = "esm_schema_version"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_base: Mapped[int | None]
    version_rank: Mapped[int | None]
    installed_rank: Mapped[int | None] = mapped_column(unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    type: Mapped[str | None] = mapped_column(String(16))
    script: Mapped[str | None] = mapped_column(String(1024))
    checksum: Mapped[bytes | None] = mapped_column(LargeBinary)
    installed_by: Mapped[str | None] = mapped_column(String(255))
    installed_on: Mapped[datetime | None]
    execution_time: Mapped[int | None]
    success: Mapped[bool | None]
    query_results: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql", "mariadb"))

    def __init__(self, version: str) -> None:
        self.version = version
        self.installed_by = getpass.getuser()
        self.installed_on = datetime.now()
        self.type = "NOSQL"

    @classmethod
    def from_script_data(cls, script_data: ScriptData) -> Self:
        scmver = cls(script_data.version)
        scmver.version_base = script_data.version_base
        scmver.version_rank = script_data.version_rank
        scmver.description = script_data.description
        scmver.script = script_data.path
        scmver.checksum = script_data.checksum
        return scmver
