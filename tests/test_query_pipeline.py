import json

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..services.config import load_config
from ..services.errors import QueryError
from ..services.pipeline import answer_question


class FakeProvider:
    def __init__(self, spec):
        self.reply = spec if isinstance(spec, str) else json.dumps(spec)

    def complete(self, system_prompt, user_message, json_mode=False):
        return self.reply


@tagged('standard', 'at_install')
class TestQueryPipeline(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.partner'].create([
            {'name': 'ZZ Chat Alpha', 'city': 'Delhi', 'autopost_bills': 'never'},
            {'name': 'ZZ Chat Beta', 'city': 'Mumbai', 'autopost_bills': 'never'},
            {'name': 'ZZ Chat Gamma', 'city': 'Bangalore', 'autopost_bills': 'never'},
        ])

    def ask(self, spec, env=None):
        return answer_question(env or self.env, 'test', provider=FakeProvider(spec))['result']

    def test_list_with_filter_order_and_limit(self):
        result = self.ask({
            'intent': 'list', 'model': 'res.partner',
            'filters': [{'field': 'name', 'op': 'ilike', 'value': 'ZZ Chat'}],
            'fields': ['name', 'city'],
            'order': [{'field': 'name', 'direction': 'asc'}], 'limit': 2,
        })
        self.assertEqual(result['type'], 'table')
        self.assertEqual([c['name'] for c in result['columns']], ['name', 'city'])
        self.assertEqual(result['rows'], [['ZZ Chat Alpha', 'Delhi'], ['ZZ Chat Beta', 'Mumbai']])
        self.assertEqual(result['total'], 3)
        self.assertTrue(result['truncated'])

    def test_count_with_period(self):
        result = self.ask({
            'intent': 'count', 'model': 'res.partner',
            'filters': [{'field': 'create_date', 'period': 'today'},
                        {'field': 'name', 'op': 'ilike', 'value': 'ZZ Chat'}],
        })
        self.assertEqual(result['rows'], [['3']])

    def test_aggregate_group_by(self):
        result = self.ask({
            'intent': 'aggregate', 'model': 'res.partner',
            'filters': [{'field': 'name', 'op': 'ilike', 'value': 'ZZ Chat'}],
            'groupby': ['city'], 'aggregates': [{'func': 'count'}],
            'order': [{'field': 'count', 'direction': 'desc'}],
        })
        self.assertEqual(result['rows'], [['Mumbai', '2'], ['Delhi', '1']])
        self.assertEqual([c['label'] for c in result['columns']], ['City', 'Count'])

    def test_limit_is_clamped(self):
        result = self.ask({'intent': 'list', 'model': 'res.partner', 'limit': 100000})
        self.assertLessEqual(len(result['rows']), load_config(self.env).max_rows)

    def test_clarify_and_unsupported_are_messages(self):
        for intent in ('clarify', 'unsupported'):
            result = self.ask({'intent': intent, 'message': 'Which customer?'})
            self.assertEqual(result, {'type': 'message', 'text': 'Which customer?'})

    def test_bad_specs_are_rejected(self):
        bad_specs = [
            {'intent': 'list', 'model': 'res.partner', 'filters': [{'field': 'nonexistent', 'op': '=', 'value': 1}]},
            {'intent': 'list', 'model': 'res.users'},
            {'intent': 'list', 'model': 'ir.config_parameter'},
            {'intent': 'list', 'model': 'res.partner', 'filters': [{'field': 'name', 'op': '; DROP TABLE', 'value': 'x'}]},
            {'intent': 'list', 'model': 'res.partner', 'filters': [{'field': 'type', 'op': '=', 'value': 'banana'}]},
            {'intent': 'explode'},
            'not even json {',
        ]
        for spec in bad_specs:
            with self.subTest(spec=spec), self.assertRaises(Exception) as ctx:
                self.ask(spec)
            self.assertTrue(hasattr(ctx.exception, 'message'))  # QueryError or ProviderError

    def test_user_without_sales_rights_cannot_query_orders(self):
        user = self.env['res.users'].create({
            'name': 'Plain', 'login': 'zz_plain',
            'group_ids': [Command.set([self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(QueryError):
            self.ask({'intent': 'list', 'model': 'sale.order'}, env=self.env(user=user))