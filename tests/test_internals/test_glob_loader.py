import pytest

from esmigrate.commons import MAX_VERSION_PART, Direction, MigVersion, ScriptData
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidSchemaFileError, InvalidSchemaPatternError
from esmigrate.internals import GlobLoader, pair_scripts

BASE_PATTERN = r"V(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>\w+)\.(?P<extension>esm)"
NO_MATCH = "does not match the configured pattern"
MIXED = "plain and up/down files mixed, a plain file must be the only one"
DUPLICATE = "duplicate version"
NAMES_DIFFER = "up and down script names must match"
ZERO = "version 0.0 is not allowed"


def make_script(version, name, direction, extension):
    parsed = MigVersion.parse(version)
    segment = f".{direction}" if direction else ""
    path = f"V{parsed.base}_{parsed.rank}__{name}{segment}.{extension}"
    return ScriptData(parsed, name, extension, path, "GET twitter", direction)


def plain(version, name="a", extension="esm"):
    return make_script(version, name, None, extension)


def up(version, name="a", extension="esm"):
    return make_script(version, name, Direction.UP, extension)


def down(version, name="a", extension="esm"):
    return make_script(version, name, Direction.DOWN, extension)


def loader_for(monkeypatch, pattern):
    monkeypatch.setenv("SCHEMA_PATTERN", pattern)
    return GlobLoader(ContextConfig())


@pytest.fixture(scope="module")
def glob_loader():
    """pytest fixture for providing default GlobLoader object"""
    return GlobLoader(ContextConfig())


def test_scan_dir_raises_not_a_directory_error(glob_loader):
    """Test fails if scan_dir does not raise error for invalid directory"""
    with pytest.raises(NotADirectoryError):
        glob_loader.scan_dir("not_a_valid_path")


def test_scan_dir_parses_valid_file_names(glob_loader, fs):
    """Test fails if scan_dir cannot process a valid schema directory"""
    fs.create_file("./schema_dir/V1_1__create_index_mapping_for_twitter.esm")
    assert len(glob_loader.scan_dir("./schema_dir")) > 0


def test_scan_dir_raises_invalid_schema_file_error(glob_loader, fs):
    """Test fails if scan_dir dies not raise error when schema file cannot be read"""
    fs.create_file("./schema_dir/V1_1__create_index_mapping_for_twitter.esm", contents="dummy", st_size=10000)
    with pytest.raises(InvalidSchemaFileError):
        glob_loader.scan_dir("./schema_dir")


def test_scan_dir_raises_invalid_schema_pattern_error(glob_loader, fs):
    """Test fails if scan_dir does not raise error for invalid file names"""
    fs.create_file("./schema_dir/V1_1_create_index_mapping_for_twitter.esm")
    with pytest.raises(InvalidSchemaPatternError):
        glob_loader.scan_dir("./schema_dir")


def test_scan_dir_raises_context_object_not_set_error():
    """Test fails if scan_dir does not raise error when called without a context"""
    with pytest.raises(ContextObjectNotSetError):
        GlobLoader().scan_dir(".")


def test_scan_dir_sorts_versions_numerically(glob_loader, fs):
    """Test fails if scan_dir sorts versions or sequences of 10 and above lexicographically"""
    for name in ["V10_1__d.esm", "V1_10__b.esm", "V9_1__c.esm", "V1_9__a.esm", "V1_2__x.esm"]:
        fs.create_file(f"./schema_dir/{name}")
    versions = [str(item.version) for item in glob_loader.scan_dir("./schema_dir")]
    assert versions == ["1.2", "1.9", "1.10", "9.1", "10.1"]


def test_scan_dir_stores_paths_relative_to_schema_dir(glob_loader, fs):
    """Test fails if scan_dir keeps the schema directory prefix in script paths"""
    fs.create_file("/srv/project/schema_dir/V1_1__create_index.esm")
    assert [item.path for item in glob_loader.scan_dir("/srv/project/schema_dir")] == ["V1_1__create_index.esm"]


