import json
import re
from pathlib import Path

import pytest

from esmigrate.commons import local_config_file_path
from esmigrate.contexts import ContextConfig

DOCS = Path(__file__).parents[1] / "docs"
JSON_BLOCK = re.compile(r"```json\n(.*?)```", re.DOTALL)
ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
FILE_FIELDS = ("elastic_ca_certs", "elastic_client_cert", "elastic_client_key")


def config_examples():
    for page in sorted(DOCS.glob("*.md")):
        for index, block in enumerate(JSON_BLOCK.findall(page.read_text(encoding="utf-8"))):
            data = json.loads(block)
            if "profiles" in data:
                yield pytest.param(data, id=f"{page.stem}-{index}")


EXAMPLES = list(config_examples())


def test_docs_contain_config_examples():
    """Test fails if the documentation config examples are no longer found, which would silently skip their checks"""
    assert len(EXAMPLES) >= 7


@pytest.mark.parametrize("config", EXAMPLES)
def test_documented_config_examples_load(fs, monkeypatch, config):
    """Test fails if a config.json example in the documentation cannot be loaded"""
    monkeypatch.delenv("ESMIGRATE_CONFIG", raising=False)
    for name in set(ENV_REFERENCE.findall(json.dumps(config))):
        monkeypatch.setenv(name, "example")
    profiles = {name: fields for entry in config["profiles"] for name, fields in entry.items()}
    for fields in profiles.values():
        for field in FILE_FIELDS:
            if field in fields:
                fs.create_file(fields[field])
    fs.create_file(local_config_file_path, contents=json.dumps(config))
    for name in profiles:
        assert ContextConfig().load_for(name).profile == name
