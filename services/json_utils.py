import json
import re

from .providers.base import ProviderError

_FENCE = re.compile(r'^```(?:json)?\s*|\s*```$', re.IGNORECASE)
_THINK = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)


def extract_json(text):
    """Parse JSON from an LLM answer, tolerating code fences, <think> blocks
    and extra chatter around the object."""
    cleaned = _FENCE.sub('', _THINK.sub('', text or '').strip()).strip()
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    start, end = cleaned.find('{'), cleaned.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except ValueError:
            pass
    raise ProviderError('bad_response', 'The model did not return valid JSON.')