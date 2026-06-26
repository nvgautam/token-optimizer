class SessionManager:
    def __init__(self, pty_wrapper, tokenizer, config):
        raise NotImplementedError

    def trigger_handoff(self) -> None:
        raise NotImplementedError
