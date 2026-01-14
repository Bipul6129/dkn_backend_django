from django.conf import settings
from django.db import models
from accounts.models import Region

User = settings.AUTH_USER_MODEL


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class KnowledgeResource(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
        FLAGGED = "FLAGGED", "Flagged"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PUBLISHED = "PUBLISHED", "Published"
        UNPUBLISHED = "UNPUBLISHED", "Unpublished"
        CHANGE_REQUESTED = "CHANGE_REQUESTED", "Change Requested"

    class ReviewStage(models.TextChoices):
        CHAMPION = "CHAMPION", "Knowledge Champion"
        REGIONAL_OFFICER = "REGIONAL_OFFICER", "Regional Officer"
        GOV_COUNCIL = "GOV_COUNCIL", "Knowledge Governance Council"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    current_stage = models.CharField(max_length=30, choices=ReviewStage.choices, default=ReviewStage.CHAMPION)
    submitted_at = models.DateTimeField(null=True, blank=True)

    submitted_version = models.ForeignKey(
        "KnowledgeResourceVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )


    region = models.CharField(
        max_length=20,
        choices=Region.choices,
        default=Region.GLOBAL,
    )

    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="uploaded_resources")

    tags = models.ManyToManyField("Tag", blank=True, related_name="resources")
    metadata = models.JSONField(default=dict, blank=True)

    # ✅ pointer to latest version (optional but very useful)
    latest_version = models.ForeignKey(
        "KnowledgeResourceVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class KnowledgeResourceVersion(models.Model):
    resource = models.ForeignKey(
        KnowledgeResource,
        on_delete=models.CASCADE,
        related_name="versions"
    )

    version_number = models.PositiveIntegerField()
    file = models.FileField(upload_to="knowledge_resources/")
    notes = models.TextField(blank=True)  # optional: "fixed formatting", "updated policy"
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="resource_versions_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("resource", "version_number")]
        ordering = ["-version_number"]

    def __str__(self):
        return f"{self.resource_id} v{self.version_number}"


class AIFlag(models.Model):
    class FlagType(models.TextChoices):
        DUPLICATE = "DUPLICATE", "Duplicate"
        OUTDATED = "OUTDATED", "Outdated"
        METADATA = "METADATA", "Metadata issue"
        QUALITY = "QUALITY", "Low quality"
        ERROR = "ERROR", "AI error"

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    resource = models.ForeignKey(
        KnowledgeResource,
        on_delete=models.CASCADE,
        related_name="ai_flags"
    )

    # ✅ NEW: link flag to a specific version
    version = models.ForeignKey(
        "KnowledgeResourceVersion",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ai_flags"
    )

    flag_type = models.CharField(max_length=20, choices=FlagType.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MEDIUM)
    message = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        v = f" v{self.version.version_number}" if self.version else ""
        return f"{self.flag_type}{v} ({self.severity})"



class ReviewStep(models.Model):
    class Stage(models.TextChoices):
        CHAMPION = "CHAMPION", "Knowledge Champion"
        REGIONAL_OFFICER = "REGIONAL_OFFICER", "Regional Officer"
        GOV_COUNCIL = "GOV_COUNCIL", "Knowledge Governance Council"

    class Decision(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        FLAGGED = "FLAGGED", "Flagged"
        CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes Requested"
        PUBLISHED = "PUBLISHED", "Published"
        UNPUBLISHED = "UNPUBLISHED", "Unpublished"

    resource = models.ForeignKey(KnowledgeResource, on_delete=models.CASCADE, related_name="review_steps")

    # ✅ which version this decision applied to
    version = models.ForeignKey(
        "KnowledgeResourceVersion",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="review_steps"
    )

    stage = models.CharField(max_length=30, choices=Stage.choices)
    decision = models.CharField(max_length=30, choices=Decision.choices)

    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="review_steps_made")
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
