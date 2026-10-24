from esmigrate.commons import ScriptData


def test_script_data_stores_integer_version_key():
    """Test fails if ScriptData does not convert regex-captured strings to an integer version key"""
    script_data = ScriptData("1", "10", "create_index", "esm", "V1_10__create_index.esm", "GET twitter")
    assert script_data.version_key == (1, 10)
    assert script_data.version == "1.10"
