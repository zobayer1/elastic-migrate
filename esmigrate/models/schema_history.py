from datetime import datetime

from sqlalchemy import Index, LargeBinary, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from esmigrate.models.base import Base
from esmigrate.models.types import UTCDateTime


class SchemaHistory(Base):
    __tablename__ = "esm_schema_history"
    __table_args__ = (Index("ix_esm_schema_history_namespace_id", "namespace", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    namespace: Mapped[str] = mapped_column(String(64))
    version_base: Mapped[int | None]
    version_rank: Mapped[int | None]
    operation: Mapped[str] = mapped_column(String(8))
    description: Mapped[str | None] = mapped_column(String(256))
    script: Mapped[str | None] = mapped_column(String(256))
    checksum: Mapped[bytes | None] = mapped_column(LargeBinary)
    executed_by: Mapped[str | None] = mapped_column(String(256))
    executed_on: Mapped[datetime | None] = mapped_column(UTCDateTime)
    execution_time: Mapped[int | None]
    success: Mapped[bool | None]
    query_results: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql", "mariadb"))
