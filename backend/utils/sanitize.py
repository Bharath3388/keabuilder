"""Input sanitization utilities for LLM prompts and user input."""

import re


# Patterns that indicate prompt injection attempts
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*",
    r"\[INST\]",
    r"<\|im_start\|>",
    r"<\|system\|>",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def sanitize_prompt(prompt: str, max_length: int = 2000) -> str:
    """Sanitize a user-provided prompt before sending to an LLM.

    - Truncates to max_length
    - Strips common injection patterns
    - Removes control characters
    """
    # Truncate
    prompt = prompt[:max_length]

    # Remove control characters (keep newlines and tabs)
    prompt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", prompt)

    # Flag and strip injection attempts
    prompt = _INJECTION_RE.sub("[filtered]", prompt)

    return prompt.strip()


def sanitize_for_json_prompt(data: dict) -> dict:
    """Sanitize a dict before embedding it in an LLM prompt as JSON.

    Ensures string values don't contain injection attempts.
    """
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_prompt(value, max_length=1000)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_for_json_prompt(value)
        else:
            sanitized[key] = value
    return sanitized
