import logging
import time
import requests

from .base import ProviderError, BaseProvider
_logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseProvider):
    """Works with any server that implements /chat/completions
    (groq/openrouter/gemini compatibility endpoint and others)"""

    def _validate(self):
        c = self.config
        if not (c.base_url or '').lower().startswith(('http://', 'https://')):
            raise ProviderError('missing_config', 'Base URL must start with http:// or https://')
        if not c.model_id:
            raise ProviderError('missing_config', 'Model ID is empty.')
        if not c.api_key:
            raise ProviderError('missing_config', 'API key is empty.')

    def _post(self, payload):
        url = self.config.base_url.rstrip('/') + '/chat/completions'
        headers = {
            'Authorization': f'Bearer {self.config.api_key}',
            'Content-Type': 'application/json',
        }
        try:
            resp = requests.post(
                url, json=payload, headers=headers, timeout=(5, self.config.timeout),
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderError(
                'timeout', f'No response within {self.config.timeout} seconds.'
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderError(
                'unreachable',
                'Could not reach the server. Check the Base URL and your internet connection.',
            ) from exc

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise ProviderError(
                    'bad_response', 'The server returned a non-JSON answer. Check the Base URL.'
                ) from exc
        raise self._http_error(resp)

    @staticmethod
    def _detail(resp):
        try:
            body = resp.json()
        except ValueError:
            return (resp.text or '')[:200]
        if isinstance(body, list) and body:  # Gemini sometimes wraps errors in a list
            body = body[0]
        err = body.get('error', body) if isinstance(body, dict) else body
        if isinstance(err, dict):
            err = err.get('message') or err
        return str(err)[:200]

    def _http_error(self, resp):
        status, detail = resp.status_code, self._detail(resp)
        _logger.warning('AI provider returned HTTP %s: %s', status, detail)  # never log the key
        if status in (401, 403):
            return ProviderError('invalid_key', f'Authentication failed (HTTP {status}). Check the API key. Provider says: {detail}')
        if status == 402:
            return ProviderError('insufficient_credits', f'The provider reports insufficient credits or balance. Provider says: {detail}')
        if status == 404:
            return ProviderError('unknown_model', f"Model '{self.config.model_id}' or the endpoint was not found. Check the Model ID and Base URL. Provider says: {detail}")
        if status == 429:
            retry = resp.headers.get('Retry-After')
            wait = f' Retry after {retry}s.' if retry else ''
            return ProviderError('rate_limited', f'Rate limit or free quota reached.{wait} Provider says: {detail}')
        if status == 400:
            return ProviderError('bad_request', f'The provider rejected the request (HTTP 400): {detail}')
        if status >= 500:
            return ProviderError('server_error', f'The provider had an internal error (HTTP {status}). Try again later.')
        return ProviderError('http_error', f'Unexpected response (HTTP {status}): {detail}')

    def complete(self, system_prompt, user_message, json_mode=False):
        self._validate()
        c = self.config
        payload = {
            'model': c.model_id,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message},
            ],
            'temperature': c.temperature,
            'max_tokens': c.max_tokens,
        }
        if json_mode:
            payload['response_format'] = {'type': 'json_object'}
        try:
            data = self._post(payload)
        except ProviderError as exc:
            # Some free models reject response_format: retry once without it.
            if json_mode and exc.code == 'bad_request':
                payload.pop('response_format')
                data = self._post(payload)
            else:
                raise
        try:
            text = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError('bad_response', 'Unexpected response format from the provider.') from exc
        if not text or not str(text).strip():
            raise ProviderError('bad_response', 'The model returned an empty answer.')
        return text

    def test(self):
        self._validate()
        payload = {
            'model': self.config.model_id,
            'messages': [{'role': 'user', 'content': 'Reply with the single word: OK'}],
            'max_tokens': 16,
            'temperature': 0,
        }
        start = time.monotonic()
        data = self._post(payload)
        if not isinstance(data, dict) or 'choices' not in data:
            raise ProviderError('bad_response', 'Unexpected response format from the provider.')
        return int((time.monotonic() - start) * 1000)