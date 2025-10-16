# fidden/celery.py
import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")

app = Celery("fidden")
# Read config from Django settings, using `CELERY_` namespace
app.config_from_object("django.conf:settings", namespace="CELERY")
# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

# Celery Beat schedule: periodic tasks
app.conf.beat_schedule = {
    # Prefill slots daily at midnight
    "prefill-slots-daily": {
        "task": "api.tasks.prefill_slots",
        "schedule": crontab(hour=0, minute=0),
        "args": (7,),
    },
    # Send reminders every 15 minutes
    "send-upcoming-reminders": {
        "task": "api.tasks.send_upcoming_slot_reminders",
        "schedule": crontab(minute="*/15"),
        "args": (30,),
    },
    # Cleanup cancelled bookings daily at 1 AM
    "cleanup-cancelled-bookings": {
        "task": "api.tasks.cleanup_old_cancelled_bookings",
        "schedule": crontab(hour=1, minute=0),
        "args": (7, 1000),
    },
    # Complete bookings every 5 minutes
    "complete-bookings-every-minute": {
        "task": "payments.tasks.complete_past_bookings",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
    # Send bookings reminders every minutes
    "send-booking-reminders": {
        "task": "payments.tasks.send_booking_reminders",
        "schedule": crontab(minute="*"),  # every 60 seconds
    },
    "calculate-analytics-daily": {
        "task": "api.tasks.calculate_analytics",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'generate-weekly-ai-reports': {
        'task': 'api.tasks.generate_weekly_ai_reports',
        'schedule': crontab(day_of_week='sunday', hour=20, minute=0),  # Every Sunday at 8 PM
    },
    'send-smart-rebooking-prompts': {
        'task': 'api.tasks.send_smart_rebooking_prompts',
        'schedule': crontab(hour=10, minute=0),  # Every day at 10 AM
    },
    'send-auto-followups': {
        'task': 'api.tasks.send_auto_followups',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    'reengage-ghost-clients': {
        'task': 'api.tasks.reengage_ghost_clients',
        'schedule': crontab(day_of_week='monday', hour=11, minute=0),  # Every Monday at 11 AM
    },
}
