from odoo.tests import tagged
from odoo.tests.common import BaseCase

from ..services.prompt_builder import select_schema

SCHEMA = {
    name: {'label': label} for name, label in [
        ('sale.order', 'Sales Orders'), ('purchase.order', 'Purchase Orders'),
        ('account.move', 'Invoices and Journal Entries'), ('res.partner', 'Contacts'),
        ('product.product', 'Products'), ('pos.order', 'POS Orders'), ('crm.lead', 'CRM Leads'),
    ]
}


@tagged('standard', 'at_install')
class TestSelectSchema(BaseCase):

    def pick(self, question):
        return list(select_schema(question, SCHEMA))

    def test_single_topics(self):
        self.assertEqual(self.pick('top 10 sales orders this month'), ['sale.order'])
        self.assertEqual(self.pick('list all purchase orders from last week'), ['purchase.order'])
        self.assertEqual(self.pick('show invoices above 1000 for April'), ['account.move'])
        self.assertEqual(self.pick('how many contacts per country?'), ['res.partner'])

    def test_multiple_topics(self):
        picked = self.pick('customers with invoices above 1000')
        self.assertEqual(set(picked), {'res.partner', 'account.move'})

    def test_no_match_keeps_everything(self):
        self.assertEqual(set(self.pick('hello there')), set(SCHEMA))