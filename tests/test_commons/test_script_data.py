import dataclasses
import hashlib

import pytest

from esmigrate.commons import MAX_VERSION_PART, Direction, MigVersion, ScriptData


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


@pytest.mark.parametrize(("text", "member"), [("up", Direction.UP), ("down", Direction.DOWN)])
def test_direction_matches_its_file_name_segment(text, member):
    """Test fails if a direction cannot be built from, or printed as, its file name segment"""
    assert Direction(text) is member
    assert str(member) == text


@pytest.mark.parametrize("text", ["UP", "sideways", ""])
def test_direction_rejects_other_text(text):
    """Test fails if anything other than up or down is accepted as a direction"""
    with pytest.raises(ValueError, match="not a valid Direction"):
        Direction(text)


def test_script_data_stores_file_details():
    """Test fails if ScriptData does not keep the version, description, path, content, checksum and direction"""
    version = MigVersion(1, 10)
    script = ScriptData(version, "create_index", "esm", "V1_10__create_index.up.esm", "GET twitter", Direction.UP)
    assert script.version == version
    assert script.description == "create_index.esm"
    assert script.path == "V1_10__create_index.up.esm"
    assert script.content == "GET twitter"
    assert script.checksum == hashlib.sha1(b"GET twitter").digest()
    assert script.direction is Direction.UP


def test_script_data_is_plain_without_a_direction():
    """Test fails if a script built without a direction is not a plain file"""
    script = ScriptData(MigVersion(1, 0), "create_index", "esm", "V1_0__create_index.esm", "GET twitter")
    assert script.direction is None
