# api/apps.py

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.conf import settings
from django.apps import AppConfig, apps
from django.db.models.signals import post_save

def _setup_daily_slot_prefill_schedule():
    """Create or update a daily midnight schedule for pre-filling slots.

    Uses django-celery-beat's DatabaseScheduler via PeriodicTask + CrontabSchedule.
    Safe to call multiple times (idempotent).
    """
    try:
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        from django.db import transaction

        # Run this after the current transaction commits (e.g., on migrations)
        def _create_or_update():
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute="0",
                hour="0",
                day_of_week="*",
                day_of_month="*",
                month_of_year="*",
                timezone=getattr(settings, "CELERY_TIMEZONE", settings.TIME_ZONE),
            )

            PeriodicTask.objects.update_or_create(
                name="Prefill slots daily at midnight",
                defaults={
                    "task": "api.tasks.prefill_slots",
                    "crontab": schedule,
                    "enabled": True,
                    # Prefill the next 7 days; adjust via admin if needed
                    "args": "[7]",
                },
            )

        transaction.on_commit(_create_or_update)
    except Exception:
        # Silently ignore during app import if beat isn't installed or DB isn't ready
        # (e.g., during collectstatic, makemigrations). Admin can manage schedule later.
        pass

class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        # Import models module so the handler function is defined
        import api.models  # noqa

        Booking = apps.get_model("payments", "Booking")
        from api.models import on_booking_status_change

        post_save.connect(
            on_booking_status_change,
            sender=Booking,
            dispatch_uid="api_on_booking_status_change",
            weak=False,
        )

        # keep your _setup_daily_slot_prefill_schedule() hook
        def _handler(**kwargs):
            from .apps import _setup_daily_slot_prefill_schedule
            _setup_daily_slot_prefill_schedule()
        post_migrate.connect(_handler, sender=self)
