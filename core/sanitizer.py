"""
Sensitive Data Sanitizer & Redactor for The Iron Throne RPG.
Ensures zero leakage of tokens, passwords, payment info, and credentials.
"""
import re
from typing import Optional
from config import BOT_TOKEN

# 1. Telegram Bot Token pattern
BOT_TOKEN_REGEX = re.compile(r"\b\d{8,11}:[A-Za-z0-9_-]{35}\b")

# 2. Database URI credentials pattern: postgresql+asyncpg://user:pass@host/db
DB_URL_REGEX = re.compile(r"://([^:@]+):([^@]+)@")

# 3. Common secret key-value assignments
SECRET_KV_REGEX = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api_key|apikey|access_token|auth_token|token|card_number|cvv|cvc)\s*[:=]\s*['\"]?([^\s,;'\"]+)['\"]?"
)

# 4. Bank card numbers (16 digits formatted or consecutive, Visa, Mastercard, Uzcard, Humo)
CARD_NUMBER_REGEX = re.compile(
    r"\b(?:\d{4}[ -]?){3}\d{4}\b|\b\d{16}\b"
)

# 5. Telegram WebApp hash / initData tokens
TG_HASH_REGEX = re.compile(r"\bhash=[a-fA-F0-9]{64}\b")
TG_AUTH_DATE_REGEX = re.compile(r"auth_date=\d+")

# 6. Authorization header values
AUTH_HEADER_REGEX = re.compile(r"(?i)\b(Bearer|tma)\s+([A-Za-z0-9_\-\.+=%]+)")


def sanitize_sensitive_data(text: Optional[str]) -> str:
    """
    Scans any input text, log, or stack trace and replaces confidential data with [REDACTED].
    """
    if not text:
        return ""

    sanitized = str(text)

    # A. Redact specific configured BOT_TOKEN if present
    if BOT_TOKEN and len(BOT_TOKEN) > 10:
        sanitized = sanitized.replace(BOT_TOKEN, "[BOT_TOKEN_REDACTED]")

    # B. Telegram Bot Token regex
    sanitized = BOT_TOKEN_REGEX.sub("[BOT_TOKEN_REDACTED]", sanitized)

    # C. Database Connection String Password
    sanitized = DB_URL_REGEX.sub(r"://\1:[PASSWORD_REDACTED]@", sanitized)

    # D. Key-value secrets
    sanitized = SECRET_KV_REGEX.sub(r"\1=[REDACTED]", sanitized)

    # E. Credit / Bank Card Numbers
    sanitized = CARD_NUMBER_REGEX.sub("[CARD_NUMBER_REDACTED]", sanitized)

    # F. Telegram Auth Tokens / Hashes
    sanitized = TG_HASH_REGEX.sub("hash=[HASH_REDACTED]", sanitized)
    sanitized = AUTH_HEADER_REGEX.sub(r"\1 [AUTH_TOKEN_REDACTED]", sanitized)

    return sanitized


def truncate_stack_trace(stack_trace: Optional[str], max_lines: int = 8) -> str:
    """
    Truncates a verbose Python stack trace to the most relevant trailing frames,
    sanitizing any sensitive paths/tokens.
    """
    if not stack_trace:
        return ""

    sanitized = sanitize_sensitive_data(stack_trace)
    lines = [l for l in sanitized.splitlines() if l.strip()]

    if len(lines) <= max_lines:
        return "\n".join(lines)

    # Keep the first error header line, then the last (max_lines - 1) lines
    tail = lines[-(max_lines - 1):]
    return lines[0] + "\n  ... [ko'p qatorlar qisqartirildi] ...\n" + "\n".join(tail)


# Alias for backward compatibility
sanitize_text = sanitize_sensitive_data

