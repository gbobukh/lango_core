import os
import uuid

from django.contrib.auth.models import User
from django.db import models


def api_spec_upload_to(instance, filename):
    """Store uploaded API specs on disk under tracker-scoped paths."""
    _, ext = os.path.splitext(filename)
    ext = ext.lower() if ext else ''
    stored_name = f'{uuid.uuid4().hex}{ext}'
    tracker_id = instance.tracker_id or 'unassigned'
    return f'api_specs/{tracker_id}/{stored_name}'


def _format_from_filename(filename):
    ext = os.path.splitext(filename or '')[1].lower()
    if ext in ('.yaml', '.yml'):
        return 'openapi'
    if ext == '.json':
        return 'json'
    if ext == '.md':
        return 'markdown'
    if ext == '.txt':
        return 'plain'
    if ext == '.html':
        return 'html'
    return 'unknown'

class TargetParameter(models.Model):
    """
    Defines a metadata parameter (e.g. 'Country', 'Traffic Source') 
    and its allowed/predefined values.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the parameter (e.g. 'Country')")
    values = models.JSONField(
        default=list, 
        blank=True, 
        help_text="List of predefined values (e.g. ['US', 'UK', 'CA'])"
    )
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_target_parameters',
        blank=True,
        help_text="Users who can view and use this target parameter.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Target Parameter"
        verbose_name_plural = "Target Parameters"

class PublisherConfig(models.Model):
    partner_account = models.OneToOneField(
        'integrations.PartnerAccount',
        on_delete=models.CASCADE,
        limit_choices_to={'account_type__name': 'Publisher'},
        related_name='publisher_config',
        help_text="Select a Publisher Account to configure"
    )
    config = models.JSONField(default=dict, blank=True, help_text="Configuration state for parameters")
    is_locked = models.BooleanField(default=True, help_text="Uncheck to edit configuration. Automatically locks on save.")
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_publisher_configs',
        blank=True,
        help_text="Users who can view and use this publisher config.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def publisher_name(self):
        return self.partner_account.name

    def __str__(self):
        return self.partner_account.name

    class Meta:
        verbose_name = "Publisher Config"
        verbose_name_plural = "Publisher Configs"


class CompatibilityMatrix(models.Model):
    """
    Defines compatibility rules for Target Parameters.
    Example: IF OS='iOS' THEN Device Type ALLOW ['Mobile', 'Tablet']
    """
    subject_parameter = models.ForeignKey(
        TargetParameter, 
        on_delete=models.CASCADE, 
        related_name='rules_as_subject',
        help_text="The parameter that triggers the rule (e.g., 'OS')"
    )
    subject_value = models.CharField(
        max_length=255, 
        help_text="The value of the subject parameter that triggers the rule (e.g., 'iOS')"
    )
    target_parameter = models.ForeignKey(
        TargetParameter, 
        on_delete=models.CASCADE, 
        related_name='rules_as_target',
        help_text="The parameter being restricted (e.g., 'Device Type')"
    )
    allowed_values = models.JSONField(
        default=list, 
        help_text="List of allowed values for the target parameter (e.g., ['Mobile', 'Tablet'])"
    )
    is_locked = models.BooleanField(default=True, help_text="Uncheck to edit rule. Automatically locks on save.")
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_compatibility_matrices',
        blank=True,
        help_text="Users who can view and use this compatibility rule.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-lock on save
        self.is_locked = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"IF {self.subject_parameter}={self.subject_value} THEN {self.target_parameter} ALLOW {self.allowed_values}"

    class Meta:
        verbose_name = "Compatibility Rule"
        verbose_name_plural = "Compatibility Matrix"
        unique_together = ('subject_parameter', 'subject_value', 'target_parameter')

class TrafficType(models.Model):
    name = models.CharField(max_length=255, unique=True)
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_traffic_types',
        blank=True,
        help_text="Users who can view and use this traffic type.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Traffic Type"
        verbose_name_plural = "Traffic Types"
        ordering = ['name']

class GlobalVariable(models.Model):
    """
    Defines a standard system variable name (e.g. 'std_subid').
    Used to normalize data keys across different Trackers.
    """
    name = models.CharField(max_length=255, unique=True, help_text="Name of the standard system variable (e.g. 'std_subid')")
    description = models.TextField(blank=True, help_text="Description of what this variable represents")
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_global_variables',
        blank=True,
        help_text="Users who can view and use this global variable.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Global Variable"
        verbose_name_plural = "Global Variables"
        ordering = ['name']


class TrackerConfig(models.Model):
    """
    Stores configuration for a Tracker (e.g. mapping of Global Variables to response keys).
    One-to-One with Tracker.
    """
    tracker = models.OneToOneField(
        'integrations.Tracker',
        on_delete=models.CASCADE,
        related_name='tracker_config',
        help_text="Select a Tracker to configure"
    )
    mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuration state: {'GlobalVarName': 'TrackerKey'}"
    )
    is_locked = models.BooleanField(default=True, help_text="Uncheck to edit configuration. Automatically locks on save.")
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_tracker_configs',
        blank=True,
        help_text="Users who can view and use this tracker response mapping.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Config for {self.tracker.name}"

    class Meta:
        verbose_name = "Tracker Response Mapping"
        verbose_name_plural = "Tracker Response Mappings"


class SegmentAttributeType(models.Model):
    """Allowed type/category for a segment attribute."""
    name = models.CharField(max_length=255, unique=True)
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_segment_attribute_types',
        blank=True,
        help_text="Users who can view and use this segment attribute type.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Segments Attribute Type"
        verbose_name_plural = "Segments Attributes Types"
        ordering = ['name']


class SegmentAttribute(models.Model):
    """Segment attribute: name plus type from Segments Attributes Types."""
    name = models.CharField(max_length=255)
    attribute_type = models.ForeignKey(
        SegmentAttributeType,
        on_delete=models.PROTECT,
        related_name='attributes',
        help_text="Type from Segments Attributes Types",
    )
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_segment_attributes',
        blank=True,
        help_text="Users who can view and use this segment attribute.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.attribute_type})"

    class Meta:
        verbose_name = "Segments Attribute"
        verbose_name_plural = "Segments Attributes"
        ordering = ['name']


class ApiSpec(models.Model):
    """Uploaded API specification file for a tracker/platform (read by agents later)."""

    FORMAT_CHOICES = [
        ('openapi', 'OpenAPI (YAML)'),
        ('json', 'JSON'),
        ('markdown', 'Markdown'),
        ('plain', 'Plain text'),
        ('html', 'HTML'),
        ('unknown', 'Unknown'),
    ]

    tracker = models.ForeignKey(
        'integrations.Tracker',
        on_delete=models.CASCADE,
        related_name='api_specs',
        help_text='Platform (tracker) this specification belongs to.',
    )
    name = models.CharField(
        max_length=255,
        help_text='Label for this spec (e.g. "Admin API v2").',
    )
    spec_file = models.FileField(
        upload_to=api_spec_upload_to,
        help_text='Upload the API specification file from your computer.',
    )
    source_filename = models.CharField(
        max_length=512,
        blank=True,
        help_text='Original filename as uploaded by the user.',
    )
    format = models.CharField(
        max_length=20,
        choices=FORMAT_CHOICES,
        default='unknown',
        help_text='Detected or assigned format hint for agents.',
    )
    visible_to = models.ManyToManyField(
        User,
        related_name='visible_api_specs',
        blank=True,
        help_text='Users who can view and use this API spec.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.tracker.name})'

    def save(self, *args, **kwargs):
        if self.spec_file and not self.source_filename:
            self.source_filename = os.path.basename(self.spec_file.name)
        if self.source_filename and self.format == 'unknown':
            self.format = _format_from_filename(self.source_filename)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        stored_file = self.spec_file
        super().delete(*args, **kwargs)
        if stored_file:
            stored_file.delete(save=False)

    class Meta:
        verbose_name = 'API Spec'
        verbose_name_plural = 'API Specs'
        ordering = ['tracker__name', 'name']
        unique_together = ('tracker', 'name')

