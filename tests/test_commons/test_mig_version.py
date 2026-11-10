import dataclasses

import pytest

from esmigrate.commons import MAX_VERSION_PART, MigVersion, parse_version


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


def test_mig_version_orders_parts_numerically():
    """Test fails if versions are not ordered by base and then rank as integers"""
    versions = [MigVersion(10, 1), MigVersion(1, 10), MigVersion(9, 1), MigVersion(1, 9), MigVersion(1, 2)]
    assert [str(version) for version in sorted(versions)] == ["1.2", "1.9", "1.10", "9.1", "10.1"]


def test_mig_version_is_identified_by_its_integers():
    """Test fails if the same integers written with leading zeros count as a different version"""
    assert MigVersion.parse("1.01") == MigVersion.parse("1.1") == MigVersion(1, 1)
    assert len({MigVersion.parse("01.1"), MigVersion(1, 1)}) == 1


def test_mig_version_prints_base_and_rank():
    """Test fails if a version is not printed as base.rank"""
    assert str(MigVersion(1, 10)) == "1.10"
    assert f"{MigVersion(2, 0)}" == "2.0"


def test_mig_version_is_immutable():
    """Test fails if a version can be changed after it is created"""
    version = MigVersion(1, 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        version.base = 2  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", MigVersion(1, 0)),
        ("0", MigVersion(0, 0)),
        ("1.10", MigVersion(1, 10)),
        (" 01.09 ", MigVersion(1, 9)),
        (f"{MAX_VERSION_PART}.{MAX_VERSION_PART}", MigVersion(MAX_VERSION_PART, MAX_VERSION_PART)),
    ],
)
def test_mig_version_parses_valid_text(text, expected):
    """Test fails if MigVersion.parse does not read a base with an optional rank"""
    assert MigVersion.parse(text) == expected


@pytest.mark.parametrize("text", ["", "latest", "1.", ".1", "1.2.3", "1.x", "-1.0"])
def test_mig_version_parse_rejects_invalid_text(text):
    """Test fails if MigVersion.parse accepts text that is not a version"""
    with pytest.raises(ValueError, match="Invalid version"):
        MigVersion.parse(text)


@pytest.mark.parametrize("text", [str(MAX_VERSION_PART + 1), f"1.{MAX_VERSION_PART + 1}"])
def test_mig_version_parse_rejects_parts_out_of_range(text):
    """Test fails if MigVersion.parse accepts a part above the integer column limit"""
    with pytest.raises(ValueError, match="out of range"):
        MigVersion.parse(text)


@pytest.mark.parametrize(
    ("base", "rank"),
    [(0, 0), (0, MAX_VERSION_PART), (MAX_VERSION_PART, 0), (MAX_VERSION_PART, MAX_VERSION_PART)],
)
def test_mig_version_accepts_range_limits(base, rank):
    """Test fails if a part at the lowest or highest allowed value is rejected"""
    version = MigVersion(base, rank)
    assert (version.base, version.rank) == (base, rank)


@pytest.mark.parametrize(
    ("base", "rank"),
    [(-1, 0), (0, -1), (MAX_VERSION_PART + 1, 0), (0, MAX_VERSION_PART + 1)],
)
def test_mig_version_rejects_parts_out_of_range(base, rank):
    """Test fails if a part below zero or above the integer column limit is accepted"""
    with pytest.raises(ValueError, match="out of range"):
        MigVersion(base, rank)
