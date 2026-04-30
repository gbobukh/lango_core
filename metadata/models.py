from django.db import models

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-lock on save
        self.is_locked = True
        super().save(*args, **kwargs)

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-lock on save
        self.is_locked = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Config for {self.tracker.name}"

    class Meta:
        verbose_name = "Tracker Response Mapping"
        verbose_name_plural = "Tracker Response Mappings"


class SegmentAttributeType(models.Model):
    """Allowed type/category for a segment attribute."""
    name = models.CharField(max_length=255, unique=True)

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.attribute_type})"

    class Meta:
        verbose_name = "Segments Attribute"
        verbose_name_plural = "Segments Attributes"
        ordering = ['name']