@pytest.mark.parametrize("name", ["V2147483648_1__too_big.esm", "V1_2147483648__too_big.esm"])
def test_scan_dir_rejects_versions_exceeding_integer_columns(glob_loader, fs, name):
    """Test fails if version parts larger than a 32-bit INTEGER column are accepted"""
    fs.create_file(f"./schema_dir/{name}")
    with pytest.raises(InvalidSchemaPatternError, match="invalid version"):
        glob_loader.scan_dir("./schema_dir")


def test_scan_dir_accepts_largest_version(glob_loader, fs):
    """Test fails if the largest 32-bit version and sequence are rejected"""
    fs.create_file("./schema_dir/V2147483647_2147483647__max.esm")
    assert glob_loader.scan_dir("./schema_dir")[0].version == MigVersion(MAX_VERSION_PART, MAX_VERSION_PART)


def test_scan_dir_reads_utf8_scripts(glob_loader, fs):
    """Test fails if schema files are not read as UTF-8 regardless of the locale"""
    fs.create_file("./schema_dir/V1_0__unicode.esm", contents='PUT twitter/_doc/1\n{"user": "zoë"}', encoding="utf-8")
    assert "zoë" in glob_loader.scan_dir("./schema_dir")[0].content


def test_scan_dir_uses_esm_extension_by_default(glob_loader, fs):
    """Test fails if the default extension is not .esm or legacy .exm files are picked up by default"""
    fs.create_file("./schema_dir/V1_0__new.esm")
    fs.create_file("./schema_dir/V1_1__legacy.exm")
    assert [item.description for item in glob_loader.scan_dir("./schema_dir")] == ["new.esm"]


def test_scan_dir_supports_configured_legacy_extension(fs):
    """Test fails if projects cannot keep their v1 .exm files by setting schema_ext"""
    context = ContextConfig()
    context.schema_ext = ".exm"
    fs.create_file("./schema_dir/V1_0__legacy.exm")
    fs.create_file("./schema_dir/V1_1__new.esm")
    assert [item.description for item in GlobLoader(context).scan_dir("./schema_dir")] == ["legacy.exm"]


def test_scan_dir_accepts_extension_without_leading_dot(fs):
    """Test fails if a schema_ext written without its dot does not select the same files"""
    context = ContextConfig()
    context.schema_ext = "esm"
    fs.create_file("./schema_dir/V1_0__a.esm")
    assert [item.description for item in GlobLoader(context).scan_dir("./schema_dir")] == ["a.esm"]


def test_scan_dir_returns_one_script_per_file_with_its_direction(glob_loader, fs):
    """Test fails if .up, .down and plain files are not separate scripts carrying their direction"""
    for name in ["V1_0__a.up.esm", "V1_0__a.down.esm", "V1_1__b.esm"]:
        fs.create_file(f"./schema_dir/{name}")
    assert [(item.path, item.direction, item.description) for item in glob_loader.scan_dir("./schema_dir")] == [
        ("V1_0__a.down.esm", Direction.DOWN, "a.esm"),
        ("V1_0__a.up.esm", Direction.UP, "a.esm"),
        ("V1_1__b.esm", None, "b.esm"),
    ]


def test_scan_dir_orders_scripts_regardless_of_listing_order(glob_loader, fs, mocker):
    """Test fails if the order of the scripts depends on the order the directory is listed in"""
    paths = [f"./schema_dir/{name}" for name in ["V1_10__c.esm", "V1_9__b.esm", "V1_0__a.up.esm", "V1_0__a.down.esm"]]
    for path in paths:
        fs.create_file(path)
    mocker.patch("esmigrate.internals.glob_loader.glob.glob", return_value=paths)
    assert [item.path for item in glob_loader.scan_dir("./schema_dir")] == [
        "V1_0__a.down.esm",
        "V1_0__a.up.esm",
        "V1_9__b.esm",
        "V1_10__c.esm",
    ]


