import pytest

from esmigrate.commons import parse_version


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
