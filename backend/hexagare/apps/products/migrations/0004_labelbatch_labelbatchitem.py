# Generated for Phase 5 (Bulk Unit Generation + Label PDFs).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_UNIT_STATUS_CHOICES = [
    ("GENERATED", "Generated"),
    ("AVAILABLE", "Available"),
    ("RESERVED", "Reserved"),
    ("IN_TRANSIT", "In transit"),
    ("SOLD", "Sold"),
    ("RETURNED", "Returned"),
    ("DAMAGED", "Damaged"),
    ("LOST", "Lost"),
    ("CANCELLED", "Cancelled"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0001_initial"),
        ("products", "0003_serializedunit_serializedunitevent_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LabelBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.PositiveIntegerField()),
                ("initial_status", models.CharField(choices=_UNIT_STATUS_CHOICES, help_text="Status every unit in the batch was generated as.", max_length=16)),
                ("barcode_type", models.CharField(choices=[("code128", "Code 128")], default="code128", max_length=16)),
                ("include_product_name", models.BooleanField(default=True)),
                ("include_variant", models.BooleanField(default=True)),
                ("include_sku", models.BooleanField(default=True)),
                ("include_mrp", models.BooleanField(default=False)),
                ("include_selling_price", models.BooleanField(default=False)),
                ("custom_text", models.CharField(blank=True, max_length=120)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("READY", "Ready"), ("FAILED", "Failed")], db_index=True, default="PENDING", max_length=12)),
                ("pdf_file", models.FileField(blank=True, upload_to="labels/")),
                ("pdf_generated_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("label_size", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="label_batches", to="products.labelsize")),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="label_batches", to="inventory.location")),
                ("variant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="label_batches", to="products.productvariant")),
            ],
            options={
                "verbose_name_plural": "label batches",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="LabelBatchItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="products.labelbatch")),
                ("serialized_unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="label_batch_items", to="products.serializedunit")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.AddField(
            model_name="labelbatch",
            name="units",
            field=models.ManyToManyField(related_name="label_batches", through="products.LabelBatchItem", to="products.serializedunit"),
        ),
        migrations.AddConstraint(
            model_name="labelbatchitem",
            constraint=models.UniqueConstraint(fields=("batch", "serialized_unit"), name="uniq_unit_per_label_batch"),
        ),
    ]
