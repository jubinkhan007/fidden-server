import re
from typing import Optional

_PHONE_ATTRS = ("phone_number", "phone", "mobile", "mobile_number", "tel")
E164_RE = re.compile(r"^\+\d{7,15}$")

def _to_e164(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "").replace("-", "")
    return s if E164_RE.match(s) else None

def get_user_phone(user) -> Optional[str]:
    """Return an E.164 phone from user or related profile, else None."""
    if not user:
        return None
    for a in _PHONE_ATTRS:
        p = _to_e164(getattr(user, a, None))
        if p:
            return p
    prof = getattr(user, "profile", None) or getattr(user, "userprofile", None)
    if prof:
        for a in _PHONE_ATTRS:
            p = _to_e164(getattr(prof, a, None))
            if p:
                return p
    return None
