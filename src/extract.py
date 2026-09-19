"""
Plain-text SI and BL attachment identification and field extraction.

Enhanced with Feature 1 (Field Normalization):
  - Uses expanded label aliases from normalize.py
  - Better handling of field name variations
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

# Import enhanced label aliases from our normalization module
from .normalize import LABEL_ALIASES, normalize_label, get_standard_field


# The 7 core fields used for comparison
FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)

# Fields that may span multiple lines (party names/addresses)
PARTY_FIELDS = {"shipper", "consignee", "notify_party"}

# Values that indicate a field is actually missing
MISSING_MARKERS = {"", "n/a", "na", "tba", "tbd", "unknown", "-", "--", "???", "___"}


@dataclass
class ReviewRequired(Exception):
    """Exception raised when a document needs manual human review."""
    review_reason: str       # Short code for the pipeline
    internal_reason: str     # Detailed reason for debugging
    detail: str              # Human-readable explanation
    
    def __str__(self) -> str:
        return self.detail


def identify_attachments(paths: list[str]) -> dict[str, str]:
    """
    Identify SI and BL attachments by filename pattern.
    Filename should contain _SI or _BL (e.g., document_SI.txt, email_BL.txt)
    
    NOTE: Enhanced attachment validation is now handled by the new
    attachment_validation.py module. This function is kept for backward
    compatibility and simple cases.
    """
    roles: dict[str, list[str]] = {"SI": [], "BL": []}
    unknown: list[str] = []
    
    for path in paths:
        name = Path(path).name
        if re.search(r"_SI(?:\.|_)", name, flags=re.IGNORECASE):
            roles["SI"].append(path)
        elif re.search(r"_BL(?:\.|_)", name, flags=re.IGNORECASE):
            roles["BL"].append(path)
        else:
            unknown.append(path)
    
    if unknown or len(roles["SI"]) > 1 or len(roles["BL"]) > 1:
        raise ReviewRequired(
            "unreadable",
            "ambiguous_attachment_role",
            f"Could not uniquely identify SI and BL attachments; "
            f"unknown={unknown}, roles={roles}",
        )
    
    if not roles["SI"] or not roles["BL"]:
        missing = [role for role in ("SI", "BL") if not roles[role]]
        raise ReviewRequired(
            "missing_attachment",
            "missing_attachment",
            f"Missing required attachment role(s): {', '.join(missing)}",
        )
    
    return {"SI": roles["SI"][0], "BL": roles["BL"][0]}


def _looks_missing(value: str) -> bool:
    """Check if a value looks like it's missing or placeholder text."""
    compact = re.sub(r"\s+", " ", value).strip().casefold()
    return compact in MISSING_MARKERS


def _validate_document_type(text: str, role: str, path: str) -> None:
    """
    Verify that the document content matches the expected role.
    SI should start with "SHIPPING INSTRUCTION"
    BL should start with "BILL OF LADING"
    """
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    expected = "SHIPPING INSTRUCTION" if role == "SI" else "BILL OF LADING"
    
    if expected not in first_line.upper():
        raise ReviewRequired(
            "wrong_doc_type",
            "wrong_document_type",
            f"{path} was assigned as {role}, but its first line is {first_line!r}",
        )


def parse_fields(text: str, role: str, path: str) -> dict[str, str]:
    """
    Parse fields from document text.
    
    Enhanced with Feature 1: Uses expanded label aliases from normalize.py
    so that more label variations are recognized (e.g., "Load Port", "POL",
    "Gross Wt", etc.)
    """
    _validate_document_type(text, role, path)
    
    extracted: dict[str, str] = {}
    active_party_field: str | None = None
    
    for raw_line in text.splitlines():
        # Handle multi-line party fields (continuation lines start with space)
        if active_party_field and raw_line[:1].isspace() and raw_line.strip():
            extracted[active_party_field] = (
                f"{extracted[active_party_field]} {raw_line.strip()}"
            ).strip()
            continue
        
        active_party_field = None
        
        # Skip lines without a colon (label: value format)
        if ":" not in raw_line:
            continue
        
        label, value = raw_line.split(":", 1)
        
        # ENHANCEMENT (Feature 1): Use our enhanced label matching
        # that supports many more aliases
        field = get_standard_field(label)
        
        if not field:
            continue
        
        # Only extract fields we care about
        if field not in FIELDS:
            continue
        
        value = value.strip()
        
        # Check for duplicate conflicting values
        if field in extracted and extracted[field] != value:
            raise ReviewRequired(
                "unreadable",
                "duplicate_conflicting_field",
                f"{path} contains conflicting values for {field}",
            )
        
        extracted[field] = value
        
        # Remember party fields for multi-line continuation
        if field in PARTY_FIELDS:
            active_party_field = field
    
    # Check for missing required fields
    missing = [
        field for field in FIELDS
        if field not in extracted or _looks_missing(extracted[field])
    ]
    
    if missing:
        raise ReviewRequired(
            "missing_value",
            "missing_required_value",
            f"{path} is missing reliable value(s): {', '.join(missing)}",
        )
    
    return extracted


def extract_attachment(inbox: Any, path: str, role: str) -> dict[str, str]:
    """
    Read and parse one supported plain-text attachment.
    
    NOTE: For enhanced validation (corrupted files, unsupported formats,
    size limits, etc.), use the attachment_validation module before
    calling this function.
    """
    # Check file extension
    if Path(path).suffix.casefold() != ".txt":
        raise ReviewRequired(
            "unreadable",
            "unsupported_attachment_format",
            f"Basic version supports .txt only; cannot read {path}",
        )
    
    # Try to read the file
    try:
        raw = inbox.read_bytes(path)
    except (OSError, ValueError) as exc:
        raise ReviewRequired(
            "unreadable",
            "attachment_read_failed",
            f"Could not read {path}: {exc}",
        ) from exc
    
    # Check for empty file
    if not raw:
        raise ReviewRequired(
            "unreadable",
            "empty_attachment",
            f"Attachment is empty: {path}",
        )
    
    # Try to decode as UTF-8
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ReviewRequired(
            "unreadable",
            "attachment_decode_failed",
            f"Could not decode {path} as UTF-8",
        ) from exc
    
    return parse_fields(text, role, path)
