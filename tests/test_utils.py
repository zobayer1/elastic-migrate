# -*- coding: utf-8 -*-
from esmigrate.utils import title, version, version_short


def test_version():
    assert version and len(version) > 0


def test_version_short():
    assert version_short and len(version_short) > 0
    assert version_short in version


def test_title():
    assert title and len(title) > 0
