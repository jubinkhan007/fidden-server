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