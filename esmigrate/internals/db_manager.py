# -*- coding: utf-8 -*-
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError, ArgumentError, UnboundExecutionError
from sqlalchemy.orm import sessionmaker

from esmigrate.exceptions import InvalidDBConnectionError, SchemaVersionSqlDbError
from esmigrate.models import SchemaVersion
from esmigrate.models.base import Base


class DBManager(object):
    def __init__(self, db_url: str, echo: bool = False):
        try:
            self.engine = create_engine(db_url, echo=echo)
            self.session = sessionmaker(bind=self.engine)()
            Base.metadata.create_all(bind=self.engine)
        except (ArgumentError, UnboundExecutionError) as err:
            raise InvalidDBConnectionError(str(err))

    def __del__(self):
        if hasattr(self, "session") and self.session:
            self.session.close()

    def schema_version_exists(self):
        return SchemaVersion.metadata.tables[SchemaVersion.__tablename__].exists(self.engine)

    def insert_new_schema(self, scmver: SchemaVersion):
        try:
            scmver_latest = self.find_latest_schema()
            if scmver_latest and not scmver_latest.success:
                self.session.rollback()
                raise SchemaVersionSqlDbError(f"Failed previous version: {scmver_latest.version}")
            scmver.installed_rank = scmver_latest.installed_rank + 1 if scmver_latest else 1
            self.session.add(scmver)
            self.session.commit()
        except SQLAlchemyError as err:
            self.session.rollback()
            raise SchemaVersionSqlDbError(str(err))

    def find_schema_by_version(self, version: str):
        return self.session.query(SchemaVersion).get(version)

    def find_latest_schema(self):
        return self.session.query(SchemaVersion).order_by(SchemaVersion.installed_rank.desc()).first()

    def find_all_schema(self):
        return self.session.query(SchemaVersion).order_by(SchemaVersion.installed_rank).all()

    def delete_all_failed_schema(self):
        try:
            self.session.query(SchemaVersion).filter(SchemaVersion.success.is_(False)).delete()
            self.session.commit()
        except SQLAlchemyError as err:  # pragma: no cover
            self.session.rollback()
            raise SchemaVersionSqlDbError(str(err))

    def delete_all_schema(self, cutoff_rank: int = 0):
        try:
            self.session.query(SchemaVersion).filter(SchemaVersion.installed_rank >= cutoff_rank).delete()
            self.session.commit()
        except SQLAlchemyError as err:  # pragma: no cover
            self.session.rollback()
            raise SchemaVersionSqlDbError(str(err))
