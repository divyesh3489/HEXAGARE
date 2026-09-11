"""``resolve_fee`` -- the configured-fee fallback (section 22)."""

import datetime
from decimal import Decimal

from django.test import TestCase

from apps.integrations.amazon.models import AmazonFeeConfig
from apps.integrations.amazon.services.fees import resolve_fee
from apps.products.models import Category, Product
from apps.sales.models import SalesChannel


class ResolveFeeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.channel = SalesChannel.objects.get(code="AMAZON")
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad", category=cls.category, status=Product.Status.ACTIVE
        )
        cls.other_product = Product.objects.create(
            name="Other", category=cls.category, status=Product.Status.ACTIVE
        )

    def test_no_config_returns_zero(self):
        fee = resolve_fee(
            AmazonFeeConfig.FeeName.REFERRAL,
            sales_channel_id=self.channel.pk,
            product=self.product,
            order_date=datetime.date(2026, 1, 1),
            taxable_value=Decimal("1000.00"),
        )
        self.assertEqual(fee, Decimal("0.00"))

    def test_percentage_fee_computed_against_taxable_value(self):
        AmazonFeeConfig.objects.create(
            fee_name=AmazonFeeConfig.FeeName.REFERRAL,
            fee_type=AmazonFeeConfig.FeeType.PERCENTAGE,
            value=Decimal("15.00"),
            sales_channel=self.channel,
            effective_from=datetime.date(2025, 1, 1),
        )
        fee = resolve_fee(
            AmazonFeeConfig.FeeName.REFERRAL,
            sales_channel_id=self.channel.pk,
            product=self.product,
            order_date=datetime.date(2026, 1, 1),
            taxable_value=Decimal("1000.00"),
        )
        self.assertEqual(fee, Decimal("150.00"))

    def test_product_specific_config_wins_over_category_and_global(self):
        AmazonFeeConfig.objects.create(
            fee_name=AmazonFeeConfig.FeeName.CLOSING,
            fee_type=AmazonFeeConfig.FeeType.FIXED,
            value=Decimal("10.00"),
            sales_channel=self.channel,
            effective_from=datetime.date(2025, 1, 1),
        )
        AmazonFeeConfig.objects.create(
            fee_name=AmazonFeeConfig.FeeName.CLOSING,
            fee_type=AmazonFeeConfig.FeeType.FIXED,
            value=Decimal("20.00"),
            sales_channel=self.channel,
            applicable_category=self.category,
            effective_from=datetime.date(2025, 1, 1),
        )
        AmazonFeeConfig.objects.create(
            fee_name=AmazonFeeConfig.FeeName.CLOSING,
            fee_type=AmazonFeeConfig.FeeType.FIXED,
            value=Decimal("30.00"),
            sales_channel=self.channel,
            applicable_product=self.product,
            effective_from=datetime.date(2025, 1, 1),
        )
        fee = resolve_fee(
            AmazonFeeConfig.FeeName.CLOSING,
            sales_channel_id=self.channel.pk,
            product=self.product,
            order_date=datetime.date(2026, 1, 1),
            taxable_value=Decimal("1000.00"),
        )
        self.assertEqual(fee, Decimal("30.00"))

        # A different product in the same category falls through to the
        # category-level config, not the product-specific one above.
        other_fee = resolve_fee(
            AmazonFeeConfig.FeeName.CLOSING,
            sales_channel_id=self.channel.pk,
            product=self.other_product,
            order_date=datetime.date(2026, 1, 1),
            taxable_value=Decimal("1000.00"),
        )
        self.assertEqual(other_fee, Decimal("20.00"))

    def test_outside_effective_date_range_is_ignored(self):
        AmazonFeeConfig.objects.create(
            fee_name=AmazonFeeConfig.FeeName.SHIPPING,
            fee_type=AmazonFeeConfig.FeeType.FIXED,
            value=Decimal("80.00"),
            sales_channel=self.channel,
            effective_from=datetime.date(2025, 1, 1),
            effective_to=datetime.date(2025, 12, 31),
        )
        fee = resolve_fee(
            AmazonFeeConfig.FeeName.SHIPPING,
            sales_channel_id=self.channel.pk,
            product=self.product,
            order_date=datetime.date(2026, 1, 1),
            taxable_value=Decimal("1000.00"),
        )
        self.assertEqual(fee, Decimal("0.00"))