def test_scan_dir_reads_leading_zeros_as_numbers(glob_loader, fs):
    """Test fails if leading zeros change the version or are dropped from the recorded path"""
    fs.create_file("./schema_dir/V01_010__a.esm")
    script = glob_loader.scan_dir("./schema_dir")[0]
    assert script.version == MigVersion(1, 10)
    assert script.path == "V01_010__a.esm"


def test_scan_dir_ignores_direction_after_the_extension(glob_loader, fs):
    """Test fails if a file with its direction after the extension is picked up"""
    fs.create_file("./schema_dir/V1_0__a.esm.up")
    assert glob_loader.scan_dir("./schema_dir") == []


def test_scan_dir_lists_every_illegal_file_name(glob_loader, fs):
    """Test fails if file name problems are not reported together, one sorted line per file"""
    for name in ["V9__bad.esm", "V2147483648_0__big.esm", "V1_0__fine.esm", "V1__bad.esm"]:
        fs.create_file(f"./schema_dir/{name}")
    with pytest.raises(InvalidSchemaPatternError) as err:
        glob_loader.scan_dir("./schema_dir")
    assert str(err.value) == (
        "Illegal file names:\n"
        f"  V1__bad.esm: {NO_MATCH}\n"
        f"  V2147483648_0__big.esm: invalid version, each part must be a whole number up to {MAX_VERSION_PART}\n"
        f"  V9__bad.esm: {NO_MATCH}"
    )


def test_scan_dir_lists_illegal_file_names_regardless_of_listing_order(glob_loader, fs, mocker):
    """Test fails if the file name error depends on the order the directory is listed in"""
    paths = ["./schema_dir/V9__b.esm", "./schema_dir/V1__a.esm"]
    for path in paths:
        fs.create_file(path)
    mocker.patch("esmigrate.internals.glob_loader.glob.glob", return_value=paths)
    with pytest.raises(InvalidSchemaPatternError) as err:
        glob_loader.scan_dir("./schema_dir")
    assert str(err.value) == f"Illegal file names:\n  V1__a.esm: {NO_MATCH}\n  V9__b.esm: {NO_MATCH}"


def test_scan_dir_reports_file_names_before_reading_files(glob_loader, fs):
    """Test fails if an unreadable file hides an illegal file name"""
    fs.create_file("./schema_dir/V1_0__unreadable.esm", contents="dummy", st_size=10000)
    fs.create_file("./schema_dir/V1__bad.esm")
    with pytest.raises(InvalidSchemaPatternError):
        glob_loader.scan_dir("./schema_dir")


def test_scan_dir_stops_at_the_first_unreadable_file(glob_loader, fs):
    """Test fails if a read error does not name the first unreadable file only"""
    fs.create_file("./schema_dir/V1_0__first.esm", contents="dummy", st_size=10000)
    fs.create_file("./schema_dir/V1_1__second.esm", contents="dummy", st_size=10000)
    with pytest.raises(InvalidSchemaFileError, match="Error reading file") as err:
        glob_loader.scan_dir("./schema_dir")
    assert "V1_0__first.esm" in str(err.value)
    assert "V1_1__second.esm" not in str(err.value)


def test_scan_dir_treats_every_file_as_plain_without_direction_group(fs, monkeypatch):
    """Test fails if a custom pattern without a direction group does not read every file as plain"""
    loader = loader_for(monkeypatch, r"V(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>[\w.]+)\.(?P<extension>esm)")
    fs.create_file("./schema_dir/V1_0__a.up.esm")
    script = loader.scan_dir("./schema_dir")[0]
    assert script.direction is None
    assert script.description == "a.up.esm"


def test_scan_dir_reads_groups_by_name(fs, monkeypatch):
    """Test fails if a custom pattern with its groups in another order is read by position"""
    loader = loader_for(monkeypatch, r"(?P<name>[a-z]+)-(?P<sequence>\d+)-(?P<version>\d+)\.(?P<extension>esm)")
    fs.create_file("./schema_dir/create-5-2.esm")
    script = loader.scan_dir("./schema_dir")[0]
    assert script.version == MigVersion(2, 5)
    assert script.description == "create.esm"


