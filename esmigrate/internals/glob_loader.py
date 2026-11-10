import glob
import os
from collections import defaultdict
from collections.abc import Iterable

from esmigrate.commons import MAX_VERSION_PART, Direction, Migration, MigVersion, ScriptData
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import InvalidSchemaFileError, InvalidSchemaPatternError, error_list

ZERO_VERSION = MigVersion(0, 0)


def pair_scripts(scripts: Iterable[ScriptData]) -> list[Migration]:
    by_version: defaultdict[MigVersion, list[ScriptData]] = defaultdict(list)
    for script in scripts:
        by_version[script.version].append(script)

    migrations: list[Migration] = []
    errors: list[str] = []
    for version in sorted(by_version):
        group = by_version[version]
        files = ", ".join(sorted(script.path for script in group))
        plain = [script for script in group if script.direction is None]
        ups = [script for script in group if script.direction is Direction.UP]
        downs = [script for script in group if script.direction is Direction.DOWN]
        if version == ZERO_VERSION:
            errors.append(f"{version}: version 0.0 is not allowed ({files})")
        elif plain and (ups or downs):
            errors.append(f"{version}: plain and up/down files mixed, a plain file must be the only one ({files})")
        elif max(len(plain), len(ups), len(downs)) > 1:
            errors.append(f"{version}: duplicate version ({files})")
        elif ups and downs and ups[0].description != downs[0].description:
            errors.append(f"{version}: up and down script names must match ({files})")
        else:
            up = (plain or ups or [None])[0]
            migrations.append(Migration(up=up, down=downs[0] if downs else None))

    if errors:
        raise InvalidSchemaFileError(error_list("Invalid migrations:", errors))
    return migrations


class GlobLoader:
    def __init__(self, ctx: ContextConfig) -> None:
        self._ctx = ctx

    def scan_dir(self, schema_dir: str) -> list[ScriptData]:
        if not schema_dir or not os.path.isdir(schema_dir):
            raise NotADirectoryError(f"Not a valid directory: {schema_dir}")

        schema_ext = self._ctx.schema_ext if self._ctx.schema_ext.startswith(".") else f".{self._ctx.schema_ext}"

        matched: list[tuple[str, MigVersion, str, str, Direction | None]] = []
        errors: list[str] = []
        for _path in sorted(glob.glob(os.path.join(schema_dir, f"*{schema_ext}"))):
            _file = os.path.basename(_path)
            m = self._ctx.schema_regex.fullmatch(_file)
            if m is None or None in (m["version"], m["sequence"], m["name"], m["extension"]):
                errors.append(f"{_file}: does not match the configured pattern")
                continue
            try:
                _version = MigVersion(int(m["version"]), int(m["sequence"]))
            except ValueError:
                errors.append(f"{_file}: invalid version, each part must be a whole number up to {MAX_VERSION_PART}")
                continue
            _raw_direction = m.groupdict().get("direction")
            try:
                _direction = Direction(_raw_direction) if _raw_direction else None
            except ValueError:
                errors.append(f"{_file}: invalid direction '{_raw_direction}', must be up or down")
                continue
            matched.append((_path, _version, m["name"], m["extension"], _direction))

        if errors:
            raise InvalidSchemaPatternError(error_list("Illegal file names:", errors))

        file_items: list[ScriptData] = []
        for _path, _version, _name, _ext, _direction in matched:
            try:
                with open(_path, encoding="utf-8") as schema_file:
                    _content = schema_file.read()
            except Exception as err:
                raise InvalidSchemaFileError(f"Error reading file: {_path}, {err!s}") from err

            file_items.append(
                ScriptData(
                    version=_version,
                    name=_name,
                    extension=_ext,
                    path=os.path.relpath(_path, schema_dir),
                    content=_content,
                    direction=_direction,
                )
            )

        return sorted(file_items, key=lambda k: (k.version, k.path))

    def load_migrations(self, schema_dir: str) -> list[Migration]:
        return pair_scripts(self.scan_dir(schema_dir))
