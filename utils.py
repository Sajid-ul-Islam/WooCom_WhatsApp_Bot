import re


def normalize_phone(phone: str) -> str:
    """Strip everything except digits from a phone number for consistent matching."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def clean_html(raw_html: str) -> str:
    """Strip HTML tags from text (e.g. WooCommerce descriptions)."""
    if not raw_html:
        return ""
    return re.sub(r"<[^<]+?>", "", raw_html).strip()