def test_scan_dir_reads_direction_from_custom_pattern(fs, monkeypatch):
    """Test fails if the direction captured by a custom pattern is not used"""
    loader = loader_for(
        monkeypatch, r"V(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>[a-z]+)-(?P<direction>\w+)\.(?P<extension>esm)"
    )
    fs.create_file("./schema_dir/V1_0__a-down.esm")
    assert loader.scan_dir("./schema_dir")[0].direction is Direction.DOWN


def test_scan_dir_treats_empty_direction_capture_as_plain(fs, monkeypatch):
    """Test fails if a direction group that captures nothing does not mean a plain file"""
    loader = loader_for(
        monkeypatch, r"V(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>[a-z]+)(?P<direction>)\.(?P<extension>esm)"
    )
    fs.create_file("./schema_dir/V1_0__a.esm")
    assert loader.scan_dir("./schema_dir")[0].direction is None


def test_scan_dir_lists_invalid_direction_capture(fs, monkeypatch):
    """Test fails if a captured direction other than up or down is not a file name error"""
    loader = loader_for(
        monkeypatch, r"V(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>[a-z]+)\.(?P<direction>\w+)\.(?P<extension>esm)"
    )
    fs.create_file("./schema_dir/V1_0__a.sideways.esm")
    with pytest.raises(InvalidSchemaPatternError) as err:
        loader.scan_dir("./schema_dir")
    assert str(err.value) == (
        "Illegal file names:\n  V1_0__a.sideways.esm: invalid direction 'sideways', must be up or down"
    )


def test_scan_dir_rejects_file_matching_only_part_of_the_pattern(fs, monkeypatch):
    """Test fails if a pattern that matches only the start of a file name is enough"""
    loader = loader_for(monkeypatch, r"V(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>\w)\.(?P<extension>es)")
    fs.create_file("./schema_dir/V1_0__a.esm")
    with pytest.raises(InvalidSchemaPatternError, match=NO_MATCH):
        loader.scan_dir("./schema_dir")


def test_scan_dir_rejects_prefix_before_the_default_pattern(glob_loader, fs):
    """Test fails if text before the version is accepted by the default pattern"""
    fs.create_file("./schema_dir/old_V1_0__a.esm")
    with pytest.raises(InvalidSchemaPatternError, match=NO_MATCH):
        glob_loader.scan_dir("./schema_dir")


@pytest.mark.parametrize(
    ("pattern", "file_name"),
    [
        (rf"{BASE_PATTERN}|W\d+\.esm", "W2.esm"),
        (r"V(?P<version>\d+)?_(?P<sequence>\d+)__(?P<name>\w+)\.(?P<extension>esm)", "V_1__a.esm"),
        (r"V(?P<version>\d+)_(?P<sequence>\d+)?__(?P<name>\w+)\.(?P<extension>esm)", "V1___a.esm"),
        (r"V(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>\w+)?\.(?P<extension>esm)", "V1_0__.esm"),
        (r"V(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>[a-z]+)\.?(?P<extension>zzz)?esm", "V1_0__a.esm"),
    ],
)
def test_scan_dir_rejects_match_without_a_required_group(fs, monkeypatch, pattern, file_name):
    """Test fails if a match in which a required group takes no part is not reported as a file name error"""
    loader = loader_for(monkeypatch, pattern)
    fs.create_file(f"./schema_dir/{file_name}")
    with pytest.raises(InvalidSchemaPatternError) as err:
        loader.scan_dir("./schema_dir")
    assert str(err.value) == f"Illegal file names:\n  {file_name}: {NO_MATCH}"


def test_scan_dir_supports_top_level_alternation(fs, monkeypatch):
    """Test fails if a file matching the first alternative of a custom pattern is not read"""
    loader = loader_for(monkeypatch, rf"{BASE_PATTERN}|W\d+\.esm")
    fs.create_file("./schema_dir/V1_0__a.esm")
    assert [str(item.version) for item in loader.scan_dir("./schema_dir")] == ["1.0"]


