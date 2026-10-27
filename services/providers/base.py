class ProviderError(Exception):
    """Raised for every provider failure with a user readable message"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class BaseProvider:
    def __init__(self, config):
        self.config = config

    def complete(self, system_prompt, user_message, json_mode=False):
        raise NotImplementedError

    def test(self):
        """Return latency in ms or raise ProviderError"""
        raise NotImplementedError