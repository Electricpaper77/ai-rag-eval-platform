import re
from typing import Tuple, Optional

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

INJECTION_PATTERNS = [
    r"ignore (all )?instructions",
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (all )?(previous|prior|above) instructions",
    r"reveal (the )?(system|developer) prompt",
    r"(print|dump|exfiltrate) (the )?(system|developer) prompt",
    r"show (me )?(your )?(system|developer) prompt",
    r"you are now",
    r"do anything now",
    r"jailbreak",
    r"bypass (the )?(policy|safety|guardrails?)",
]

INJECTION_RE = re.compile("|".join(f"({p})" for p in INJECTION_PATTERNS), re.IGNORECASE)

def redact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = SSN_RE.sub("[REDACTED_SSN]", text)
    text = CREDIT_CARD_RE.sub("[REDACTED_CARD]", text)
    return text

def check_injection(text: str) -> Tuple[bool, Optional[str]]:
    normalized = re.sub(r"[\W_]+", " ", text or "").strip()
    if INJECTION_RE.search(normalized):
        return True, "prompt_injection"
    return False, None
