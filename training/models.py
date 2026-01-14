from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Region  # you showed this earlier


User = settings.AUTH_USER_MODEL


class TrainingCourse(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PUBLISHED,  # keep simple: published by default
    )

    # regional targeting – employees see only their region (and GLOBAL)
    region = models.CharField(
        max_length=20,
        choices=Region.choices,
        default=Region.GLOBAL,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="training_courses_created",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.title} ({self.region})"


class TrainingMaterial(models.Model):
    """
    A single training resource: file and/or URL.
    """

    course = models.ForeignKey(
        TrainingCourse,
        on_delete=models.CASCADE,
        related_name="materials",
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    file = models.FileField(
        upload_to="training_materials/",
        blank=True,
        null=True,
    )
    link_url = models.URLField(blank=True)

    order = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.course_id}: {self.title}"


class TrainingQuestion(models.Model):
    """
    Quiz question for a course.
    (Champions can manage via Django admin; frontend will fetch only.)
    """

    course = models.ForeignKey(
        TrainingCourse,
        on_delete=models.CASCADE,
        related_name="questions",
    )

    text = models.TextField()
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"Q{self.order} for course {self.course_id}"


class TrainingOption(models.Model):
    """
    Possible answer for a question.
    """

    question = models.ForeignKey(
        TrainingQuestion,
        on_delete=models.CASCADE,
        related_name="options",
    )

    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Option for Q{self.question_id}"


class TrainingAttempt(models.Model):
    """
    A single quiz attempt for a course by a user.
    Used for progress + gamification later.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="training_attempts",
    )

    course = models.ForeignKey(
        TrainingCourse,
        on_delete=models.CASCADE,
        related_name="attempts",
    )

    score = models.PositiveIntegerField()
    total_questions = models.PositiveIntegerField()
    is_passed = models.BooleanField(default=False)

    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"{self.user} – {self.course} ({self.score}/{self.total_questions})"


class TrainingAttemptAnswer(models.Model):
    """
    Stores the chosen option for each question in an attempt.
    """

    attempt = models.ForeignKey(
        TrainingAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )

    question = models.ForeignKey(
        TrainingQuestion,
        on_delete=models.CASCADE,
    )

    selected_option = models.ForeignKey(
        TrainingOption,
        on_delete=models.CASCADE,
    )

    def __str__(self) -> str:
        return f"Attempt {self.attempt_id} – Q{self.question_id}"
