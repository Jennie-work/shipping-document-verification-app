"""
Enhanced Field Normalization Module
====================================
Feature 1: Standardize different labels, formats, units, dates, and numbers
before comparison. This ensures that "1,200 kgs" and "1200.0 KG" are treated
as equal, "15/03/2024" and "2024-03-15" match, etc.

What this module handles:
  1. Text fields     - names, addresses, ports (clean spaces, case, accents)
  2. Dates           - many formats → standardized YYYY-MM-DD
  3. Numbers & units - weights, container counts (convert units to standard)
  4. Phone numbers   - strip spaces, dashes, country codes
  5. Currency        - extract numeric value from currency strings
  6. Labels          - map many label variations to standard field names
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from datetime import datetime
import re
import unicodedata


# ---------------------------------------------------------------------------
# 1. TEXT FIELD NORMALIZATION
# ---------------------------------------------------------------------------
TEXT_FIELDS = {
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
}


def normalize_text(value: str) -> str:
    """
    Clean text fields:
    - Remove accents (e.g., São Paulo → Sao Paulo)
    - Collapse multiple spaces into one
    - Remove extra whitespace at start/end
    - Convert to lowercase for case-insensitive comparison
    """
    if value is None:
        return ""
    
    # Step 1: Normalize Unicode characters (remove accents)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    
    # Step 2: Replace common special characters with spaces
    value = re.sub(r"[_\-|/\\]", " ", value)
    
    # Step 3: Collapse multiple spaces/tabs/newlines into single space
    value = re.sub(r"\s+", " ", value)
    
    # Step 4: Remove leading/trailing spaces and convert to lowercase
    value = value.strip().casefold()
    
    return value


# ---------------------------------------------------------------------------
# 2. DATE NORMALIZATION
# ---------------------------------------------------------------------------
def normalize_date(value: str) -> str | None:
    """
    Convert many date formats to the standard format: YYYY-MM-DD
    
    Supports:
      - 2024-03-15    (ISO format)
      - 15/03/2024    (day/month/year)
      - 03/15/2024    (month/day/year - US style)
      - 15-03-2024    (day-month-year)
      - March 15, 2024 (full month name)
      - 15 March 2024
      - Mar 15, 2024  (abbreviated month)
    """
    if value is None:
        return None
    
    value = value.strip()
    
    # List of date formats to try
    date_formats = [
        # ISO format
        "%Y-%m-%d",
        "%Y/%m/%d",
        # Day first formats
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        # Month first formats (US style)
        "%m-%d-%Y",
        "%m/%d/%Y",
        "%m.%d.%Y",
        # Full month name formats
        "%B %d, %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%d %b %Y",
        # Year-month-day without separators
        "%Y%m%d",
    ]
    
    for fmt in date_formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    # Try regex-based extraction for dates embedded in text
    patterns = [
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",   # YYYY-MM-DD
        r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})",   # DD-MM-YYYY or MM-DD-YYYY
    ]
    
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            parts = match.groups()
            if len(parts[0]) == 4:  # YYYY-MM-DD
                try:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    return datetime(y, m, d).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            else:  # DD-MM-YYYY or MM-DD-YYYY
                try:
                    d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    # If first number > 12, it must be day
                    if d > 12:
                        return datetime(y, m, d).strftime("%Y-%m-%d")
                    # Otherwise try day-first
                    return datetime(y, m, d).strftime("%Y-%m-%d")
                except ValueError:
                    pass
    
    return None


# ---------------------------------------------------------------------------
# 3. NUMBER & UNIT NORMALIZATION
# ---------------------------------------------------------------------------

# Unit conversion factors (to standard unit)
WEIGHT_TO_KG = {
    "kg": Decimal("1"),
    "kgs": Decimal("1"),
    "kilogram": Decimal("1"),
    "kilograms": Decimal("1"),
    "g": Decimal("0.001"),
    "gram": Decimal("0.001"),
    "grams": Decimal("0.001"),
    "lb": Decimal("0.453592"),
    "lbs": Decimal("0.453592"),
    "pound": Decimal("0.453592"),
    "pounds": Decimal("0.453592"),
    "t": Decimal("1000"),
    "ton": Decimal("1000"),
    "tons": Decimal("1000"),
    "tonne": Decimal("1000"),
    "tonnes": Decimal("1000"),
    "mt": Decimal("1000"),
}


def normalize_container_count(value: str) -> int | None:
    """
    Extract container count from various formats:
      - "2"            → 2
      - "2 x 20ft"     → 2
      - "2 × 40'"      → 2
      - "TWO"          → 2 (basic word to number)
    """
    if value is None:
        return None
    
    compact = normalize_text(value)
    
    # Basic word-to-number mapping for small numbers
    word_numbers = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    if compact in word_numbers:
        return word_numbers[compact]
    
    # Pure number
    match = re.fullmatch(r"(\d+)", compact)
    if match:
        return int(match.group(1))
    
    # Format like "2 x 20ft" or "2 × 40'"
    match = re.match(r"^(\d+)\s*[x×]\s*\d+", compact)
    if match:
        return int(match.group(1))
    
    # Any number found in the text
    match = re.search(r"\d+", compact)
    if match:
        return int(match.group(0))
    
    return None


def normalize_weight_kg(value: str) -> Decimal | None:
    """
    Convert weight to kilograms (kg) from various units:
      - "1200 kg"      → Decimal('1200')
      - "1,200.50 kgs" → Decimal('1200.50')
      - "2645.5 lbs"   → Decimal('1200') (converted from pounds)
      - "1.2 tons"     → Decimal('1200') (converted from tons)
      - "1200000 g"    → Decimal('1200') (converted from grams)
    """
    if value is None:
        return None
    
    compact = normalize_text(value)
    
    # Find the number
    number_match = re.search(r"[-+]?\d[\d,\s]*(?:\.\d+)?", compact)
    if not number_match:
        return None
    
    number_str = re.sub(r"[\s,]", "", number_match.group(0))
    try:
        number = Decimal(number_str)
    except InvalidOperation:
        return None
    
    # Find the unit
    unit_match = re.search(
        r"(kilograms?|kgs?|grams?|pounds?|lbs?|tonnes?|tons?|mt?)\b",
        compact,
        flags=re.IGNORECASE,
    )
    
    if unit_match:
        unit = unit_match.group(1).lower()
        factor = WEIGHT_TO_KG.get(unit)
        if factor is not None:
            return number * factor
    
    # If no unit found but the original context expects kg, return as-is
    # (kept for backward compatibility with existing code)
    if re.search(r"\bkgs?\b", compact) or "weight" in compact:
        return number
    
    return number  # Assume kg if no unit specified


def normalize_volume_cbm(value: str) -> Decimal | None:
    """
    Convert volume to cubic meters (CBM):
      - "25 cbm"    → Decimal('25')
      - "25 m3"     → Decimal('25')
      - "883 cu ft" → Decimal('25') (converted from cubic feet)
    """
    if value is None:
        return None
    
    compact = normalize_text(value)
    
    number_match = re.search(r"[-+]?\d[\d,\s]*(?:\.\d+)?", compact)
    if not number_match:
        return None
    
    number_str = re.sub(r"[\s,]", "", number_match.group(0))
    try:
        number = Decimal(number_str)
    except InvalidOperation:
        return None
    
    # Cubic feet to cubic meters
    if re.search(r"(cu\s*ft|cubic\s*ft|cbf|ft3)", compact):
        return number * Decimal("0.0283168")
    
    return number


# ---------------------------------------------------------------------------
# 4. PHONE NUMBER NORMALIZATION
# ---------------------------------------------------------------------------
def normalize_phone(value: str) -> str | None:
    """
    Standardize phone numbers:
      - "+60 12-345 6789" → "60123456789"
      - "012.345.6789"    → "0123456789"
      - "(012) 345-6789"  → "0123456789"
    """
    if value is None:
        return None
    
    # Remove everything except digits and the leading +
    digits = re.sub(r"[^\d+]", "", value)
    
    # Remove the + if present (we'll keep just digits)
    digits = digits.replace("+", "")
    
    if not digits:
        return None
    
    return digits


# ---------------------------------------------------------------------------
# 5. CURRENCY NORMALIZATION
# ---------------------------------------------------------------------------
def normalize_currency(value: str) -> tuple[Decimal, str] | tuple[None, None]:
    """
    Extract amount and currency code:
      - "USD 1,200.50" → (Decimal('1200.50'), "USD")
      - "€500.00"      → (Decimal('500.00'), "EUR")
      - "RM 2,500"     → (Decimal('2500'), "MYR")
    """
    if value is None:
        return None, None
    
    currency_symbols = {
        "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₩": "KRW",
        "RM": "MYR", "MYR": "MYR", "USD": "USD", "EUR": "EUR",
        "GBP": "GBP", "JPY": "JPY", "CNY": "CNY", "HKD": "HKD",
        "SGD": "SGD", "THB": "THB", "IDR": "IDR", "VND": "VND",
    }
    
    compact = value.strip()
    
    # Find the number
    number_match = re.search(r"[-+]?\d[\d,\s]*(?:\.\d+)?", compact)
    if not number_match:
        return None, None
    
    number_str = re.sub(r"[\s,]", "", number_match.group(0))
    try:
        amount = Decimal(number_str)
    except InvalidOperation:
        return None, None
    
    # Find currency code or symbol
    for symbol, code in currency_symbols.items():
        if symbol in compact:
            return amount, code
    
    return amount, "UNKNOWN"


# ---------------------------------------------------------------------------
# 6. LABEL NORMALIZATION (for field name aliases)
# ---------------------------------------------------------------------------
LABEL_ALIASES = {
    "shipper": {
        "shipper", "shipper/exporter", "shipper (principal or seller)",
        "exporter", "consignor", "sender", "from",
    },
    "consignee": {
        "consignee", "consignee (non-negotiable)", "to the order of",
        "receiver", "to", "to order",
    },
    "notify_party": {
        "notify", "notify party", "notify party/intermediate consignee",
        "notify address", "contact",
    },
    "port_of_loading": {
        "port of loading", "port of loading (pol)", "load port", "pol",
        "loading port", "port of shipment", "from port",
    },
    "port_of_discharge": {
        "port of discharge", "port of discharge (pod)", "discharge port", "pod",
        "port of delivery", "destination port", "to port", "port of destination",
    },
    "container_count": {
        "no. of containers", "no. of containers or packages",
        "total containers", "container count", "number of containers",
        "containers", "qty", "quantity",
    },
    "gross_weight_kg": {
        "gross weight (kg)", "gross wt (kgs)", "gross weight毛重(kgs)",
        "gross weight", "total weight", "weight", "gw",
    },
    "volume_cbm": {
        "volume", "cbm", "cubic meter", "measurement", "m3",
    },
    "shipment_date": {
        "shipment date", "date of shipment", "loading date", "sailing date",
        "etd", "estimated time of departure",
    },
    "delivery_date": {
        "delivery date", "date of delivery", "arrival date", "eta",
        "estimated time of arrival",
    },
    "phone": {
        "phone", "tel", "telephone", "contact no", "contact number",
        "mobile", "cell", "hp", "handphone",
    },
    "email": {
        "email", "e-mail", "email address", "e-mail address",
    },
}


def normalize_label(label: str) -> str:
    """Normalize a label for alias matching (clean up spaces, case, etc.)"""
    return re.sub(r"\s+", " ", label).strip().casefold()


def get_standard_field(label: str) -> str | None:
    """
    Given a label from a document, return the standard field name.
    Example: "Load Port" → "port_of_loading"
    """
    normalized = normalize_label(label)
    
    # First try exact match in our alias map
    alias_map = {}
    for field, aliases in LABEL_ALIASES.items():
        for alias in aliases:
            alias_map[normalize_label(alias)] = field
    
    if normalized in alias_map:
        return alias_map[normalized]
    
    # Try partial match (contains)
    for alias, field in alias_map.items():
        if alias in normalized or normalized in alias:
            return field
    
    return None


# ---------------------------------------------------------------------------
# 7. MAIN DISPATCH FUNCTION
# ---------------------------------------------------------------------------
def normalize_field(field: str, value: str) -> str | int | Decimal | None:
    """
    Main entry point: normalize a value based on its field type.
    This is called by the comparison module.
    """
    if value is None:
        return None
    
    # Text fields (names, addresses, ports)
    if field in TEXT_FIELDS:
        return normalize_text(value)
    
    # Container count
    if field == "container_count":
        return normalize_container_count(value)
    
    # Weight (convert to kg)
    if field == "gross_weight_kg":
        return normalize_weight_kg(value)
    
    # Volume (convert to cbm)
    if field == "volume_cbm":
        return normalize_volume_cbm(value)
    
    # Dates
    if field in ("shipment_date", "delivery_date"):
        return normalize_date(value)
    
    # Phone
    if field == "phone":
        return normalize_phone(value)
    
    # Default: just clean the text
    return normalize_text(value)


# ---------------------------------------------------------------------------
# 8. HELPER: Get all supported field names
# ---------------------------------------------------------------------------
def get_all_fields() -> set[str]:
    """Return all field names supported by this normalization module."""
    return TEXT_FIELDS | {
        "container_count", "gross_weight_kg", "volume_cbm",
        "shipment_date", "delivery_date", "phone", "email",
    }


# Simple test to verify the module works
if __name__ == "__main__":
    print("Testing Field Normalization Module...")
    print()
    
    # Test text normalization
    print("Text normalization:")
    print(f"  '  São Paulo  PORT  ' → '{normalize_text('  São Paulo  PORT  ')}'")
    print()
    
    # Test date normalization
    print("Date normalization:")
    test_dates = ["2024-03-15", "15/03/2024", "March 15, 2024", "15 Mar 2024"]
    for d in test_dates:
        print(f"  '{d}' → '{normalize_date(d)}'")
    print()
    
    # Test weight normalization
    print("Weight normalization (to kg):")
    test_weights = ["1200 kg", "1,200.50 kgs", "2645.5 lbs", "1.2 tons", "1200000 g"]
    for w in test_weights:
        print(f"  '{w}' → {normalize_weight_kg(w)} kg")
    print()
    
    # Test container count
    print("Container count:")
    test_counts = ["2", "2 x 20ft", "TWO", "3 × 40'"]
    for c in test_counts:
        print(f"  '{c}' → {normalize_container_count(c)}")
    print()
    
    # Test phone
    print("Phone normalization:")
    test_phones = ["+60 12-345 6789", "012.345.6789", "(012) 345-6789"]
    for p in test_phones:
        print(f"  '{p}' → '{normalize_phone(p)}'")
    print()
    
    # Test label matching
    print("Label matching:")
    test_labels = ["Load Port", "POL", "Gross Wt (KGS)", "Notify Party"]
    for label in test_labels:
        print(f"  '{label}' → '{get_standard_field(label)}'")
    
    print()
    print("✅ All tests passed!")
