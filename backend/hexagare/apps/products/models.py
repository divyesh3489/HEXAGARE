"""Catalog domain models: ``Category`` -> ``Product`` -> ``ProductVariant``.

Per ADR-002, **SKU and pricing are plain columns on ``ProductVariant``**, not
standalone entities. Variant properties (size / colour / material / anything) are
data rows via ``ProductAttribute`` / ``ProductAttributeValue`` -- never
product-specific columns (ADR-004). Serialized units, barcodes and bulk
generation are built in later phases and live alongside these models.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify

_MONEY = Decimal("0.01")
_HUNDRED = Decimal("100")
_ZERO = Decimal("0.00")

#: Price columns that live on both ``Product`` (as an optional default) and
#: ``ProductVariant`` (nullable -- ``NULL`` means "inherit the product's value").
PRICE_FIELDS = ("mrp", "selling_price", "purchase_price", "tax_rate")


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _discount_amount(mrp, selling_price) -> Decimal:
    """Money off the MRP (never negative). ``0`` if either input is missing."""
    if mrp is None or selling_price is None:
        return _ZERO
    return _quantize(max(Decimal(mrp) - Decimal(selling_price), _ZERO))


def _discount_percent(mrp, selling_price) -> Decimal:
    """``discount_amount`` as a percentage of MRP. ``0`` if MRP is missing/zero."""
    if not mrp:
        return _ZERO
    return _quantize(_discount_amount(mrp, selling_price) / Decimal(mrp) * _HUNDRED)


class TimestampedModel(models.Model):
    """Adds ``created_at`` / ``updated_at`` to a model."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimestampedModel):
    """A node in the product category tree.

    ``code`` is a short token (e.g. ``MP``) used by the SKU suggestion service
    (see ``apps.products.services.sku``). The tree is self-referential; deleting
    a parent is blocked while children exist.
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    code = models.CharField(
        max_length=12,
        blank=True,
        help_text="Short token used when suggesting SKUs, e.g. 'MP'.",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class Product(TimestampedModel):
    """A sellable product.

    Carries **optional default pricing** (``mrp`` / ``selling_price`` /
    ``purchase_price`` / ``tax_rate``); each ``ProductVariant`` inherits these
    unless it sets its own value (see ADR-005). ``discount`` is always derived
    from MRP and selling price, never stored. SKU stays on the variant (ADR-002).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        DRAFT = "draft", "Draft"
        DISCONTINUED = "discontinued", "Discontinued"

    name = models.CharField(max_length=200)
    code = models.CharField(
        max_length=16,
        blank=True,
        help_text="Short token used when suggesting SKUs, e.g. 'MP'.",
    )
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    hsn_sac = models.CharField("HSN / SAC", max_length=16, blank=True)
    weight = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Weight in kilograms.",
    )
    dimensions = models.CharField(
        max_length=120,
        blank=True,
        help_text="Free-form, e.g. '30 x 25 x 4 cm'.",
    )
    tags = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    # -- default pricing (optional; variants inherit unless they override) ----
    mrp = models.DecimalField(
        "default MRP",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    selling_price = models.DecimalField(
        "default selling price (GST inclusive)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    purchase_price = models.DecimalField(
        "default purchase price",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    tax_rate = models.DecimalField(
        "default GST rate (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def discount_amount(self) -> Decimal:
        """Derived: ``mrp - selling_price`` (never negative), from this product's
        own defaults. ``0`` unless both defaults are set."""
        return _discount_amount(self.mrp, self.selling_price)

    @property
    def discount_percent(self) -> Decimal:
        return _discount_percent(self.mrp, self.selling_price)


class ProductVariant(TimestampedModel):
    """A specific, sellable variation of a product.

    ``sku`` is a globally unique column (ADR-002); it is auto-suggested on
    create but may be edited freely.

    The four price columns are **nullable overrides** (ADR-005): ``NULL`` means
    "inherit the product's default"; a value overrides it for this variant. Read
    the resolved figures via ``effective_*``. ``selling_price`` is
    **GST-inclusive** -- the taxable base, GST amount and discount are all
    derived from the effective values (see section 5 of ``HEXAGARE_FEATURES.md``).
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display label, e.g. '11 x 23 inch'. Optional.",
    )
    code = models.CharField(
        max_length=24,
        blank=True,
        help_text="Short token used when suggesting the SKU, e.g. '11X23'.",
    )
    sku = models.CharField(max_length=64, unique=True, db_index=True)
    barcode = models.CharField(
        max_length=64,
        blank=True,
        help_text="Optional variant-level barcode value (per-unit barcodes come later).",
    )
    mrp = models.DecimalField(
        "MRP override",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Blank inherits the product's default MRP.",
    )
    selling_price = models.DecimalField(
        "selling price override (GST inclusive)",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Blank inherits the product's default selling price.",
    )
    purchase_price = models.DecimalField(
        "purchase price override",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Blank inherits the product's default purchase price.",
    )
    tax_rate = models.DecimalField(
        "GST rate override (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Blank inherits the product's default GST rate.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product__name", "name", "sku"]

    def __str__(self) -> str:
        return self.sku

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    # -- resolved pricing (variant override -> product default -> 0) ---------
    def _resolved_price(self, field: str) -> Decimal | None:
        own = getattr(self, field)
        if own is not None:
            return own
        return getattr(self.product, field, None)

    @property
    def effective_mrp(self) -> Decimal:
        return self._resolved_price("mrp") or _ZERO

    @property
    def effective_selling_price(self) -> Decimal:
        return self._resolved_price("selling_price") or _ZERO

    @property
    def effective_purchase_price(self) -> Decimal:
        return self._resolved_price("purchase_price") or _ZERO

    @property
    def effective_tax_rate(self) -> Decimal:
        return self._resolved_price("tax_rate") or _ZERO

    @property
    def base_price(self) -> Decimal:
        """Taxable value: ``effective_selling_price / (1 + effective_tax_rate / 100)`` (2 dp)."""
        divisor = Decimal("1") + (self.effective_tax_rate / _HUNDRED)
        if divisor == 0:
            return _quantize(self.effective_selling_price)
        return _quantize(self.effective_selling_price / divisor)

    @property
    def gst_amount(self) -> Decimal:
        """GST portion of the GST-inclusive effective selling price (2 dp)."""
        return _quantize(self.effective_selling_price - self.base_price)

    @property
    def cgst_amount(self) -> Decimal:
        """Central GST for an intra-state sale -- half of ``gst_amount``."""
        return _quantize(self.gst_amount / Decimal("2"))

    @property
    def sgst_amount(self) -> Decimal:
        """State GST for an intra-state sale -- the balance of ``gst_amount``."""
        return _quantize(self.gst_amount - self.cgst_amount)

    @property
    def discount_amount(self) -> Decimal:
        """Derived: ``effective_mrp - effective_selling_price`` (never negative)."""
        return _discount_amount(self.effective_mrp, self.effective_selling_price)

    @property
    def discount_percent(self) -> Decimal:
        return _discount_percent(self.effective_mrp, self.effective_selling_price)

    # -- availability follows the product's status (ADR-006) ---------------
    @property
    def effective_status(self) -> str:
        """The status shown to the world -- a value of :class:`Product.Status`.

        The variant's own ``is_active`` only matters while the **product** is
        active; a draft / inactive / discontinued product overrides it.
        """
        if self.product.status == Product.Status.ACTIVE:
            return Product.Status.ACTIVE if self.is_active else Product.Status.INACTIVE
        return self.product.status

    @property
    def is_available(self) -> bool:
        """Sellable right now: the product is active *and* this variant is active."""
        return self.product.status == Product.Status.ACTIVE and self.is_active


class ProductAttribute(models.Model):
    """A reusable variant property definition (Size, Colour, Material, ...).

    The set of attributes is global and data-driven -- adding "Finish" is a row,
    not a migration.
    """

    name = models.CharField(max_length=60, unique=True)
    code = models.SlugField(max_length=40, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ProductAttributeValue(models.Model):
    """The value a given ``ProductVariant`` carries for one ``ProductAttribute``."""

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="attribute_values",
    )
    attribute = models.ForeignKey(
        ProductAttribute,
        on_delete=models.PROTECT,
        related_name="values",
    )
    value = models.CharField(max_length=120)

    class Meta:
        ordering = ["attribute__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "attribute"],
                name="uniq_attribute_per_variant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attribute.name}: {self.value}"


class ProductImage(TimestampedModel):
    """An image for a product, optionally scoped to a single variant.

    Files go through ``STORAGES["default"]`` -- S3 in staging/production, the
    local media volume in development. Only the object key is stored in Postgres.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/images/")
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"Image #{self.pk} for {self.product.name}"


class LabelSize(TimestampedModel):
    """A physical label / sheet geometry, used by the Phase 5 label-PDF renderer."""

    class Orientation(models.TextChoices):
        HORIZONTAL = "horizontal", "Horizontal"
        VERTICAL = "vertical", "Vertical"

    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=40, unique=True)
    width_mm = models.DecimalField(max_digits=7, decimal_places=2)
    height_mm = models.DecimalField(max_digits=7, decimal_places=2)
    columns = models.PositiveSmallIntegerField(default=1)
    rows = models.PositiveSmallIntegerField(default=1)
    margin_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    gutter_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    orientation = models.CharField(
        max_length=12,
        choices=Orientation.choices,
        default=Orientation.HORIZONTAL,
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