def test_scan_dir_supports_global_flags_in_pattern(fs, monkeypatch):
    """Test fails if a custom pattern with global flags does not apply them to file names"""
    loader = loader_for(monkeypatch, r"(?i)v(?P<version>\d+)_(?P<sequence>\d+)__(?P<name>\w+)\.(?P<extension>esm)")
    fs.create_file("./schema_dir/V1_0__a.esm")
    assert [str(item.version) for item in loader.scan_dir("./schema_dir")] == ["1.0"]


def test_pair_scripts_pairs_up_and_down():
    """Test fails if an .up and a .down with the same name are not one reversible migration"""
    up_script, down_script = up("1.0"), down("1.0")
    [migration] = pair_scripts([down_script, up_script])
    assert migration.up is up_script
    assert migration.down is down_script
    assert migration.version == MigVersion(1, 0)
    assert migration.description == "a.esm"
    assert migration.reversible


@pytest.mark.parametrize("build", [up, plain])
def test_pair_scripts_keeps_script_without_down_irreversible(build):
    """Test fails if a lone .up or plain file is not an irreversible migration"""
    script = build("1.0")
    [migration] = pair_scripts([script])
    assert migration.up is script
    assert migration.down is None
    assert not migration.reversible


def test_pair_scripts_allows_lone_down():
    """Test fails if a lone .down is not a reversible migration without an up script"""
    script = down("1.0")
    [migration] = pair_scripts([script])
    assert migration.up is None
    assert migration.down is script
    assert migration.version == MigVersion(1, 0)
    assert migration.description == "a.esm"
    assert migration.reversible


def test_pair_scripts_combines_every_valid_set_in_version_order():
    """Test fails if migrations of each valid kind are not returned sorted by version"""
    scripts = [plain("10.0"), up("1.10"), plain("1.9"), down("1.10"), down("9.1"), up("2.0")]
    assert [(str(item.version), item.reversible) for item in pair_scripts(scripts)] == [
        ("1.9", False),
        ("1.10", True),
        ("2.0", False),
        ("9.1", True),
        ("10.0", False),
    ]


def test_pair_scripts_accepts_any_iterable():
    """Test fails if pair_scripts needs a list or fails on empty input"""
    assert len(pair_scripts(script for script in [up("1.0"), down("1.0")])) == 1
    assert pair_scripts(iter([])) == []
    assert pair_scripts([]) == []


def test_pair_scripts_allows_zero_base_or_rank():
    """Test fails if a version other than 0.0 is rejected for having a zero part"""
    assert [str(item.version) for item in pair_scripts([plain("0.1"), plain("1.0")])] == ["0.1", "1.0"]


@pytest.mark.parametrize(
    ("scripts", "expected"),
    [
        ([plain("1.0"), up("1.0")], f"1.0: {MIXED} (V1_0__a.esm, V1_0__a.up.esm)"),
        ([plain("1.0"), down("1.0")], f"1.0: {MIXED} (V1_0__a.down.esm, V1_0__a.esm)"),
        ([plain("1.0"), up("1.0"), down("1.0")], f"1.0: {MIXED} (V1_0__a.down.esm, V1_0__a.esm, V1_0__a.up.esm)"),
        ([up("1.0", "a"), up("1.0", "b")], f"1.0: {DUPLICATE} (V1_0__a.up.esm, V1_0__b.up.esm)"),
        ([down("1.0", "a"), down("1.0", "b")], f"1.0: {DUPLICATE} (V1_0__a.down.esm, V1_0__b.down.esm)"),
        ([plain("1.0", "a"), plain("1.0", "b")], f"1.0: {DUPLICATE} (V1_0__a.esm, V1_0__b.esm)"),
        ([up("1.0", "a"), down("1.0", "b")], f"1.0: {NAMES_DIFFER} (V1_0__a.up.esm, V1_0__b.down.esm)"),
        ([up("1.0"), down("1.0", extension="exm")], f"1.0: {NAMES_DIFFER} (V1_0__a.down.exm, V1_0__a.up.esm)"),
    ],
)
def test_pair_scripts_rejects_invalid_sets(scripts, expected):
    """Test fails if an invalid set of files for a version is accepted or reported with the wrong message"""
    with pytest.raises(InvalidSchemaFileError) as err:
        pair_scripts(scripts)
    assert str(err.value) == f"Invalid migrations:\n  {expected}"


