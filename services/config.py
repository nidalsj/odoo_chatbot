from dataclasses import dataclass

PARAM_PREFIX = 'odoo_chatbot.'
DEFAULT_PROVIDER = 'groq'

# Models used in free tiers may change so this is just a seggestion.
# will tell you if one has been retired.
# If you face validation errors, check the provider's docs for the latest model names
PRESETS = {
    'groq': {
        'base_url': 'https://api.groq.com/openai/v1',
        'model_id': 'openai/gpt-oss-20b',
    },
    'gemini': {
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
        'model_id': 'gemini-3.5-flash',
    },
    'openrouter': {
        'base_url': 'https://openrouter.ai/api/v1',
        'model_id': 'meta-llama/llama-3.3-70b-instruct:free',
    },
}


@dataclass
class AIConfig:
    provider: str = DEFAULT_PROVIDER
    base_url: str = ''
    api_key: str = ''
    model_id: str = ''
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout: int = 30
    max_rows: int = 50
    daily_cap: int = 30  # per user 0 = unlimited


def load_config(env):
    icp = env['ir.config_parameter'].sudo()

    def get(key, default):
        value = icp.get_str(PARAM_PREFIX + key)
        return value if value else default

    provider = get('provider', DEFAULT_PROVIDER)
    preset = PRESETS.get(provider, {})
    return AIConfig(
        provider=provider,
        base_url=get('base_url', preset.get('base_url', '')),
        api_key=get('api_key', ''),
        model_id=get('model_id', preset.get('model_id', '')),
        temperature=float(get('temperature', 0.0)),
        max_tokens=int(get('max_tokens', 1024)),
        timeout=int(get('timeout', 30)),
        max_rows=int(get('max_rows', 50)),
        daily_cap=int(get('daily_cap', 30)),
    )