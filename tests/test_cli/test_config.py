from tests.test_cli.helpers import (
    ES_HOST,
    invoke,
)


def test_cli_config_command_loads_context_profile(runner, context):
    """Test fails if `esmigrate config` does not print the loaded profile"""
    result = invoke(runner, "config")
    assert result.exit_code == 0
    assert f'elastic_host: "{ES_HOST}"' in result.output
