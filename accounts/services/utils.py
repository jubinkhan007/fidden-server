import random
from django.conf import settings
from django.core.mail import send_mail

def generate_otp():
    """Generate a 6-digit numeric OTP as string with leading zeros if needed."""
    return f"{random.randint(0, 999999):06d}"


def send_otp_email(user_email, otp):
    """Send the OTP email to the user."""
    subject = "Your OTP Code"
    message = f"Your OTP code is {otp}"
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user_email]

    send_mail(subject, message, from_email, recipient_list)
