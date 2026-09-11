"""``CSVAmazonOrderSource`` parsing (no DB access needed)."""

import io
from decimal import Decimal

from django.test import SimpleTestCase

from apps.integrations.amazon.sources import (
    AmazonOrderRow,
    AmazonOrderRowError,
    CSVAmazonOrderSource,
)

HEADER = (
    "order_id,order_date,order_status,amazon_sku,quantity,selling_price,gst_amount,"
    "referral_fee,closing_fee,fulfillment_fee,shipping_cost,advertising_cost,other_charges,"
    "refund_amount"
)


def _source(csv_text: str) -> list:
    return list(CSVAmazonOrderSource(io.StringIO(csv_text)).rows())


class CSVAmazonOrderSourceTests(SimpleTestCase):
    def test_parses_a_full_row(self):
        csv_text = (
            HEADER + "\n"
            "AMZ-1,2026-01-10,Shipped,HEX-MP-A-001,2,1180.00,180.00,"
            "150.00,20.00,80.00,80.00,50.00,10.00,0.00\n"
        )
        [row] = _source(csv_text)
        self.assertIsInstance(row, AmazonOrderRow)
        self.assertEqual(row.order_id, "AMZ-1")
        self.assertEqual(row.quantity, 2)
        self.assertEqual(row.selling_price, Decimal("1180.00"))
        self.assertEqual(row.referral_fee, Decimal("150.00"))

    def test_blank_fee_columns_parse_as_none(self):
        csv_text = (
            HEADER + "\n"
            "AMZ-1,2026-01-10,Shipped,HEX-MP-A-001,1,1180.00,180.00,,,,,,,0.00\n"
        )
        [row] = _source(csv_text)
        self.assertIsNone(row.referral_fee)
        self.assertIsNone(row.shipping_cost)

    def test_missing_required_column_is_a_file_level_error(self):
        [entry] = _source("order_id,order_date\nAMZ-1,2026-01-10\n")
        self.assertIsInstance(entry, AmazonOrderRowError)
        self.assertEqual(entry.row_number, 0)
        self.assertIn("Missing required column", entry.message)

    def test_bad_date_is_a_row_level_error(self):
        csv_text = (
            HEADER + "\n"
            "AMZ-1,10-01-2026,Shipped,HEX-MP-A-001,1,1180.00,180.00,,,,,,,0.00\n"
        )
        [entry] = _source(csv_text)
        self.assertIsInstance(entry, AmazonOrderRowError)
        self.assertEqual(entry.row_number, 2)
        self.assertIn("order_date", entry.message)

    def test_one_bad_row_does_not_stop_the_rest(self):
        csv_text = (
            HEADER + "\n"
            "AMZ-1,not-a-date,Shipped,HEX-MP-A-001,1,1180.00,180.00,,,,,,,0.00\n"
            "AMZ-2,2026-01-10,Shipped,HEX-MP-A-001,1,1180.00,180.00,,,,,,,0.00\n"
        )
        entries = _source(csv_text)
        self.assertIsInstance(entries[0], AmazonOrderRowError)
        self.assertIsInstance(entries[1], AmazonOrderRow)
        self.assertEqual(entries[1].order_id, "AMZ-2")
