import json
import os
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError

if TYPE_CHECKING:
    from sphinx.application import Sphinx

RELEASES_URL = "https://github.com/zobayer1/elastic-migrate/releases"
LATEST_RELEASE_API = "https://api.github.com/repos/zobayer1/elastic-migrate/releases/latest"
OUTPUT = Path("_generated") / "latest-release.md"


def fetch_latest_release(url: str = LATEST_RELEASE_API, token: str | None = None) -> dict[str, Any] | None:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
            return json.load(response)
    except HTTPError as err:
        if err.code == 404:
            err.close()
            return None
        raise


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KiB"
    return f"{size / 1024**2:.1f} MiB"


def render_release(release: dict[str, Any] | None) -> str:
    if release is None:
        return f"No signed release has been published yet. See all releases on [GitHub]({RELEASES_URL}).\n"
    published = str(release.get("published_at") or "")[:10]
    lines = [
        f"## {release.get('name') or release['tag_name']}",
        "",
        f"Tag `{release['tag_name']}`, published {published}. [Release notes]({release['html_url']}).",
        "",
        "| File | Size |",
        "|---|---|",
    ]
    for asset in sorted(release.get("assets", []), key=lambda item: item["name"]):
        lines.append(f"| [{asset['name']}]({asset['browser_download_url']}) | {format_size(asset['size'])} |")
    return "\n".join(lines) + "\n"


def write_latest_release(app: "Sphinx") -> None:
    try:
        release = fetch_latest_release(token=os.getenv("GITHUB_TOKEN"))
        content = render_release(release)
    except (HTTPError, URLError, TimeoutError):
        if os.getenv("GITHUB_ACTIONS") == "true":
            raise
        content = f"Release information could not be loaded. See all releases on [GitHub]({RELEASES_URL}).\n"
    output = Path(app.srcdir) / OUTPUT
    output.parent.mkdir(exist_ok=True)
    output.write_text(content, encoding="utf-8")


def setup(app: "Sphinx") -> dict[str, Any]:
    app.connect("builder-inited", write_latest_release)
    return {"parallel_read_safe": True}
