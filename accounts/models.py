from django.contrib.auth.models import AbstractUser
from django.db import models

class Region(models.TextChoices):
    GLOBAL = "GLOBAL", "Global"
    EU = "EU", "Europe"
    APAC = "APAC", "Asia-Pacific"
    NA = "NA", "North America"
    SA = "SA", "South America"


class User(AbstractUser):
    class Role(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        CHAMPION = "CHAMPION", "Knowledge Champion"
        OFFICER = "OFFICER", "Regional Officer"
        COUNCIL = "COUNCIL", "Government Council"
        ADMIN = "ADMIN", "System Admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    region = models.CharField(
        max_length=20,
        choices=Region.choices,
        blank=True,
        null=True,
    )
