import hashlib

import pytest

from esmigrate.commons import make_sha1, parse_version


@pytest.fixture
def parameter(request):
    """pytest fixture for allowing indirect pytest.mark.parametrize"""
    return request.param


@pytest.mark.parametrize(
    ("parameter", "expected"),
    [("1.2", (1, 2)), ("1.10", (1, 10)), ("10.1", (10, 1)), ("2", (2, 0)), (" 01.09 ", (1, 9))],
    indirect=["parameter"],
)
def test_parse_version_parses_valid_versions(parameter, expected):
    """Test fails if parse_version does not return integer (base, sequence) pairs"""
    assert parse_version(parameter) == expected


@pytest.mark.parametrize("parameter", ["", "latest", "1.", ".1", "1.2.3", "1.x", "-1.0"], indirect=["parameter"])
def test_parse_version_raises_value_error(parameter):
    """Test fails if parse_version does not raise ValueError for invalid versions"""
    with pytest.raises(ValueError, match="Invalid version"):
        parse_version(parameter)


def test_parse_version_orders_double_digit_sequences_after_single_digit():
    """Test fails if version 1.10 does not sort after 1.9"""
    assert parse_version("1.9") < parse_version("1.10") < parse_version("9.1") < parse_version("10.1")


def test_make_sha1_returns_raw_digest_of_utf8_text():
    """Test fails if make_sha1 does not return the raw SHA-1 digest of the UTF-8 encoded text"""
    assert make_sha1("").hex() == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    assert make_sha1("zoë") == hashlib.sha1("zoë".encode()).digest()


def test_make_sha1_honours_requested_encoding():
    """Test fails if make_sha1 ignores the requested encoding"""
    assert make_sha1("zoë", encoding="latin-1") == hashlib.sha1("zoë".encode("latin-1")).digest()
