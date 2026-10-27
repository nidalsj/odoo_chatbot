from .base import ProviderError
from .openai_compatible import OpenAICompatibleProvider


def build_provider(config):
    # Every preset speaks the OpenAI chat-completions format.
    return OpenAICompatibleProvider(config)