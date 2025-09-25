def extract_validation_error_message(error):
    """
    Extract single error message from DRF ValidationError
    so we can return {"detail": "..."} consistently.
    """
    if hasattr(error, "detail"):
        if isinstance(error.detail, list):
            return str(error.detail[0]) if error.detail else "Validation error"
        elif isinstance(error.detail, dict):
            first_key = next(iter(error.detail))
            messages = error.detail[first_key]
            if isinstance(messages, list) and messages:
                return str(messages[0])
            return str(messages)
        return str(error.detail)
    return str(error)

# def send_reminder_email(user_email, reminder_message, subject="Reminder Notification"):
#     """
#     Send a reminder email to the user.
    
#     Args:
#         user_email (str): Recipient's email address
#         reminder_message (str): Body text of the reminder
#         subject (str): Email subject (default: "Reminder Notification")
#     """
#     from_email = "no-reply@example.com"
#     recipient_list = [user_email]

#     send_mail(subject, reminder_message, from_email, recipient_list)