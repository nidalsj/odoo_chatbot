from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..services.config import PRESETS, AIConfig, load_config
from ..services.providers import ProviderError, build_provider


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatbot_provider = fields.Selection(
        [
            ('groq', 'Groq'),
            ('gemini', 'Google Gemini'),
            ('openrouter', 'OpenRouter'),
            ('custom', 'Custom (OpenAI-compatible)'),
        ],
        string='AI Provider', default='groq', config_parameter='odoo_chatbot.provider',
    )
    chatbot_base_url = fields.Char(
        string='Base URL', default=PRESETS['groq']['base_url'],
        config_parameter='odoo_chatbot.base_url',
    )
    chatbot_api_key = fields.Char(string='API Key', config_parameter='odoo_chatbot.api_key')
    chatbot_model_id = fields.Char(
        string='Model ID', default=PRESETS['groq']['model_id'],
        config_parameter='odoo_chatbot.model_id',
    )
    chatbot_temperature = fields.Float(
        string='Temperature', default=0.0, config_parameter='odoo_chatbot.temperature',
    )
    chatbot_max_tokens = fields.Integer(
        string='Max Tokens', default=1024, config_parameter='odoo_chatbot.max_tokens',
    )
    chatbot_timeout = fields.Integer(
        string='Timeout (seconds)', default=30, config_parameter='odoo_chatbot.timeout',
    )
    chatbot_max_rows = fields.Integer(
        string='Max Rows Returned', default=50, config_parameter='odoo_chatbot.max_rows',
    )
    chatbot_daily_cap = fields.Integer(
        string='Daily Requests per User', default=30, config_parameter='odoo_chatbot.daily_cap',
        help='Protects your free quota. 0 means unlimited.',
    )

    @api.onchange('chatbot_provider')
    def _onchange_chatbot_provider(self):
        saved = load_config(self.env)
        if self.chatbot_provider == saved.provider:
            self.chatbot_base_url = saved.base_url
            self.chatbot_model_id = saved.model_id
            return
        preset = PRESETS.get(self.chatbot_provider)
        if preset:  # custom has no preset: keep whatever the admin typed
            self.chatbot_base_url = preset['base_url']
            self.chatbot_model_id = preset['model_id']

    @api.constrains(
        'chatbot_temperature', 'chatbot_max_tokens', 'chatbot_timeout',
        'chatbot_max_rows', 'chatbot_daily_cap',
    )
    def _check_chatbot_limits(self):
        for rec in self:
            if not 0.0 <= rec.chatbot_temperature <= 2.0:
                raise ValidationError('Temperature must be between 0 and 2.')
            if not 16 <= rec.chatbot_max_tokens <= 8192:
                raise ValidationError('Max Tokens must be between 16 and 8192.')
            if not 5 <= rec.chatbot_timeout <= 120:
                raise ValidationError('Timeout must be between 5 and 120 seconds.')
            if not 1 <= rec.chatbot_max_rows <= 200:
                raise ValidationError('Max Rows must be between 1 and 200.')
            if rec.chatbot_daily_cap < 0:
                raise ValidationError('Daily Requests cannot be negative.')

    def action_chatbot_test_connection(self):
        """Tests the values currently in the form and not the saved ones"""
        self.ensure_one()
        config = AIConfig(
            provider=self.chatbot_provider,
            base_url=self.chatbot_base_url or '',
            api_key=self.chatbot_api_key or '',
            model_id=self.chatbot_model_id or '',
            timeout=self.chatbot_timeout or 30,
        )
        try:
            latency_ms = build_provider(config).test()
        except ProviderError as exc:
            raise ValidationError(f'Connection failed: {exc.message}') from exc
        return {
            'effect': {
                'fadeout': 'slow',
                'message': f'Connection successful: {config.model_id} answered in {latency_ms} ms.',
                'type': 'rainbow_man',
            }
        }