@pytest.mark.parametrize(
    ("scripts", "files"),
    [
        ([plain("0.0")], "V0_0__a.esm"),
        ([up("0.0")], "V0_0__a.up.esm"),
        ([down("0.0")], "V0_0__a.down.esm"),
        ([up("0.0"), down("0.0")], "V0_0__a.down.esm, V0_0__a.up.esm"),
    ],
)
def test_pair_scripts_rejects_version_zero(scripts, files):
    """Test fails if any file for version 0.0, which means nothing applied, is accepted"""
    with pytest.raises(InvalidSchemaFileError) as err:
        pair_scripts(scripts)
    assert str(err.value) == f"Invalid migrations:\n  0.0: {ZERO} ({files})"


@pytest.mark.parametrize(
    ("scripts", "expected"),
    [
        ([plain("0.0"), up("0.0")], f"0.0: {ZERO} (V0_0__a.esm, V0_0__a.up.esm)"),
        ([up("0.0", "a"), up("0.0", "b")], f"0.0: {ZERO} (V0_0__a.up.esm, V0_0__b.up.esm)"),
        ([up("0.0", "a"), down("0.0", "b")], f"0.0: {ZERO} (V0_0__a.up.esm, V0_0__b.down.esm)"),
        (
            [plain("1.0"), up("1.0", "a"), up("1.0", "b")],
            f"1.0: {MIXED} (V1_0__a.esm, V1_0__a.up.esm, V1_0__b.up.esm)",
        ),
        (
            [up("1.0", "a"), up("1.0", "b"), down("1.0", "c")],
            f"1.0: {DUPLICATE} (V1_0__a.up.esm, V1_0__b.up.esm, V1_0__c.down.esm)",
        ),
    ],
)
def test_pair_scripts_reports_only_the_first_problem_of_a_version(scripts, expected):
    """Test fails if a version does not report one error, in the order 0.0, mixed, duplicate, names differ"""
    with pytest.raises(InvalidSchemaFileError) as err:
        pair_scripts(scripts)
    assert str(err.value) == f"Invalid migrations:\n  {expected}"


def test_pair_scripts_lists_every_invalid_version_in_order():
    """Test fails if pairing problems are not reported together, one line per version sorted by version"""
    scripts = [
        up("10.0", "a"),
        down("10.0", "b"),
        plain("1.10"),
        up("1.10"),
        plain("2.0"),
        plain("1.9", "a"),
        plain("1.9", "b"),
        plain("0.0"),
    ]
    with pytest.raises(InvalidSchemaFileError) as err:
        pair_scripts(scripts)
    assert str(err.value) == (
        "Invalid migrations:\n"
        f"  0.0: {ZERO} (V0_0__a.esm)\n"
        f"  1.9: {DUPLICATE} (V1_9__a.esm, V1_9__b.esm)\n"
        f"  1.10: {MIXED} (V1_10__a.esm, V1_10__a.up.esm)\n"
        f"  10.0: {NAMES_DIFFER} (V10_0__a.up.esm, V10_0__b.down.esm)"
    )


def test_pair_scripts_lists_files_sorted_by_path():
    """Test fails if the files named in an error depend on the order of the input"""
    with pytest.raises(InvalidSchemaFileError) as err:
        pair_scripts([up("1.0", "b"), up("1.0", "a")])
    assert str(err.value) == f"Invalid migrations:\n  1.0: {DUPLICATE} (V1_0__a.up.esm, V1_0__b.up.esm)"


