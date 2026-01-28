import re
from typing import Tuple, Optional

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")

INJECTION_PATTERNS = [
    r"ignore (all )?instructions",
    r"reveal (the )?(system|developer) prompt",
    r"show (me )?(your )?(system|developer) prompt",
    r"you are now",
    r"do anything now",
    r"jailbreak",
]

INJECTION_RE = re.compile("|".join(f"({p})" for p in INJECTION_PATTERNS), re.IGNORECASE)

def redact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text

def check_injection(text: str) -> Tuple[bool, Optional[str]]:
    if INJECTION_RE.search(text or ""):
        return True, "prompt_injection"
    return False, None
