"""
Shipping Document Verification - Source Package

Modules:
  - classify: Email classification (BL_COMPARISON, SI_REQUEST, etc.)
  - extract: Field extraction from document text
  - compare: SI vs BL document comparison
  - normalize: Field normalization (Feature 1) - standardizes labels, 
               dates, numbers, units, text formats
  - attachment_validation: Attachment validation (Feature 2) - checks 
               for missing, corrupted, unsupported, or incorrect files
  - pipeline: Main processing pipeline that ties everything together
"""

# Core modules
from . import classify
from . import extract
from . import compare
from . import normalize
from . import attachment_validation  # NEW: Feature 2
from . import pipeline

# Convenience imports for easy access
from .normalize import (
    normalize_text,
    normalize_date,
    normalize_weight_kg,
    normalize_container_count,
    normalize_phone,
    normalize_currency,
    normalize_field,
    get_standard_field,
    LABEL_ALIASES,
)

from .attachment_validation import (
    validate_attachments,
    quick_validate_single,
    get_supported_formats,
    ValidationResult,
    AttachmentIssue,
)

from .pipeline import process_inbox, validate_submission
from .extract import ReviewRequired, extract_attachment, identify_attachments

__all__ = [
    # Modules
    "classify",
    "extract",
    "compare",
    "normalize",
    "attachment_validation",
    "pipeline",
    # Feature 1: Normalization functions
    "normalize_text",
    "normalize_date",
    "normalize_weight_kg",
    "normalize_container_count",
    "normalize_phone",
    "normalize_currency",
    "normalize_field",
    "get_standard_field",
    "LABEL_ALIASES",
    # Feature 2: Attachment validation
    "validate_attachments",
    "quick_validate_single",
    "get_supported_formats",
    "ValidationResult",
    "AttachmentIssue",
    # Pipeline
    "process_inbox",
    "validate_submission",
    # Exceptions
    "ReviewRequired",
]
