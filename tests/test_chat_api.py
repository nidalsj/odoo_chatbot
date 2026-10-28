from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..services.config import AIConfig
from ..services.errors import QueryError
from ..services.providers import ProviderError

MODULE = 'odoo.addons.odoo_chatbot.models.chatbot_conversation'
RESULT = {
    'type': 'table', 'title': 'Contacts', 'summary': '3 contacts found.',
    'columns': [], 'rows': [], 'total': 3, 'truncated': False,
}


@tagged('standard', 'at_install')
class TestChatApi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref('base.group_user')

        def make(login):
            return cls.env['res.users'].create({
                'name': login, 'login': login, 'group_ids': [Command.set([group.id])],
            })
        cls.u1, cls.u2 = make('zz_chat_u1'), make('zz_chat_u2')

    def send(self, user, conversation_id, text, error=None):
        Conv = self.env['chatbot.conversation'].with_user(user)
        with patch(f'{MODULE}.answer_question') as mocked:
            if error:
                mocked.side_effect = error
            else:
                mocked.return_value = {'spec': {'intent': 'list'}, 'result': RESULT}
            return Conv.send_message(conversation_id, text)

    def test_first_message_creates_conversation_and_title(self):
        out = self.send(self.u1, False, 'show me contacts created this month')
        self.assertEqual([m['role'] for m in out['messages']], ['user', 'bot'])
        self.assertEqual(out['messages'][1]['text'], '3 contacts found.')
        self.assertEqual(out['conversation']['name'], 'show me contacts created this month')
        self.assertEqual(out['conversation']['bucket'], 'today')

        conv_id = out['conversation']['id']
        second = self.send(self.u1, conv_id, 'and another one')
        self.assertEqual(second['conversation']['name'], out['conversation']['name'])
        Conv = self.env['chatbot.conversation'].with_user(self.u1)
        self.assertEqual(len(Conv.get_messages(conv_id)), 4)

    def test_long_title_is_shortened(self):
        out = self.send(self.u1, False, 'x' * 120)
        self.assertLessEqual(len(out['conversation']['name']), 50)

    def test_conversations_are_private(self):
        out = self.send(self.u1, False, 'hello there')
        conv_id = out['conversation']['id']
        Conv2 = self.env['chatbot.conversation'].with_user(self.u2)
        self.assertEqual(Conv2.get_conversations(), [])
        with self.assertRaises(AccessError):
            Conv2.get_messages(conv_id)
        with self.assertRaises(AccessError):
            self.send(self.u2, conv_id, 'sneaky')

    def test_invalid_input(self):
        Conv = self.env['chatbot.conversation'].with_user(self.u1)
        for bad in ('', '   ', None, 'x' * 5000):
            with self.assertRaises(UserError):
                Conv.send_message(False, bad)
        with self.assertRaises(UserError):
            Conv.send_message('1; DROP TABLE', 'hi')

    def test_daily_cap(self):
        with patch(f'{MODULE}.load_config', return_value=AIConfig(daily_cap=1)):
            self.send(self.u1, False, 'first question')
            with self.assertRaises(UserError):
                self.send(self.u1, False, 'second question')
            self.send(self.u2, False, 'other user is unaffected')

    def test_provider_error_is_friendly_and_saved(self):
        out = self.send(self.u1, False, 'anything', error=ProviderError('rate_limited', 'raw provider detail'))
        bot = out['messages'][1]
        self.assertEqual(bot['status'], 'error')
        self.assertNotIn('raw provider detail', bot['text'])
        saved = self.env['chatbot.message'].sudo().browse(bot['id'])
        self.assertIn('raw provider detail', saved.error_message)

    def test_query_error_message_is_shown(self):
        out = self.send(self.u1, False, 'anything', error=QueryError('I cannot filter by x.'))
        self.assertEqual(out['messages'][1]['text'], 'I cannot filter by x.')
        self.assertEqual(out['messages'][1]['status'], 'error')

    def test_unexpected_error_is_generic(self):
        out = self.send(self.u1, False, 'anything', error=RuntimeError('boom internal'))
        self.assertEqual(out['messages'][1]['status'], 'error')
        self.assertNotIn('boom', out['messages'][1]['text'])