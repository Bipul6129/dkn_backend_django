from django.conf import settings
from django.db import models
from django.db.models import Q
from accounts.models import Region  # you already have this
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

User = settings.AUTH_USER_MODEL


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNING = "PLANNING", "Planning"
        ACTIVE = "ACTIVE", "Active"
        ON_HOLD = "ON_HOLD", "On hold"
        COMPLETED = "COMPLETED", "Completed"
        ARCHIVED = "ARCHIVED", "Archived"

    name = models.CharField(max_length=255)
    client = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNING,
    )

    region = models.CharField(
        max_length=20,
        choices=Region.choices,
        default=Region.GLOBAL,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="projects_created",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    # handy helper: returns the current project lead (or None)
    @property
    def lead(self):
        assignment = (
            self.assignments
            .select_related("user")
            .filter(role=ProjectAssignment.Role.LEAD)
            .first()
        )
        return assignment.user if assignment else None


class ProjectAssignment(models.Model):
    """
    Links users to projects with a role (Lead / Member / etc).

    Enforces:
      - a user appears only once per project
      - at most ONE LEAD per project
    """

    class Role(models.TextChoices):
        LEAD = "LEAD", "Project Lead"
        MEMBER = "MEMBER", "Team Member"
        REVIEWER = "REVIEWER", "Reviewer / QA"
        STAKEHOLDER = "STAKEHOLDER", "Stakeholder"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="assignments",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_assignments",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("project", "user")]
        constraints = [
            # per project, only one row is allowed with role=LEAD
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(role="LEAD"),
                name="unique_lead_per_project",
            )
        ]

    def __str__(self):
        return f"{self.project} – {self.user} ({self.role})"

    @property
    def is_lead(self):
        return self.role == self.Role.LEAD


class CollaborationSpace(models.Model):
    """
    Workspace for a project (Kanban board, discussion area, etc.)
    ERD: CollaborationSpace <<core>>
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="spaces",
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # optional: which user created the space
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collaboration_spaces_created",
    )

    is_default = models.BooleanField(
        default=False,
        help_text="Primary workspace for this project.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.title} ({self.project})"


User = settings.AUTH_USER_MODEL

# ... Project, ProjectAssignment, CollaborationSpace already here ...


class CollaborationPost(models.Model):
    """
    A message or file shared inside a collaboration space.
    Either message, file, or both.
    """
    space = models.ForeignKey(
        "CollaborationSpace",
        on_delete=models.CASCADE,
        related_name="posts",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="collab_posts",
    )
    message = models.TextField(blank=True)
    file = models.FileField(
        upload_to="collab_posts/",
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]  # oldest → newest

    def __str__(self):
        base = f"Post {self.id} in space {self.space_id}"
        if self.message:
            return base + f": {self.message[:30]}"
        return base + " (file)"
