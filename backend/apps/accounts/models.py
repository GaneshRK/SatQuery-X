import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    """
    Tenant/organization for SatQuery-X.

    An organization owns projects and can have multiple users.
    """

    TIER_CHOICES = [
        ("free", "Free Community"),
        ("pro", "Professional Analyst"),
        ("enterprise", "Enterprise Defense / Gov"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=255,
        unique=True,
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
    )

    tier = models.CharField(
        max_length=32,
        choices=TIER_CHOICES,
        default="free",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["tier", "created_at"],
                name="org_tier_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.tier})"


class Project(models.Model):
    """
    A workspace belonging to an organization.

    SatQuery-X sessions, analyses and other project-scoped resources
    can be associated with a Project through the rest of the system.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="projects",
        null=True,
        blank=True,
    )

    name = models.CharField(
        max_length=255,
    )

    description = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "-created_at"],
                name="project_org_created_idx",
            ),
            models.Index(
                fields=["organization", "name"],
                name="project_org_name_idx",
            ),
        ]

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    SatQuery-X application user.

    Authentication is handled by Django's authentication system and
    JWT endpoints exposed through the accounts API.

    Roles:
        OWNER   -> organization owner
        ADMIN   -> organization/project administrator
        ANALYST -> remote-sensing analyst
        VIEWER  -> read-only access

    Legacy values are intentionally retained for database compatibility.
    They can be removed later after existing users have been migrated.
    """

    ROLE_CHOICES = [
        ("OWNER", "Organization Owner"),
        ("ADMIN", "Project Administrator"),
        ("ANALYST", "Remote Sensing Analyst"),
        ("VIEWER", "Read-Only Viewer"),

        # Legacy database compatibility.
        # Do not use these for newly created users.
        ("JUDGE", "Legacy Judge"),
        ("demo", "Legacy Demo Analyst"),
        ("judge", "Legacy Judge"),
        ("admin", "Legacy Administrator"),
    ]

    role = models.CharField(
        max_length=32,
        choices=ROLE_CHOICES,
        default="ANALYST",
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )

    class Meta:
        ordering = ["username"]
        indexes = [
            models.Index(
                fields=["organization", "role"],
                name="user_org_role_idx",
            ),
            models.Index(
                fields=["organization", "is_active"],
                name="user_org_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.username} ({self.role})"

    @property
    def is_owner(self):
        return self.role == "OWNER"

    @property
    def is_admin(self):
        return self.role in {"OWNER", "ADMIN"}

    @property
    def is_analyst(self):
        return self.role == "ANALYST"

    @property
    def is_viewer(self):
        return self.role == "VIEWER"

    def belongs_to_organization(self, organization):
        """
        Safely check whether this user belongs to an organization.
        """
        if organization is None:
            return False

        return (
            self.organization_id is not None
            and self.organization_id == organization.pk
        )