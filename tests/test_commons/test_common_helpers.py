# -*- coding: utf-8 -*-
import os

from esmigrate.commons import is_valid_json, is_valid_ndjson, is_valid_path, parse_file_path


def test_is_valid_json_succeeds():
    test_string = """
        {
            "query": {"match_all": {}}
        }
        """
    assert is_valid_json(test_string)


def test_is_valid_json_fails():
    test_string = """
        {
            'query': {'match_all': {}}
        }
        """
    assert not is_valid_json(test_string)


def test_is_valid_ndjson_succeeds_single():
    test_string = """{"key": "value"}"""
    assert is_valid_ndjson(test_string)


def test_is_valid_ndjson_succeeds_multiple():
    test_string = """{"key1": "value1"}\n{"key2": "value2"}\n"""
    assert is_valid_ndjson(test_string)


def test_is_valid_ndjson_fails():
    test_string = """
        {
            "query": {"match_all": {}}
        }
        """
    assert not is_valid_ndjson(test_string)


def test_is_valid_path_succeeds():
    assert is_valid_path('http://192.168.5.127:9200', 'twitter/_search?size=100')


def test_is_valid_path_fails():
    assert not is_valid_path('just_a_string', 'which won\'t pass')


def test_parse_file_path_succeeds():
    file_path = os.path.join(os.getcwd(), 'README.md')
    prefix, filename, extension = parse_file_path(file_path)
    assert file_path == os.path.join(prefix, filename + extension)
