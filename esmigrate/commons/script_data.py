from hashlib import sha1


class ScriptData:
    @staticmethod
    def make_sha1(s: str, encoding: str = "utf-8") -> bytes:
        return sha1(s.encode(encoding)).digest()

    def __init__(
        self, version: int | str, sequence: int | str, name: str, extension: str, path: str, content: str
    ) -> None:
        self.version_base = int(version)
        self.version_rank = int(sequence)
        self.description = f"{name}.{extension}"
        self.version = f"{version}.{sequence}"
        self.path = path
        self.content = content
        self.checksum = ScriptData.make_sha1(content)
        self.status = None

    @property
    def version_key(self) -> tuple[int, int]:
        return self.version_base, self.version_rank
