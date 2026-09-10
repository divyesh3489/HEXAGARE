"""Catalog domain models: ``Category`` -> ``Product`` -> ``ProductVariant``.

Per ADR-002, **SKU and pricing are plain columns on ``ProductVariant``**, not
standalone entities. Variant properties (size / colour / material / anything) are
data rows via ``ProductAttribute`` / ``ProductAttributeValue`` -- never
product-specific columns (ADR-004). Serialized units, barcodes and bulk
generation are built in later phases and live alongside these models.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
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


class SerializedUnit(TimestampedModel):
    """One physical, individually-tracked unit of a ``ProductVariant``.

    The ``serial_number`` is immutable, globally unique and never reused -- it is
    allocated by :mod:`apps.products.services.serial_numbers` under a per-variant
    Postgres advisory lock, formatted as
    ``<HEXAGARE_SERIAL_PREFIX><variant token>-<zero-padded sequence>``
    (e.g. ``HXMP1123-000001``). ``sequence`` is the per-variant counter behind
    that serial; ``(variant, sequence)`` is unique so a serial can never be
    handed out twice.

    ``status`` moves only along :attr:`ALLOWED_TRANSITIONS` (see sections 14-15
    of ``HEXAGARE_FEATURES.md`` and ``docs/serialized-units.md``). In Phase 3 the
    plain ``transition`` endpoint applies a move directly; from Phase 4 the
    status changes tied to a business action (reserve / transfer / sell / return
    / damage / lose) must go through ``SerializedInventoryService`` so the stock
    ledger stays in step. ``location`` and ``status`` are independent fields:
    an ``IN_TRANSIT`` unit still records the location it is currently at.

    The barcode is **not** stored -- it is the Code128 rendering of
    ``serial_number``, produced on demand.
    """

    class Status(models.TextChoices):
        GENERATED = "GENERATED", "Generated"
        AVAILABLE = "AVAILABLE", "Available"
        RESERVED = "RESERVED", "Reserved"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        SOLD = "SOLD", "Sold"
        RETURNED = "RETURNED", "Returned"
        DAMAGED = "DAMAGED", "Damaged"
        LOST = "LOST", "Lost"
        CANCELLED = "CANCELLED", "Cancelled"

    #: Which statuses each status may move to. An empty set means terminal.
    #: Keep this in sync with the table in ``docs/serialized-units.md``.
    ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        Status.GENERATED: {Status.AVAILABLE, Status.CANCELLED},
        Status.AVAILABLE: {
            Status.RESERVED,
            Status.IN_TRANSIT,
            Status.DAMAGED,
            Status.LOST,
        },
        Status.RESERVED: {Status.AVAILABLE, Status.SOLD, Status.CANCELLED},
        Status.IN_TRANSIT: {Status.AVAILABLE, Status.SOLD, Status.LOST},
        Status.SOLD: {Status.RETURNED},
        Status.RETURNED: {Status.AVAILABLE, Status.DAMAGED},
        Status.DAMAGED: {Status.AVAILABLE, Status.LOST},
        Status.LOST: {Status.AVAILABLE},
        Status.CANCELLED: set(),
    }

    #: Statuses a unit may hold when it is first generated.
    INITIAL_STATUSES = {Status.GENERATED, Status.AVAILABLE}

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="serialized_units",
    )
    serial_number = models.CharField(max_length=64, unique=True, editable=False)
    sequence = models.PositiveIntegerField(
        editable=False,
        help_text="Per-variant counter behind the serial number.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.GENERATED,
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="serialized_units",
    )
    purchase_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "sequence"],
                name="uniq_sequence_per_variant",
            ),
        ]

    #: Fields fixed for the life of the row: the serial number is a permanent
    #: physical identity and its variant/sequence must never drift from it.
    IMMUTABLE_FIELDS = ("variant_id", "serial_number", "sequence")

    def __str__(self) -> str:
        return self.serial_number

    def save(self, *args, **kwargs):
        """Block any edit to an immutable field once the row exists.

        The API never updates these (the viewset has no update action) and
        ``services.serial_numbers`` only ever writes ``status`` / ``location``;
        this guards the admin and one-off scripts. Skipped when an explicit
        ``update_fields`` clearly touches none of them (the transition path).
        """
        update_fields = kwargs.get("update_fields")
        touches_immutable = update_fields is None or (
            {"variant", "serial_number", "sequence"} & set(update_fields)
        )
        if self.pk and not self._state.adding and touches_immutable:
            stored = type(self).objects.filter(pk=self.pk).values(*self.IMMUTABLE_FIELDS).first()
            if stored is not None:
                changed = [f for f in self.IMMUTABLE_FIELDS if getattr(self, f) != stored[f]]
                if changed:
                    raise ValueError(
                        f"{', '.join(changed)} cannot be changed on an existing "
                        f"SerializedUnit (serial numbers are immutable)."
                    )
        super().save(*args, **kwargs)

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, set())

    @property
    def allowed_transitions(self) -> list[str]:
        return sorted(self.ALLOWED_TRANSITIONS.get(self.status, set()))

    @property
    def is_terminal(self) -> bool:
        return not self.ALLOWED_TRANSITIONS.get(self.status)


class LabelBatch(TimestampedModel):
    """A bulk unit-generation run and the label-sheet PDF it produces (Phase 5).

    The batch row and its ``quantity`` :class:`SerializedUnit` rows are created in
    **one** atomic block (all-or-nothing -- ``apps.products.services.bulk_generate``);
    the PDF is rendered *after* that commits by
    ``apps.products.tasks.render_label_pdf`` and stored on ``STORAGES["default"]``
    (S3 in staging/production, the local media volume in development). A failed
    render leaves the units intact and the batch re-renderable via ``regenerate``.

    Serial numbers are **not** taken from user input -- ``bulk_generate`` calls
    the same advisory-locked allocator the single-unit path uses. See ADR-010 and
    ``docs/serialized-units.md``.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    class BarcodeType(models.TextChoices):
        CODE128 = "code128", "Code 128"

    #: Hard ceiling on one batch -- keeps the allocation transaction bounded.
    MAX_QUANTITY = 5000

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="label_batches",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="label_batches",
    )
    quantity = models.PositiveIntegerField()
    initial_status = models.CharField(
        max_length=16,
        choices=SerializedUnit.Status.choices,
        help_text="Status every unit in the batch was generated as.",
    )
    label_size = models.ForeignKey(
        LabelSize,
        on_delete=models.PROTECT,
        related_name="label_batches",
    )
    barcode_type = models.CharField(
        max_length=16,
        choices=BarcodeType.choices,
        default=BarcodeType.CODE128,
    )

    # -- optional label content (section 11) --------------------------------
    include_product_name = models.BooleanField(default=True)
    include_variant = models.BooleanField(default=True)
    include_sku = models.BooleanField(default=True)
    include_mrp = models.BooleanField(default=False)
    include_selling_price = models.BooleanField(default=False)
    custom_text = models.CharField(max_length=120, blank=True)

    # -- PDF render state -------------------------------------------------
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    pdf_file = models.FileField(upload_to="labels/", blank=True)
    pdf_generated_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    units = models.ManyToManyField(
        SerializedUnit,
        through="LabelBatchItem",
        related_name="label_batches",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "label batches"

    def __str__(self) -> str:
        return f"Batch #{self.pk}: {self.quantity} x {self.variant_id} ({self.status})"


class LabelBatchItem(models.Model):
    """One :class:`SerializedUnit` belonging to a :class:`LabelBatch` (the M2M
    through model). Rows are written once, when the batch is generated."""

    batch = models.ForeignKey(
        LabelBatch,
        on_delete=models.CASCADE,
        related_name="items",
    )
    serialized_unit = models.ForeignKey(
        SerializedUnit,
        on_delete=models.PROTECT,
        related_name="label_batch_items",
    )

    class Meta:
        # Units are appended in allocation order, so ``id`` is sequence order.
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "serialized_unit"],
                name="uniq_unit_per_label_batch",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.serialized_unit_id} on batch #{self.batch_id}"


class SerializedUnitEvent(models.Model):
    """Append-only status-change log for a :class:`SerializedUnit`.

    Written on creation and on every transition. This is the unit's own audit
    trail -- distinct from the Phase 4 ``inventory.InventoryTransaction`` stock
    ledger (ADR-008). Rows are never updated or deleted.
    """

    unit = models.ForeignKey(
        SerializedUnit,
        on_delete=models.CASCADE,
        related_name="events",
    )
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16)
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    note = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        arrow = f"{self.from_status or '-'} -> {self.to_status}"
        return f"{self.unit.serial_number}: {arrow}"
