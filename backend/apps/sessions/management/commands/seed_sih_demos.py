"""
Legacy-compatible workspace seeding command for SatQuery-X.

IMPORTANT
---------
This command intentionally does NOT generate synthetic satellite imagery,
fake scientific measurements, fabricated polygons, fake confidence scores,
or showcase analysis results.

The old command was designed around SIH showcase demos. SatQuery-X is now
treated as a standalone Earth-observation product, so this command only
creates empty analysis workspaces that can be populated through the real
imagery ingestion and analysis pipeline.

The filename is retained for backward compatibility with existing scripts.
"""

from __future__ import annotations

from typing import Iterable

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.sessions.models import Session


class Command(BaseCommand):
    help = (
        "Create clean SatQuery-X analysis workspaces without synthetic "
        "imagery or fabricated scientific results."
    )

    DEFAULT_WORKSPACES = (
        {
            "name": "Earth Observation Workspace",
            "description": (
                "General-purpose workspace for real satellite and "
                "remote-sensing imagery analysis."
            ),
        },
        {
            "name": "Change Detection Workspace",
            "description": (
                "Workspace for real multi-temporal imagery and "
                "evidence-backed change analysis."
            ),
        },
        {
            "name": "Environmental Monitoring Workspace",
            "description": (
                "Workspace for real environmental and land-surface "
                "observations."
            ),
        },
        {
            "name": "Urban Analysis Workspace",
            "description": (
                "Workspace for real urban, infrastructure, and "
                "built-environment imagery."
            ),
        },
        {
            "name": "Disaster Analysis Workspace",
            "description": (
                "Workspace for real pre-event and post-event imagery "
                "analysis."
            ),
        },
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help=(
                "Username that owns the workspaces. If omitted, the command "
                "uses an existing superuser/staff user or the first user."
            ),
        )

        parser.add_argument(
            "--name",
            type=str,
            default=None,
            help="Create only one workspace with the supplied name.",
        )

        parser.add_argument(
            "--all",
            action="store_true",
            help="Create all default SatQuery-X workspaces.",
        )

        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Delete existing empty workspaces with the same names before "
                "creating them. Workspaces containing queries or imagery are "
                "never deleted."
            ),
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("username"))

        workspace_name = options.get("name")
        create_all = options.get("all", False)
        reset = options.get("reset", False)

        if workspace_name and create_all:
            raise CommandError(
                "Use either --name or --all, not both."
            )

        if workspace_name:
            workspaces = [
                {
                    "name": workspace_name.strip(),
                    "description": (
                        "SatQuery-X Earth-observation analysis workspace."
                    ),
                }
            ]
        else:
            workspaces = list(self.DEFAULT_WORKSPACES)

        if not workspaces:
            raise CommandError("No workspaces were selected.")

        if any(not item["name"] for item in workspaces):
            raise CommandError("Workspace name cannot be empty.")

        created = 0
        existing = 0
        reset_count = 0

        for definition in workspaces:
            session, was_created, was_reset = self._create_workspace(
                user=user,
                name=definition["name"],
                description=definition["description"],
                reset=reset,
            )

            if was_reset:
                reset_count += 1

            if was_created:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created workspace: {session.name} "
                        f"({session.id})"
                    )
                )
            else:
                existing += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Workspace already exists: {session.name} "
                        f"({session.id})"
                    )
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "SatQuery-X workspace setup completed."
            )
        )
        self.stdout.write(f"Owner: {user.get_username()}")
        self.stdout.write(f"Created: {created}")
        self.stdout.write(f"Existing: {existing}")
        self.stdout.write(f"Reset: {reset_count}")
        self.stdout.write("")
        self.stdout.write(
            "No synthetic imagery, fabricated coordinates, fake measurements, "
            "or generated scientific results were created."
        )
        self.stdout.write(
            "Upload or retrieve real imagery through the normal SatQuery-X "
            "ingestion pipeline before running analysis."
        )

    def _resolve_user(self, username: str | None):
        User = get_user_model()

        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(
                    f"User '{username}' does not exist."
                ) from exc

        privileged = (
            User.objects.filter(is_superuser=True)
            .order_by("id")
            .first()
        )

        if privileged:
            return privileged

        staff = (
            User.objects.filter(is_staff=True)
            .order_by("id")
            .first()
        )

        if staff:
            return staff

        user = User.objects.order_by("id").first()

        if user:
            return user

        raise CommandError(
            "No users exist. Create an application user first, then run "
            "this command with --username."
        )

    def _create_workspace(
        self,
        *,
        user,
        name: str,
        description: str,
        reset: bool,
    ):
        existing = (
            Session.objects
            .filter(user=user, name=name)
            .order_by("created_at")
            .first()
        )

        reset_performed = False

        if existing:
            if reset and self._is_empty_workspace(existing):
                existing.delete()
                existing = None
                reset_performed = True

        if existing:
            return existing, False, reset_performed

        context = {
            "workspace_type": "earth_observation_analysis",
            "description": description,
            "data_status": "awaiting_real_imagery",
            "active_asset_ids": [],
            "active_image_pair_id": None,
            "active_pin": None,
            "active_aoi": None,
            "map_view": {},
            "last_intent": None,
            "last_query_id": None,
            "data_provenance": {
                "imagery_source": "not_loaded",
                "scientific_results": "not_available",
                "coordinates": "not_available",
            },
        }

        session = Session.objects.create(
            user=user,
            name=name,
            status=self._active_status(),
            conversation_history=[],
            conversation_context=context,
        )

        return session, True, reset_performed

    @staticmethod
    def _active_status():
        """
        Resolve the model's active status without assuming that the project
        uses a particular literal representation internally.
        """
        field = Session._meta.get_field("status")

        choices = {
            str(value).upper(): value
            for value, _label in field.choices
        }

        for candidate in ("ACTIVE", "OPEN", "RUNNING"):
            if candidate in choices:
                return choices[candidate]

        if field.default not in (None, ""):
            return field.default

        if choices:
            return next(iter(choices.values()))

        return "ACTIVE"

    @staticmethod
    def _is_empty_workspace(session: Session) -> bool:
        """
        A workspace is resettable only when it has no analysis state that
        could represent user work.
        """
        image_count = getattr(session, "image_count", None)

        if callable(image_count):
            image_count = image_count()

        if image_count is None:
            try:
                image_count = session.images.count()
            except Exception:
                image_count = 0

        if image_count:
            return False

        try:
            if session.queries.exists():
                return False
        except Exception:
            pass

        history = getattr(session, "conversation_history", None)

        if history:
            return False

        context = getattr(session, "conversation_context", None)

        if context:
            active_assets = context.get("active_asset_ids", [])
            active_pair = context.get("active_image_pair_id")
            last_query = context.get("last_query_id")

            if active_assets or active_pair or last_query:
                return False

        return True