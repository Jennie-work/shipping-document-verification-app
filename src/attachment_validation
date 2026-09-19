"""
Attachment Validation Module
=============================
Feature 2: Check attachments for common issues before processing.

This module validates email attachments to catch problems early:
  1. Missing attachments      - required files (SI, BL) not found
  2. Corrupted files          - empty files, can't be read, encoding issues
  3. Unsupported formats      - file types we can't process
  4. Incorrect document types - file labeled as SI but content is BL
  5. Duplicate attachments    - multiple files for the same role
  6. File size issues         - files too large or suspiciously small
  7. Unknown attachments      - files we can't identify

Each validation check returns a structured result so the pipeline can
decide whether to flag for manual review.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# File extensions we can process
SUPPORTED_EXTENSIONS = {".txt"}

# File extensions that are explicitly unsupported (to give better error messages)
UNSUPPORTED_EXTENSIONS = {
    ".pdf": "PDF files are not supported in the basic version. Please convert to .txt first.",
    ".doc": "Word documents (.doc) are not supported. Please convert to .txt first.",
    ".docx": "Word documents (.docx) are not supported. Please convert to .txt first.",
    ".jpg": "Image files (.jpg) are not supported. Please use OCR to convert to .txt.",
    ".jpeg": "Image files (.jpeg) are not supported. Please use OCR to convert to .txt.",
    ".png": "Image files (.png) are not supported. Please use OCR to convert to .txt.",
    ".xlsx": "Excel files (.xlsx) are not supported. Please convert to .txt first.",
    ".csv": "CSV files are not supported for document verification.",
    ".zip": "ZIP archives are not supported. Please extract files first.",
}

# Maximum file size (10 MB in bytes)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Minimum file size (10 bytes - anything smaller is likely empty/corrupted)
MIN_FILE_SIZE = 10  # bytes

# Required attachment roles for BL comparison
REQUIRED_ROLES = {"SI", "BL"}


# ---------------------------------------------------------------------------
# Data structures for validation results
# ---------------------------------------------------------------------------
@dataclass
class AttachmentIssue:
    """Represents a single issue found with an attachment."""
    severity: str       # "error" or "warning"
    issue_type: str     # e.g., "missing_attachment", "corrupted_file"
    message: str        # Human-readable description
    filename: str = ""  # Which file has the issue


@dataclass
class ValidationResult:
    """Complete result of attachment validation."""
    valid: bool                         # True if no blocking errors
    issues: list[AttachmentIssue]       # All issues found
    identified_roles: dict[str, str]    # role → filepath mapping (if successful)
    
    def has_errors(self) -> bool:
        """Check if there are any error-level issues."""
        return any(issue.severity == "error" for issue in self.issues)
    
    def has_warnings(self) -> bool:
        """Check if there are any warning-level issues."""
        return any(issue.severity == "warning" for issue in self.issues)
    
    def get_error_messages(self) -> list[str]:
        """Get all error messages as a list."""
        return [issue.message for issue in self.issues if issue.severity == "error"]
    
    def get_review_reason(self) -> str | None:
        """
        Map the most severe issue to a review reason code that the pipeline expects.
        Returns one of: "missing_attachment", "unreadable", "wrong_doc_type", or None
        """
        error_types = [issue.issue_type for issue in self.issues if issue.severity == "error"]
        
        if not error_types:
            return None
        
        # Priority order for review reasons
        priority = [
            "missing_attachment",
            "wrong_doc_type",
            "unsupported_format",
            "corrupted_file",
            "empty_file",
            "encoding_error",
            "file_too_large",
            "duplicate_attachment",
            "unknown_attachment",
        ]
        
        for reason in priority:
            if reason in error_types:
                # Map to pipeline-expected review reasons
                mapping = {
                    "missing_attachment": "missing_attachment",
                    "wrong_doc_type": "wrong_doc_type",
                    "unsupported_format": "unreadable",
                    "corrupted_file": "unreadable",
                    "empty_file": "unreadable",
                    "encoding_error": "unreadable",
                    "file_too_large": "unreadable",
                    "duplicate_attachment": "unreadable",
                    "unknown_attachment": "unreadable",
                }
                return mapping.get(reason, "unreadable")
        
        return "unreadable"


# ---------------------------------------------------------------------------
# Individual validation checks
# ---------------------------------------------------------------------------

def _identify_role_by_filename(filepath: str) -> str | None:
    """
    Try to identify if an attachment is SI or BL based on its filename.
    Returns "SI", "BL", or None if unknown.
    """
    name = Path(filepath).name
    
    # Check for SI pattern: _SI. or _SI_ or -SI. etc.
    if re.search(r"[_-]SI(?:[._-]|$)", name, flags=re.IGNORECASE):
        return "SI"
    
    # Check for BL pattern: _BL. or _BL_ or -BL. etc.
    if re.search(r"[_-]BL(?:[._-]|$)", name, flags=re.IGNORECASE):
        return "BL"
    
    # Also check if filename starts with SI or BL
    if re.match(r"^SI[._-]", name, flags=re.IGNORECASE):
        return "SI"
    if re.match(r"^BL[._-]", name, flags=re.IGNORECASE):
        return "BL"
    
    return None


def check_file_extension(filepath: str) -> AttachmentIssue | None:
    """
    Check if the file extension is supported.
    Returns an issue if unsupported, None if OK.
    """
    suffix = Path(filepath).suffix.lower()
    
    if suffix in SUPPORTED_EXTENSIONS:
        return None
    
    if suffix in UNSUPPORTED_EXTENSIONS:
        return AttachmentIssue(
            severity="error",
            issue_type="unsupported_format",
            message=UNSUPPORTED_EXTENSIONS[suffix],
            filename=Path(filepath).name,
        )
    
    return AttachmentIssue(
        severity="error",
        issue_type="unsupported_format",
        message=f"Unsupported file format: '{suffix}'. Only .txt files are supported.",
        filename=Path(filepath).name,
    )


def check_file_size(filepath: str, inbox: Any) -> AttachmentIssue | None:
    """
    Check if the file size is within acceptable limits.
    Returns an issue if too small/empty or too large, None if OK.
    """
    try:
        raw = inbox.read_bytes(filepath)
        size = len(raw)
    except (OSError, ValueError):
        return AttachmentIssue(
            severity="error",
            issue_type="corrupted_file",
            message=f"Cannot read file: {Path(filepath).name}",
            filename=Path(filepath).name,
        )
    
    if size == 0:
        return AttachmentIssue(
            severity="error",
            issue_type="empty_file",
            message=f"File is empty: {Path(filepath).name}",
            filename=Path(filepath).name,
        )
    
    if size < MIN_FILE_SIZE:
        return AttachmentIssue(
            severity="error",
            issue_type="corrupted_file",
            message=f"File is suspiciously small ({size} bytes), likely corrupted: {Path(filepath).name}",
            filename=Path(filepath).name,
        )
    
    if size > MAX_FILE_SIZE:
        return AttachmentIssue(
            severity="error",
            issue_type="file_too_large",
            message=f"File is too large ({size / (1024*1024):.1f} MB). Maximum allowed is 10 MB: {Path(filepath).name}",
            filename=Path(filepath).name,
        )
    
    return None


def check_file_encoding(filepath: str, inbox: Any) -> AttachmentIssue | None:
    """
    Check if the file can be decoded as UTF-8 text.
    Returns an issue if encoding fails, None if OK.
    """
    try:
        raw = inbox.read_bytes(filepath)
    except (OSError, ValueError):
        return AttachmentIssue(
            severity="error",
            issue_type="corrupted_file",
            message=f"Cannot read file: {Path(filepath).name}",
            filename=Path(filepath).name,
        )
    
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return AttachmentIssue(
            severity="error",
            issue_type="encoding_error",
            message=f"File encoding is not UTF-8. Please save as UTF-8 text: {Path(filepath).name}",
            filename=Path(filepath).name,
        )
    
    return None


def check_document_type(filepath: str, inbox: Any, expected_role: str) -> AttachmentIssue | None:
    """
    Check if the document content matches the expected role (SI or BL).
    SI documents should start with "SHIPPING INSTRUCTION"
    BL documents should start with "BILL OF LADING"
    
    Returns an issue if there's a mismatch, None if OK.
    """
    try:
        raw = inbox.read_bytes(filepath)
        text = raw.decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return AttachmentIssue(
            severity="error",
            issue_type="corrupted_file",
            message=f"Cannot read file to verify document type: {Path(filepath).name}",
            filename=Path(filepath).name,
        )
    
    # Get the first non-empty line
    first_line = ""
    for line in text.splitlines():
        if line.strip():
            first_line = line.strip().upper()
            break
    
    expected_header = "SHIPPING INSTRUCTION" if expected_role == "SI" else "BILL OF LADING"
    other_header = "BILL OF LADING" if expected_role == "SI" else "SHIPPING INSTRUCTION"
    other_role = "BL" if expected_role == "SI" else "SI"
    
    if expected_header not in first_line:
        if other_header in first_line:
            return AttachmentIssue(
                severity="error",
                issue_type="wrong_doc_type",
                message=f"File labeled as {expected_role} but content looks like {other_role}. "
                        f"First line: '{first_line[:80]}'",
                filename=Path(filepath).name,
            )
        else:
            return AttachmentIssue(
                severity="warning",
                issue_type="wrong_doc_type",
                message=f"Cannot verify {expected_role} document type. "
                        f"Expected header containing '{expected_header}', but found: '{first_line[:80]}'",
                filename=Path(filepath).name,
            )
    
    return None


# ---------------------------------------------------------------------------
# Main validation function
# ---------------------------------------------------------------------------

def validate_attachments(
    attachment_paths: list[str],
    inbox: Any,
    require_both: bool = True,
) -> ValidationResult:
    """
    Run all validation checks on a list of attachment paths.
    
    Args:
        attachment_paths: List of file paths to validate
        inbox: The inbox object that can read file bytes
        require_both: If True, both SI and BL must be present
    
    Returns:
        ValidationResult with all issues found and identified roles
    """
    issues: list[AttachmentIssue] = []
    roles: dict[str, list[str]] = {"SI": [], "BL": []}
    unknown: list[str] = []
    
    # Step 1: Identify roles by filename
    for path in attachment_paths:
        role = _identify_role_by_filename(path)
        if role == "SI":
            roles["SI"].append(path)
        elif role == "BL":
            roles["BL"].append(path)
        else:
            unknown.append(path)
    
    # Step 2: Check for unknown attachments
    if unknown:
        issues.append(AttachmentIssue(
            severity="warning",
            issue_type="unknown_attachment",
            message=f"Could not identify the role of these attachments: "
                    f"{', '.join(Path(p).name for p in unknown)}",
        ))
    
    # Step 3: Check for missing required attachments
    if require_both:
        for role in REQUIRED_ROLES:
            if not roles[role]:
                issues.append(AttachmentIssue(
                    severity="error",
                    issue_type="missing_attachment",
                    message=f"Missing required {role} attachment. "
                            f"Filename should contain '_{role}' (e.g., 'document_SI.txt')",
                ))
    
    # Step 4: Check for duplicate attachments (multiple files for same role)
    for role in REQUIRED_ROLES:
        if len(roles[role]) > 1:
            issues.append(AttachmentIssue(
                severity="error",
                issue_type="duplicate_attachment",
                message=f"Multiple {role} attachments found: "
                        f"{', '.join(Path(p).name for p in roles[role])}. "
                        f"Please include only one {role} file.",
            ))
    
    # Step 5: Validate each identified attachment individually
    all_identified = roles["SI"] + roles["BL"]
    
    for path in all_identified:
        # Check extension
        ext_issue = check_file_extension(path)
        if ext_issue:
            issues.append(ext_issue)
            continue  # Skip further checks if format is unsupported
        
        # Check file size
        size_issue = check_file_size(path, inbox)
        if size_issue:
            issues.append(size_issue)
            continue
        
        # Check encoding
        enc_issue = check_file_encoding(path, inbox)
        if enc_issue:
            issues.append(enc_issue)
            continue
        
        # Check document type matches role
        role = _identify_role_by_filename(path)
        if role:
            doc_issue = check_document_type(path, inbox, role)
            if doc_issue:
                issues.append(doc_issue)
    
    # Step 6: Build the identified roles dict (first valid file per role)
    identified: dict[str, str] = {}
    for role in REQUIRED_ROLES:
        if roles[role]:
            identified[role] = roles[role][0]
    
    # Determine if valid (no error-level issues)
    has_errors = any(i.severity == "error" for i in issues)
    
    return ValidationResult(
        valid=not has_errors,
        issues=issues,
        identified_roles=identified,
    )


# ---------------------------------------------------------------------------
# Convenience functions for common checks
# ---------------------------------------------------------------------------

def quick_validate_single(filepath: str, inbox: Any) -> tuple[bool, list[str]]:
    """
    Quick validation of a single file. Returns (is_valid, list_of_messages).
    Useful for simple checks before processing.
    """
    issues: list[str] = []
    
    # Check extension
    ext_issue = check_file_extension(filepath)
    if ext_issue:
        issues.append(ext_issue.message)
    
    # Check size
    size_issue = check_file_size(filepath, inbox)
    if size_issue:
        issues.append(size_issue.message)
    
    # Check encoding
    if not issues:  # Only check encoding if no prior issues
        enc_issue = check_file_encoding(filepath, inbox)
        if enc_issue:
            issues.append(enc_issue.message)
    
    return (len(issues) == 0, issues)


def get_supported_formats() -> str:
    """Return a human-readable string of supported formats."""
    return ", ".join(sorted(SUPPORTED_EXTENSIONS))


# Simple test to verify the module works
if __name__ == "__main__":
    print("Testing Attachment Validation Module...")
    print()
    
    print("Supported formats:", get_supported_formats())
    print()
    
    print("Filename role identification:")
    test_names = [
        "document_SI.txt", "email_BL.txt", "file-si.txt", 
        "data_bl_2024.txt", "random_file.txt", "SI-001.txt",
    ]
    for name in test_names:
        print(f"  '{name}' → role: {_identify_role_by_filename(name)}")
    
    print()
    print("✅ Module loaded successfully!")
    print()
    print("Note: Full validation requires an inbox object with file data.")
    print("This module is designed to be called from the pipeline.")
