# -*- coding: utf-8 -*-
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError, ArgumentError
from sqlalchemy.orm import sessionmaker

from esmigrate.exceptions import InvalidDBConnectionError, InvalidSchemaVersionError
from esmigrate.models import SchemaVersion
from esmigrate.models.base import Base


class DBManager(object):
    def __init__(self, db_url: str, echo: bool = False):
        try:
            self.engine = create_engine(db_url, echo=echo)
            self.session = sessionmaker(bind=self.engine)()
        except ArgumentError as err:
            raise InvalidDBConnectionError(str(err))

    def __del__(self):
        if hasattr(self, "session") and self.session:
            self.session.close()

    def initialize_db(self):
        Base.metadata.create_all(bind=self.engine)

    def insert_new_schema(self, scmver: SchemaVersion):
        try:
            self.session.add(scmver)
            self.session.commit()
        except SQLAlchemyError as err:
            self.session.rollback()
            raise InvalidSchemaVersionError(str(err))

    def find_schema_by_version(self, version: str):
        return self.session.query(SchemaVersion).get(version)
