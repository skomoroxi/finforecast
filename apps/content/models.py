"""Default templates, manual values, their history and AI drafts (TECHNICAL-TASK §6.4, §7)."""

from django.conf import settings
from django.db import models

from apps.market.models import Asset, AssetClass

from .fields import FIELDS

FIELD_CHOICES = [(f.key, f"{f.section}: {f.label}") for f in FIELDS]


class Language(models.Model):
    code = models.CharField(max_length=5, unique=True)
    name = models.CharField(max_length=40)
    enabled = models.BooleanField(default=False, help_text="Published on the site.")
    country = models.CharField(max_length=2, blank=True, help_text="Keyword research country.")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class Template(models.Model):
    """The default text of a field, per asset class and language."""

    asset_class = models.ForeignKey(AssetClass, on_delete=models.CASCADE, related_name="templates")
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name="templates")
    field = models.CharField(max_length=40, choices=FIELD_CHOICES)
    body = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_class__code", "language__code", "field"]
        constraints = [
            models.UniqueConstraint(fields=["asset_class", "language", "field"], name="one_template_per_slot"),
        ]

    def __str__(self):
        return f"{self.asset_class.code}/{self.language.code}/{self.field}"


class Override(models.Model):
    """A manual value. Wins over the template for this asset and language only."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="overrides")
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name="overrides")
    field = models.CharField(max_length=40, choices=FIELD_CHOICES)
    value = models.TextField(blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset__code", "language__code", "field"]
        constraints = [
            models.UniqueConstraint(fields=["asset", "language", "field"], name="one_override_per_slot"),
        ]

    def __str__(self):
        return f"{self.asset.code}/{self.language.code}/{self.field}"


class Revision(models.Model):
    """Every saved version of a template or manual value, for history and rollback."""

    class Kind(models.TextChoices):
        TEMPLATE = "template", "Template"
        OVERRIDE = "override", "Manual value"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    asset_class = models.ForeignKey(AssetClass, null=True, blank=True, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.CASCADE)
    language = models.ForeignKey(Language, on_delete=models.CASCADE)
    field = models.CharField(max_length=40, choices=FIELD_CHOICES)
    value = models.TextField(blank=True, help_text="Empty for a manual value that was reset to the template.")
    removed = models.BooleanField(default=False)
    note = models.CharField(max_length=100, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.kind} {self.field} {self.created_at:%Y-%m-%d %H:%M}"


class Draft(models.Model):
    """AI-written text waiting for review. Never shown on the site (TECHNICAL-TASK §7.3а)."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="drafts")
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name="drafts")
    field = models.CharField(max_length=40, choices=FIELD_CHOICES)
    value = models.TextField()
    model_name = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["asset__code", "language__code", "field"]
        constraints = [
            models.UniqueConstraint(fields=["asset", "language", "field"], name="one_draft_per_slot"),
        ]

    def __str__(self):
        return f"{self.asset.code}/{self.language.code}/{self.field}"
