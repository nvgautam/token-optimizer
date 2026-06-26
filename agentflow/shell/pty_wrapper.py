class PTYWrapper:
    def __init__(self, command: list, on_output=None, on_exit=None):
        raise NotImplementedError

    def read_output(self, timeout: float = 1.0) -> bytes:
        raise NotImplementedError

    def write_input(self, text: str) -> None:
        raise NotImplementedError
