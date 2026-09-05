from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Seed demo and judge user accounts for testing."

    def handle(self, *args, **options):
        # Demo Analyst
        demo_user, created = User.objects.get_or_create(
            username="analyst",
            defaults={"email": "analyst@isro.gov.in", "role": "demo"}
        )
        demo_user.set_password("satquery2026")
        demo_user.save()
        if created:
            self.stdout.write(self.style.SUCCESS("Created demo user 'analyst' (pass: satquery2026)"))
        else:
            self.stdout.write("Updated password for demo user 'analyst' (pass: satquery2026)")

        # SIH Judge
        judge_user, created = User.objects.get_or_create(
            username="sih_judge",
            defaults={"email": "judge@sih.gov.in", "role": "judge", "is_staff": True}
        )
        judge_user.set_password("judge2026")
        judge_user.save()
        if created:
            self.stdout.write(self.style.SUCCESS("Created judge user 'sih_judge' (pass: judge2026)"))
        else:
            self.stdout.write("Updated password for judge user 'sih_judge' (pass: judge2026)")
