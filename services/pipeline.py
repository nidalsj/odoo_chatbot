from .config import load_config
from .json_utils import extract_json
from .errors import QueryError
from .prompt_builder import build_system_prompt
from .providers import build_provider
from .query_executor import execute
from .query_validator import validate_spec
from .result_formatter import format_result
from .schema import get_schema

MAX_QUESTION_CHARS = 1000


def answer_question(env, question, provider=None):
    """question -> {'spec': <raw LLM JSON>, 'result': <JSON-safe dict>}.
    Raises ProviderError (AI side) or QueryError (question/query side)"""
    question = (question or '').strip()
    if not question:
        raise QueryError('Please type a question.')
    if len(question) > MAX_QUESTION_CHARS:
        raise QueryError(f'Please keep questions under {MAX_QUESTION_CHARS} characters.')

    config = load_config(env)
    schema = get_schema(env)
    if not schema:
        raise QueryError('There is no data available to you through the chatbot yet.')

    prompt = build_system_prompt(env, schema, config.max_rows)
    provider = provider or build_provider(config)
    spec = extract_json(provider.complete(prompt, question, json_mode=True))

    vq = validate_spec(env, spec, schema, config.max_rows)
    if vq.intent == 'message':
        result = {'type': 'message', 'text': vq.message}
    else:
        result = format_result(env, vq, execute(env, vq), schema)
    return {'spec': spec, 'result': result}