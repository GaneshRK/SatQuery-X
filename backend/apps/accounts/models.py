import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    TIER_CHOICES = [
        ("free", "Free Community"),
        ("pro", "Professional Analyst"),
        ("enterprise", "Enterprise Defense / Gov"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    tier = models.CharField(max_length=32, choices=TIER_CHOICES, default="free")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.tier})"


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="projects", null=True, blank=True
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = [
        ("OWNER", "Organization Owner"),
        ("ADMIN", "Project Administrator"),
        ("ANALYST", "Remote Sensing Analyst"),
        ("VIEWER", "Read-Only Viewer"),
        ("JUDGE", "SIH Technical Judge"),
        # Legacy/backwards compatibility choices:
        ("demo", "Demo Analyst"),
        ("judge", "SIH Judge"),
        ("admin", "Administrator"),
    ]
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default="ANALYST")
    organization = models.ForeignKey(
        Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="members"
    )

    def __str__(self):
        return f"{self.username} ({self.role})"
