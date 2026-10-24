class Command:
    def __init__(self, verb: str, path: str, body: str | None = None, head: dict[str, str] | None = None) -> None:
        self.verb = verb
        self.path = path
        self.body = body
        self.head = head if head else {}

    @property
    def verb(self) -> str:
        return self._verb

    @verb.setter
    def verb(self, value: str) -> None:
        self._verb = value

    @property
    def path(self) -> str:
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        self._path = value

    @property
    def body(self) -> str | None:
        return self._body

    @body.setter
    def body(self, value: str | None) -> None:
        self._body = value

    @property
    def head(self) -> dict[str, str]:
        return self._head

    @head.setter
    def head(self, value: dict[str, str]) -> None:
        self._head = value
