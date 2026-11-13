import pytest

from esmigrate.commons import Direction, Migration, MigVersion, ScriptData

VERSION = MigVersion(1, 10)


def make_script(name, direction):
    segment = f".{direction}" if direction else ""
    return ScriptData(VERSION, name, "esm", f"V1_10__{name}{segment}.esm", "GET twitter", direction)


def test_migration_with_up_and_down_is_reversible():
    """Test fails if a migration with both scripts does not keep them and take its details from the up script"""
    up, down = make_script("from_up", Direction.UP), make_script("from_down", Direction.DOWN)
    migration = Migration(up=up, down=down)
    assert migration.up is up
    assert migration.down is down
    assert migration.version == VERSION
    assert migration.description == "from_up.esm"
    assert migration.reversible


@pytest.mark.parametrize("direction", [Direction.UP, None])
def test_migration_without_down_is_irreversible(direction):
    """Test fails if an up or plain script without a down script counts as reversible"""
    script = make_script("only_up", direction)
    migration = Migration(up=script)
    assert migration.up is script
    assert migration.down is None
    assert migration.version == VERSION
    assert migration.description == "only_up.esm"
    assert not migration.reversible


def test_migration_with_only_down_takes_its_details_from_down():
    """Test fails if a down-only migration is not reversible or does not take its details from the down script"""
    down = make_script("only_down", Direction.DOWN)
    migration = Migration(down=down)
    assert migration.up is None
    assert migration.down is down
    assert migration.version == VERSION
    assert migration.description == "only_down.esm"
    assert migration.reversible


def test_migration_requires_at_least_one_script():
    """Test fails if a migration can be built without any script"""
    with pytest.raises(ValueError, match="needs an up or a down script"):
        Migration()


@pytest.mark.parametrize("direction", [Direction.UP, Direction.DOWN])
def test_migration_returns_the_script_for_a_direction(direction):
    """Test fails if script_for does not return the up script for up and the down script for down"""
    up, down = make_script("pair", Direction.UP), make_script("pair", Direction.DOWN)
    assert Migration(up=up, down=down).script_for(direction) is (up if direction is Direction.UP else down)


@pytest.mark.parametrize(("present", "missing"), [(Direction.UP, Direction.DOWN), (Direction.DOWN, Direction.UP)])
def test_migration_has_no_script_for_a_missing_direction(present, missing):
    """Test fails if script_for returns a script for a direction the migration does not have"""
    migration = Migration(**{present.value: make_script("only_one", present)})
    assert migration.script_for(missing) is None
