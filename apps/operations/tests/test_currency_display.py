from decimal import Decimal
from django.test import SimpleTestCase
from django.template import Template, Context
from apps.operations.templatetags.currency import cop

class CurrencyDisplayTests(SimpleTestCase):
    def test_colombian_grouping_and_precision(self):
        self.assertEqual(cop(Decimal('1250000')), '$ 1.250.000,00')
        self.assertEqual(cop(Decimal('1500.25')), '$ 1.500,25')
        self.assertEqual(cop(Decimal('-1234.565')), '$ -1.234,57')
        self.assertEqual(cop(0), '$ 0,00')
    def test_missing_price_is_not_zero(self):
        self.assertEqual(cop(None), 'Pendiente')
        self.assertEqual(cop('Pendiente de valoración'), 'Pendiente de valoración')
        self.assertEqual(cop('NaN'), 'Pendiente')
    def test_template_escapes_unknown_labels(self):
        rendered=Template('{% load currency %}{{ value|cop }}').render(Context({'value':'<script>x</script>'}))
        self.assertNotIn('<script>',rendered)
