"""Default templates, manual values, their history and AI drafts (TECHNICAL-TASK §6.4, §7)."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.market.models import Asset, AssetClass

from .fields import FIELDS, SECTIONS

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


class Reviewer(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80, unique=True)
    job_title = models.CharField(max_length=80, blank=True)
    photo_url = models.URLField(blank=True)
    profile_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ReviewerBio(models.Model):
    reviewer = models.ForeignKey(Reviewer, on_delete=models.CASCADE, related_name="bios")
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name="+")
    bio = models.TextField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["reviewer", "language"], name="one_bio_per_language")]

    def __str__(self):
        return f"{self.reviewer} ({self.language.code})"


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


class CustomBlock(models.Model):
    """An extra section on one page, in one language, placed after a chosen section."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="custom_blocks")
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name="custom_blocks")
    after_section = models.CharField(max_length=20, choices=[(s, s) for s in SECTIONS])
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Can use the same variables and conditions as other fields.")
    order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["asset__code", "language__code", "order"]

    def __str__(self):
        return f"{self.asset.code}: {self.title}"


class AnalystTarget(models.Model):
    """One published institutional target. Never estimated: a source is required."""

    class Kind(models.TextChoices):
        BANK = "bank", "Bank"
        RESEARCH = "research", "Research firm"
        PUBLIC = "public_institution", "Public institution"
        SURVEY = "survey", "Survey"
        INDIVIDUAL = "individual", "Individual"

    class Basis(models.TextChoices):
        AVERAGE = "average", "Period average"
        END = "end", "End of period"
        PEAK = "peak", "Peak"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="analyst_targets")
    institution = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    target = models.FloatField(null=True, blank=True, help_text="A single target, or fill in both range fields.")
    target_low = models.FloatField(null=True, blank=True)
    target_high = models.FloatField(null=True, blank=True)
    basis = models.CharField(max_length=10, choices=Basis.choices)
    horizon = models.CharField(
        max_length=7,
        validators=[RegexValidator(r"^\d{4}(-Q[1-4])?$", "Use a year or a quarter, such as 2027 or 2027-Q2.")],
    )
    published_on = models.DateField()
    source_title = models.CharField(max_length=200)
    source_url = models.URLField(validators=[RegexValidator(r"^https://", "The source must be an https link.")])
    note = models.CharField(max_length=120, blank=True)
    show = models.BooleanField(default=True)

    class Meta:
        ordering = ["asset__code", "-published_on"]

    def __str__(self):
        return f"{self.asset.code}: {self.institution} {self.horizon}"

    def clean(self):
        has_target = self.target is not None
        has_range = self.target_low is not None and self.target_high is not None
        if has_target == has_range:
            raise ValidationError("Give either a single target or both range fields.")
        if has_range and self.target_low > self.target_high:
            raise ValidationError("The low target is above the high target.")


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
