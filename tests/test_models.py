# -*- coding: utf-8 -*-
from datetime import datetime
import getpass

from esmigrate.models.schema_version import SchemaVersion


def test_schema_version_model():
    schema_version = SchemaVersion()
    assert schema_version.installed_by == getpass.getuser()
    assert datetime.timestamp(schema_version.installed_on) > 0
