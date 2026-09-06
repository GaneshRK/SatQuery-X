"""
SatQuery-X showcase data management command.

IMPORTANT
---------
This command intentionally does NOT generate synthetic satellite imagery,
fabricated scientific measurements, fake polygons, fake confidence values,
or simulated analysis results.

SatQuery-X must explain actual evidence produced from real imagery and
registered analysis pipelines.

For development/demo environments, this command creates only a clean
session workspace for an authenticated user. Real imagery can then be
uploaded through the normal imagery ingestion pipeline.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.sessions.models import Session


User = get_user_model()


class Command(BaseCommand):
    """
    Create an empty showcase analysis session.

    The command deliberately contains no synthetic remote-sensing data.
    """

    help = (
        "Create a clean SatQuery-X showcase analysis session without "
        "synthetic imagery or fabricated scientific results."
    )

    DEFAULT_SESSION_NAME = (
        "SatQuery-X Earth Observation Analysis"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="",
            help=(
                "Username that will own the showcase session. "
                "If omitted, an existing suitable user is selected."
            ),
        )

        parser.add_argument(
            "--name",
            type=str,
            default=self.DEFAULT_SESSION_NAME,
            help="Name of the showcase analysis session.",
        )

        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Archive existing sessions with the same name for the "
                "selected user before creating the new session."
            ),
        )

    # ------------------------------------------------------------------
    # User selection
    # ------------------------------------------------------------------

    def get_target_user(self, username: str):
        """
        Resolve an existing user.

        We do not create privileged/demo accounts automatically.
        Creating users belongs to the authentication/administration flow.
        """
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(
                    f"User '{username}' does not exist."
                ) from exc

        # Prefer an existing superuser only as a local development
        # convenience. No account is created by this command.
        user = (
            User.objects
            .filter(is_superuser=True)
            .order_by("id")
            .first()
        )

        if user is not None:
            return user

        user = (
            User.objects
            .filter(is_staff=True)
            .order_by("id")
            .first()
        )

        if user is not None:
            return user

        user = (
            User.objects
            .order_by("id")
            .first()
        )

        if user is not None:
            return user

        raise CommandError(
            "No existing user was found. Create an authenticated user "
            "first, then run this command with --username."
        )

    # ------------------------------------------------------------------
    # Session creation
    # ------------------------------------------------------------------

    def create_session(
        self,
        *,
        user,
        name: str,
        reset: bool,
    ) -> Session:
        """
        Create a clean analysis workspace.

        No imagery, query, evidence, report, satellite scene, or
        scientific result is inserted.
        """
        normalized_name = (
            name or self.DEFAULT_SESSION_NAME
        ).strip()

        if not normalized_name:
            raise CommandError(
                "Session name cannot be empty."
            )

        existing = Session.objects.filter(
            user=user,
            name=normalized_name,
        )

        if reset:
            archived_count = existing.filter(
                status=Session.STATUS_ACTIVE
            ).update(
                status=Session.STATUS_ARCHIVED
            )

            if archived_count:
                self.stdout.write(
                    self.style.WARNING(
                        f"Archived {archived_count} existing active "
                        "showcase session(s)."
                    )
                )
        else:
            active = existing.filter(
                status=Session.STATUS_ACTIVE
            ).first()

            if active is not None:
                self.stdout.write(
                    self.style.WARNING(
                        "An active showcase session already exists:"
                    )
                )
                self.stdout.write(
                    f"  {active.name}"
                )
                self.stdout.write(
                    f"  ID: {active.id}"
                )

                return active

        session = Session.objects.create(
            user=user,
            name=normalized_name,
            status=Session.STATUS_ACTIVE,
            conversation_history=[],
            conversation_context={
                "workspace_type": "earth_observation_analysis",
                "data_status": "awaiting_real_imagery",
                "active_asset_ids": [],
                "active_image_pair_id": None,
                "active_pin": None,
                "active_aoi": None,
                "map_view": {},
                "last_intent": None,
                "last_query_id": None,
            },
        )

        return session

    # ------------------------------------------------------------------
    # Command entry point
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        username = (
            options.get("username") or ""
        ).strip()

        name = (
            options.get("name")
            or self.DEFAULT_SESSION_NAME
        ).strip()

        reset = bool(
            options.get("reset")
        )

        self.stdout.write(
            "Creating SatQuery-X analysis workspace..."
        )

        user = self.get_target_user(username)

        session = self.create_session(
            user=user,
            name=name,
            reset=reset,
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "SatQuery-X showcase workspace is ready."
            )
        )
        self.stdout.write(
            f"User: {user.username}"
        )
        self.stdout.write(
            f"Session: {session.name}"
        )
        self.stdout.write(
            f"Session ID: {session.id}"
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "No synthetic imagery or fabricated scientific "
                "results were created."
            )
        )
        self.stdout.write(
            "Upload real imagery through the SatQuery-X ingestion "
            "pipeline to begin analysis."
        )