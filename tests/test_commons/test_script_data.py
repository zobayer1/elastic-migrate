import hashlib

import pytest

from esmigrate.commons import Direction, MigVersion, Operation, ScriptData
from esmigrate.commons.script_data import make_sha1


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


@pytest.mark.parametrize(
    ("member", "text"),
    [(Operation.UP, "up"), (Operation.DOWN, "down"), (Operation.FORCE, "force"), (Operation.RESET, "reset")],
)
def test_operation_is_stored_under_its_lower_case_name(member, text):
    """Test fails if a history operation is not stored and printed as its lower-case name"""
    assert member.value == text
    assert str(member) == text


@pytest.mark.parametrize("direction", list(Direction))
def test_every_direction_has_a_matching_operation(direction):
    """Test fails if a script direction cannot be recorded as the history operation of the same name"""
    assert Operation(direction.value).value == direction.value


def test_make_sha1_returns_raw_digest_of_utf8_text():
    """Test fails if make_sha1 does not return the raw SHA-1 digest of the UTF-8 encoded text"""
    assert make_sha1("").hex() == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    assert make_sha1("zoë") == hashlib.sha1("zoë".encode()).digest()


def test_make_sha1_honours_requested_encoding():
    """Test fails if make_sha1 ignores the requested encoding"""
    assert make_sha1("zoë", encoding="latin-1") == hashlib.sha1("zoë".encode("latin-1")).digest()
