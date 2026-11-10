from esmigrate.commons.script_data import Direction, ScriptData


class Migration:
    def __init__(self, up: ScriptData | None = None, down: ScriptData | None = None) -> None:
        self.up = up
        self.down = down
        self.reversible = down is not None
        if up is not None:
            self.version = up.version
            self.description = up.description
        elif down is not None:
            self.version = down.version
            self.description = down.description
        else:
            raise ValueError("Up and down migrations cannot be empty at the same time")

    def script_for(self, direction: Direction) -> ScriptData | None:
        return self.up if direction is Direction.UP else self.down
