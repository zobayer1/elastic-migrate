import importlib.util
import io
import json
import re
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

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


def load_latest_release_extension():
    spec = importlib.util.spec_from_file_location("latest_release", DOCS / "_ext" / "latest_release.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


latest_release = load_latest_release_extension()

RELEASE = {
    "name": "ElasticMigrate 2.0.0",
    "tag_name": "v2.0.0",
    "html_url": "https://github.com/zobayer1/elastic-migrate/releases/tag/v2.0.0",
    "published_at": "2026-11-01T10:00:00Z",
    "assets": [
        {"name": "SHA256SUMS", "browser_download_url": "https://example.com/SHA256SUMS", "size": 300},
        {
            "name": "elastic_migrate-2.0.0.tar.gz",
            "browser_download_url": "https://example.com/sdist",
            "size": 2_400_000,
        },
        {
            "name": "elastic_migrate-2.0.0-py3-none-any.whl",
            "browser_download_url": "https://example.com/whl",
            "size": 40_960,
        },
    ],
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


@pytest.mark.parametrize(("size", "expected"), [(300, "300 B"), (40_960, "40.0 KiB"), (2_400_000, "2.3 MiB")])
def test_latest_release_formats_sizes(size, expected):
    """Test fails if asset sizes are not shown in B, KiB or MiB"""
    assert latest_release.format_size(size) == expected


def test_latest_release_renders_assets_sorted():
    """Test fails if the latest release is not rendered with its tag, date, notes link and sorted asset table"""
    text = latest_release.render_release(RELEASE)
    assert text.startswith("## ElasticMigrate 2.0.0\n")
    assert "Tag `v2.0.0`, published 2026-11-01. [Release notes](https://github.com/" in text
    rows = [line for line in text.splitlines() if line.startswith("| [")]
    assert [row.split("]")[0][3:] for row in rows] == [
        "SHA256SUMS",
        "elastic_migrate-2.0.0-py3-none-any.whl",
        "elastic_migrate-2.0.0.tar.gz",
    ]
    assert "| 40.0 KiB |" in text


def test_latest_release_falls_back_to_tag_name():
    """Test fails if a release without a name is not titled by its tag"""
    assert latest_release.render_release({**RELEASE, "name": None, "assets": []}).startswith("## v2.0.0\n")


def test_latest_release_without_release():
    """Test fails if a missing release is not explained with a link to all releases"""
    assert "No signed release has been published yet" in latest_release.render_release(None)


def test_fetch_latest_release_sends_token_and_parses_json(mocker):
    """Test fails if the release API response is not parsed or the token is not sent"""
    urlopen = mocker.patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(RELEASE).encode()))
    assert latest_release.fetch_latest_release(token="secret")["tag_name"] == "v2.0.0"
    request = urlopen.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer secret"


@pytest.mark.parametrize(("code", "outcome"), [(404, None), (500, "raises")])
def test_fetch_latest_release_handles_http_errors(mocker, code, outcome):
    """Test fails if a missing release is not None or other API errors are swallowed"""
    error = urllib.error.HTTPError(latest_release.LATEST_RELEASE_API, code, "error", Message(), None)
    mocker.patch("urllib.request.urlopen", side_effect=error)
    if outcome == "raises":
        with pytest.raises(urllib.error.HTTPError) as raised:
            latest_release.fetch_latest_release()
        raised.value.close()
    else:
        assert latest_release.fetch_latest_release() is None
        assert error.fp is None or error.fp.closed


def test_write_latest_release_writes_generated_page(tmp_path, mocker):
    """Test fails if the generated page is not written into the docs source directory"""
    mocker.patch.object(latest_release, "fetch_latest_release", return_value=RELEASE)
    latest_release.write_latest_release(SimpleNamespace(srcdir=str(tmp_path)))
    assert "## ElasticMigrate 2.0.0" in (tmp_path / "_generated" / "latest-release.md").read_text()


def test_write_latest_release_tolerates_offline_local_builds(tmp_path, mocker, monkeypatch):
    """Test fails if a local build without network access fails instead of rendering a fallback"""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    mocker.patch.object(latest_release, "fetch_latest_release", side_effect=urllib.error.URLError("offline"))
    latest_release.write_latest_release(SimpleNamespace(srcdir=str(tmp_path)))
    assert "could not be loaded" in (tmp_path / "_generated" / "latest-release.md").read_text()


def test_write_latest_release_fails_in_ci_without_release_data(tmp_path, mocker, monkeypatch):
    """Test fails if a CI build publishes the site without release data when the API is unreachable"""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    mocker.patch.object(latest_release, "fetch_latest_release", side_effect=urllib.error.URLError("offline"))
    with pytest.raises(urllib.error.URLError):
        latest_release.write_latest_release(SimpleNamespace(srcdir=str(tmp_path)))


def test_latest_release_extension_registers_hook():
    """Test fails if the extension does not generate the page when the builder starts"""
    app = SimpleNamespace(connect=lambda event, handler: calls.append((event, handler)))
    calls = []
    assert latest_release.setup(app) == {"parallel_read_safe": True}
    assert calls == [("builder-inited", latest_release.write_latest_release)]
