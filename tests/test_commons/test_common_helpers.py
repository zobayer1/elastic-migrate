# -*- coding: utf-8 -*-
import os

from esmigrate.commons import is_valid_json, is_valid_ndjson, is_valid_url_path, parse_file_path


def test_is_valid_json_succeeds():
    assert is_valid_json("""
        {
            "query": {"match_all": {}}
        }
        """)


def test_is_valid_json_fails():
    assert not is_valid_json("""
        {
            'query': {'match_all': {}}
        }
        """)


def test_is_valid_ndjson_succeeds_for_single_line():
    assert is_valid_ndjson("""{"key": "value"}""")


def test_is_valid_ndjson_succeeds_for_multiple_lines():
    assert is_valid_ndjson("""{"key1": "value1"}\n{"key2": "value2"}\n""")


def test_is_valid_ndjson_fails():
    assert not is_valid_ndjson("""
        {
            "query": {"match_all": {}}
        }
        """)


def test_is_valid_path_succeeds():
    assert is_valid_url_path('http://192.168.5.127:9200', 'twitter/_search?size=100')


def test_is_valid_path_fails():
    assert not is_valid_url_path('just_a_string', 'which won\'t pass')


def test_parse_file_path_succeeds():
    file_path = os.path.join(os.getcwd(), 'README.md')
    prefix, filename, extension = parse_file_path(file_path)
    assert file_path == os.path.join(prefix, filename + extension)
