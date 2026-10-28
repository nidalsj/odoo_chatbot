from datetime import date

from odoo.tests import tagged
from odoo.tests.common import BaseCase

from ..services.date_resolver import resolve_between, resolve_period
from ..services.errors import QueryError


@tagged('standard', 'at_install')
class TestDateResolver(BaseCase):
    TODAY = date(2026, 10, 28)  # a Wednesday

    def test_days_and_weeks(self):
        self.assertEqual(resolve_period('today', self.TODAY), (date(2026, 10, 28), date(2026, 10, 29)))
        self.assertEqual(resolve_period('yesterday', self.TODAY), (date(2026, 10, 27), date(2026, 10, 28)))
        self.assertEqual(resolve_period('this_week', self.TODAY), (date(2026, 10, 26), date(2026, 11, 2)))
        self.assertEqual(resolve_period('last_week', self.TODAY), (date(2026, 10, 19), date(2026, 10, 26)))
        self.assertEqual(resolve_period('last_7_days', self.TODAY), (date(2026, 10, 22), date(2026, 10, 29)))

    def test_months_quarters_years(self):
        self.assertEqual(resolve_period('this_month', self.TODAY), (date(2026, 10, 1), date(2026, 11, 1)))
        self.assertEqual(resolve_period('last_month', self.TODAY), (date(2026, 9, 1), date(2026, 10, 1)))
        self.assertEqual(resolve_period('this_quarter', self.TODAY), (date(2026, 10, 1), date(2027, 1, 1)))
        self.assertEqual(resolve_period('last_quarter', self.TODAY), (date(2026, 7, 1), date(2026, 10, 1)))
        self.assertEqual(resolve_period('last_year', self.TODAY), (date(2025, 1, 1), date(2026, 1, 1)))

    def test_year_boundaries(self):
        self.assertEqual(resolve_period('this_month', date(2026, 12, 15)), (date(2026, 12, 1), date(2027, 1, 1)))
        self.assertEqual(resolve_period('last_month', date(2027, 1, 10)), (date(2026, 12, 1), date(2027, 1, 1)))

    def test_explicit_values(self):
        self.assertEqual(resolve_period('2026-04', self.TODAY), (date(2026, 4, 1), date(2026, 5, 1)))
        self.assertEqual(resolve_period('2026', self.TODAY), (date(2026, 1, 1), date(2027, 1, 1)))
        self.assertEqual(resolve_period('2026-04-10', self.TODAY), (date(2026, 4, 10), date(2026, 4, 11)))
        self.assertEqual(resolve_between('2026-04-01', '2026-04-30'), (date(2026, 4, 1), date(2026, 5, 1)))

    def test_invalid_input(self):
        for bad in ('next_decade', '2026-13', 'banana'):
            with self.assertRaises(QueryError):
                resolve_period(bad, self.TODAY)
        with self.assertRaises(QueryError):
            resolve_between('2026-04-30', '2026-04-01')