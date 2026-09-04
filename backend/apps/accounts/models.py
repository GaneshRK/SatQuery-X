from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ("demo", "Demo Analyst"),
        ("judge", "SIH Judge"),
        ("admin", "Administrator"),
    ]
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default="demo")

    def __str__(self):
        return f"{self.username} ({self.role})"
