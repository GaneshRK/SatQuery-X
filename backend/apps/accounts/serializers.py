from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import Organization, Project

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(
        source="members.count",
        read_only=True,
    )
    project_count = serializers.IntegerField(
        source="projects.count",
        read_only=True,
    )

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "slug",
            "tier",
            "created_at",
            "member_count",
            "project_count",
        )
        read_only_fields = (
            "id",
            "created_at",
            "member_count",
            "project_count",
        )


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = (
            "id",
            "organization",
            "name",
            "description",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )


class UserSerializer(serializers.ModelSerializer):
    organization_details = OrganizationSerializer(
        source="organization",
        read_only=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "organization",
            "organization_details",
            "is_active",
            "date_joined",
        )
        read_only_fields = (
            "id",
            "role",
            "organization",
            "organization_details",
            "is_active",
            "date_joined",
        )


class RegisterSerializer(serializers.ModelSerializer):
    """
    Public user registration.

    New public users are always created as ANALYSTs.
    Privileged roles must be assigned by an administrator through
    an authenticated administrative workflow.
    """

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
    )

    password_confirm = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
        )
        read_only_fields = ("id",)

    def validate_username(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Username cannot be empty."
            )

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this username already exists."
            )

        return value

    def validate_email(self, value):
        value = value.strip().lower()

        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )

        return value

    def validate(self, attrs):
        password = attrs.get("password")
        password_confirm = attrs.pop("password_confirm", None)

        if password != password_confirm:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            role="ANALYST",
        )