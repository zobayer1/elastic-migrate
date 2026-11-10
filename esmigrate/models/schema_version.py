from datetime import datetime

from sqlalchemy import LargeBinary, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from esmigrate.commons import MigVersion
from esmigrate.models.base import Base
from esmigrate.models.types import UTCDateTime


class SchemaVersion(Base):
    __tablename__ = "esm_schema_state"
    __table_args__ = (UniqueConstraint("namespace", "installed_rank"),)

    namespace: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_base: Mapped[int] = mapped_column(primary_key=True)
    version_rank: Mapped[int] = mapped_column(primary_key=True)
    installed_rank: Mapped[int | None]
    description: Mapped[str | None] = mapped_column(String(256))
    type: Mapped[str | None] = mapped_column(String(16))
    script: Mapped[str | None] = mapped_column(String(256))
    checksum: Mapped[bytes | None] = mapped_column(LargeBinary)
    installed_by: Mapped[str | None] = mapped_column(String(256))
    installed_on: Mapped[datetime | None] = mapped_column(UTCDateTime)
    execution_time: Mapped[int | None]
    success: Mapped[bool | None]
    query_results: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql", "mariadb"))

    @property
    def version(self) -> MigVersion:
        return MigVersion(base=self.version_base, rank=self.version_rank)


SCHEMA_TABLE: Table = Base.metadata.tables[SchemaVersion.__tablename__]
