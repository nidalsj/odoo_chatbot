import logging
from datetime import timezone

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.config import load_config
from ..services.date_resolver import to_utc_naive, user_tz
from ..services.errors import QueryError
from ..services.pipeline import MAX_QUESTION_CHARS, answer_question
from ..services.providers import ProviderError

_logger = logging.getLogger(__name__)

DEFAULT_TITLE = 'New chat'
MAX_TITLE_CHARS = 50
MAX_CONVERSATIONS_LISTED = 200

BUSY = 'The AI service is busy right now (free-tier limit). Please wait a minute and try again.'
UNAVAILABLE = "The AI service didn't respond. Please try again in a moment."
MISCONFIGURED = "The AI engine isn't set up correctly. Please ask your administrator to check the chatbot settings."
UNUSABLE = "The AI gave an answer I couldn't use. Please try rephrasing your question."
GENERIC = 'Something went wrong while answering. Please try again.'
PROVIDER_MESSAGES = {
    'rate_limited': BUSY,
    'timeout': UNAVAILABLE, 'unreachable': UNAVAILABLE, 'server_error': UNAVAILABLE,
    'bad_response': UNUSABLE,
    'invalid_key': MISCONFIGURED, 'unknown_model': MISCONFIGURED, 'missing_config': MISCONFIGURED,
    'insufficient_credits': MISCONFIGURED, 'bad_request': MISCONFIGURED, 'http_error': MISCONFIGURED,
}


class ChatbotConversation(models.Model):
    _name = 'chatbot.conversation'
    _description = 'Chatbot Conversation'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Title', required=True, default=DEFAULT_TITLE)
    user_id = fields.Many2one(
        'res.users', string='Owner', required=True, index=True,
        default=lambda self: self.env.user, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company, ondelete='cascade',
    )
    message_ids = fields.One2many('chatbot.message', 'conversation_id', string='Messages')

    # ---- API called by the web client ---------------------------------------

    @api.model
    def get_conversations(self):
        today = fields.Date.context_today(self.env.user)
        tz = user_tz(self.env)
        return [
            conv._to_client_dict(today, tz)
            for conv in self.search([], limit=MAX_CONVERSATIONS_LISTED)
        ]

    @api.model
    def get_messages(self, conversation_id):
        conv = self._get_own(conversation_id)
        return [message._to_client_dict() for message in conv.message_ids]

    @api.model
    def send_message(self, conversation_id, text):
        text = text.strip() if isinstance(text, str) else ''
        if not text:
            raise UserError('Please type a question.')
        if len(text) > MAX_QUESTION_CHARS:
            raise UserError(f'Please keep questions under {MAX_QUESTION_CHARS} characters.')
        self._check_daily_cap()

        conv = self._get_own(conversation_id) if conversation_id else self.create({})
        Message = self.env['chatbot.message'].sudo()
        user_message = Message.create({'conversation_id': conv.id, 'role': 'user', 'text': text})
        bot_message = Message.create({'conversation_id': conv.id, 'role': 'bot', **self._run_pipeline(text)})
        if conv.name == DEFAULT_TITLE:
            conv.sudo().write({'name': self._make_title(text)})

        today = fields.Date.context_today(self.env.user)
        return {
            'conversation': conv._to_client_dict(today, user_tz(self.env)),
            'messages': [user_message._to_client_dict(), bot_message._to_client_dict()],
        }

    # ---- internals ----------------------------------------------------------

    @api.model
    def _get_own(self, conversation_id):
        """The conversation, or an error if it doesn't exist or isn't the
        caller's (the record rules decide)."""
        if isinstance(conversation_id, bool) or not isinstance(conversation_id, int):
            raise UserError('Invalid conversation.')
        conv = self.browse(conversation_id).exists()
        if not conv:
            raise UserError('This conversation no longer exists.')
        conv.check_access('read')
        return conv

    @api.model
    def _check_daily_cap(self):
        cap = load_config(self.env).daily_cap
        if cap <= 0:
            return
        start_of_day = to_utc_naive(fields.Date.context_today(self.env.user), user_tz(self.env))
        used = self.env['chatbot.message'].sudo().search_count([
            ('user_id', '=', self.env.uid),
            ('role', '=', 'user'),
            ('create_date', '>=', start_of_day),
        ])
        if used >= cap:
            raise UserError(f'You have reached your daily limit of {cap} questions. It resets at midnight.')

    @api.model
    def _run_pipeline(self, question):
        """Values for the bot's reply. Never raises for expected failures."""
        try:
            with self.env.cr.savepoint():
                out = answer_question(self.env, question)
        except QueryError as exc:
            return {'text': exc.message, 'status': 'error', 'error_message': exc.message}
        except ProviderError as exc:
            _logger.warning('AI provider error (%s): %s', exc.code, exc.message)
            return {
                'text': PROVIDER_MESSAGES.get(exc.code, UNAVAILABLE),
                'status': 'error', 'error_message': exc.message,
            }
        except Exception:
            _logger.exception('Unexpected chatbot failure')
            return {'text': GENERIC, 'status': 'error', 'error_message': 'Unexpected error, see the server log.'}

        result = out['result']
        text = result['text'] if result['type'] == 'message' else result['summary']
        return {'text': text, 'query_spec': out['spec'], 'result': result, 'status': 'ok'}

    @staticmethod
    def _make_title(text):
        flat = ' '.join(text.split())
        return flat if len(flat) <= MAX_TITLE_CHARS else flat[:MAX_TITLE_CHARS - 1].rstrip() + '…'

    def _to_client_dict(self, today, tz):
        self.ensure_one()
        created = self.create_date
        days = (today - created.replace(tzinfo=timezone.utc).astimezone(tz).date()).days
        if days <= 0:
            bucket = 'today'
        elif days == 1:
            bucket = 'yesterday'
        elif days <= 7:
            bucket = 'previous_7_days'
        else:
            bucket = 'older'
        return {
            'id': self.id,
            'name': self.name,
            'create_date': fields.Datetime.to_string(created),
            'bucket': bucket,
        }