def test_load_migrations_groups_files_into_ordered_migrations(glob_loader, fs):
    """Test fails if load_migrations does not scan a directory and pair its files by version"""
    for name in ["V2_0__d.esm", "V1_10__c.down.esm", "V1_2__b.up.esm", "V1_1__a.up.esm", "V1_1__a.down.esm"]:
        fs.create_file(f"./schema_dir/{name}")
    migrations = glob_loader.load_migrations("./schema_dir")
    assert [
        (str(item.version), item.description, item.up and item.up.path, item.down and item.down.path, item.reversible)
        for item in migrations
    ] == [
        ("1.1", "a.esm", "V1_1__a.up.esm", "V1_1__a.down.esm", True),
        ("1.2", "b.esm", "V1_2__b.up.esm", None, False),
        ("1.10", "c.esm", None, "V1_10__c.down.esm", True),
        ("2.0", "d.esm", "V2_0__d.esm", None, False),
    ]


def test_load_migrations_keeps_each_script_content(glob_loader, fs):
    """Test fails if the up and down scripts of a migration do not keep their own content"""
    fs.create_file("./schema_dir/V1_0__a.up.esm", contents="PUT twitter")
    fs.create_file("./schema_dir/V1_0__a.down.esm", contents="DELETE twitter")
    [migration] = glob_loader.load_migrations("./schema_dir")
    assert migration.up.content == "PUT twitter"
    assert migration.down.content == "DELETE twitter"


def test_load_migrations_allows_empty_down_script(glob_loader, fs):
    """Test fails if an empty .down file is not a reversible migration"""
    fs.create_file("./schema_dir/V1_0__a.up.esm", contents="PUT twitter")
    fs.create_file("./schema_dir/V1_0__a.down.esm", contents="")
    [migration] = glob_loader.load_migrations("./schema_dir")
    assert migration.reversible
    assert migration.down.content == ""


def test_load_migrations_returns_nothing_for_empty_directory(glob_loader, fs):
    """Test fails if an empty directory is not an empty list of migrations"""
    fs.create_dir("./schema_dir")
    assert glob_loader.load_migrations("./schema_dir") == []


def test_load_migrations_pairs_files_across_leading_zeros(glob_loader, fs):
    """Test fails if an .up and a .down of the same integers written differently do not pair"""
    fs.create_file("./schema_dir/V1_01__a.up.esm")
    fs.create_file("./schema_dir/V1_1__a.down.esm")
    [migration] = glob_loader.load_migrations("./schema_dir")
    assert migration.version == MigVersion(1, 1)
    assert migration.reversible


def test_load_migrations_detects_duplicates_across_leading_zeros(glob_loader, fs):
    """Test fails if two plain files of the same integers written differently are not a duplicate version"""
    fs.create_file("./schema_dir/V1_01__a.esm")
    fs.create_file("./schema_dir/V1_1__b.esm")
    with pytest.raises(InvalidSchemaFileError) as err:
        glob_loader.load_migrations("./schema_dir")
    assert str(err.value) == f"Invalid migrations:\n  1.1: {DUPLICATE} (V1_01__a.esm, V1_1__b.esm)"


def test_load_migrations_reports_file_names_before_pairing(glob_loader, fs):
    """Test fails if a pairing problem hides an illegal file name"""
    fs.create_file("./schema_dir/V1__bad.esm")
    fs.create_file("./schema_dir/V1_0__a.esm")
    fs.create_file("./schema_dir/V1_0__a.up.esm")
    with pytest.raises(InvalidSchemaPatternError):
        glob_loader.load_migrations("./schema_dir")


def test_load_migrations_raises_not_a_directory_error(glob_loader):
    """Test fails if load_migrations does not raise error for invalid directory"""
    with pytest.raises(NotADirectoryError):
        glob_loader.load_migrations("not_a_valid_path")


def test_load_migrations_raises_context_object_not_set_error():
    """Test fails if load_migrations does not raise error when called without a context"""
    with pytest.raises(ContextObjectNotSetError):
        GlobLoader().load_migrations(".")
