
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


LANGUAGE_NAMES = {
    "english": "en",
    "hindi": "hi",
    "tamil": "ta",
    "kannada": "kn",
    "telugu": "te",
    "marathi": "mr",
}


def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()
    return value if value else None


def normalize_phone(value):
    """Normalize valid Indian mobile numbers to +91XXXXXXXXXX."""
    value = clean_text(value)

    if not value:
        return None

    digits = re.sub(r"\D", "", value)

    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if len(digits) != 10:
        return None

    if digits[0] not in "6789":
        return None

    return f"+91{digits}"


def normalize_date(value):
    """Return dates in YYYY-MM-DD format."""
    value = clean_text(value)

    if not value:
        return None

    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%Y",
    )

    for date_format in formats:
        try:
            return datetime.strptime(
                value, date_format
            ).date().isoformat()
        except ValueError:
            continue

    raise ValueError("invalid_date")


def normalize_decimal(value):
    """Parse supported currency formats into a two-decimal string."""
    value = clean_text(value)

    if not value:
        return None

    # Remove supported currency prefixes.
    cleaned = re.sub(
        r"^(?:INR|RS\.?|\u20b9)\s*",
        "",
        value,
        flags=re.IGNORECASE
    )

    # Remove thousands separators.
    cleaned = cleaned.replace(",", "").strip()

    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid_decimal") from exc

    if not amount.is_finite() or amount < 0:
        raise ValueError("invalid_decimal")

    amount = amount.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    return str(amount)


def normalize_enum(value, allowed_values):
    """Normalize language names or codes to allowed lowercase values."""
    value = clean_text(value)

    if not value:
        return None

    normalized = value.lower()
    normalized = LANGUAGE_NAMES.get(normalized, normalized)

    allowed = {item.lower() for item in allowed_values}

    if normalized not in allowed:
        raise ValueError("invalid_enum")

    return normalized
