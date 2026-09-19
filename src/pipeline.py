"""
End-to-end inbox classification and plain-text document comparison.

Enhanced with two new features:
  Feature 1: Field Normalization - standardizes labels, dates, numbers, units
  Feature 2: Attachment Validation - checks for missing, corrupted, 
             unsupported, or incorrect attachments before processing
"""
from __future__ import annotations
from collections import Counter
from typing import Any

from .classify import BL_COMPARISON, classify_email
from .compare import compare_documents
from .extract import ReviewRequired, extract_attachment, identify_attachments

# Import our new Feature 2: Attachment Validation module
from .attachment_validation import validate_attachments


DEFAULT_RESULT = {
    "status": "OK",
    "review_reason": None,
    "defect_fields": [],
    "has_defect": False,
}


def _process_comparison(
    inbox: Any, 
    email: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Process a single email that requires BL comparison.
    
    Enhanced workflow:
      1. Validate attachments (NEW Feature 2)
         - Check for missing files
         - Check for corrupted/empty files
         - Check for unsupported formats
         - Check for wrong document types
         - Check file sizes
      
      2. Extract fields from attachments
         - Uses enhanced label aliases (Feature 1, in extract.py)
      
      3. Compare documents
         - Uses enhanced field normalization (Feature 1, in normalize.py)
           for dates, units, numbers, text
    """
    paths: dict[str, str] | None = None
    extracted: dict[str, dict[str, str]] = {}
    
    try:
        attachment_list = list(email.get("attachments", []))
        
        # ============================================================
        # NEW Feature 2: Run comprehensive attachment validation
        # ============================================================
        validation = validate_attachments(attachment_list, inbox, require_both=True)
        
        if not validation.valid:
            # Attachments have issues - flag for manual review
            review_reason = validation.get_review_reason()
            error_messages = validation.get_error_messages()
            
            raise ReviewRequired(
                review_reason or "unreadable",
                "attachment_validation_failed",
                f"Attachment validation failed: {'; '.join(error_messages)}",
            )
        
        # Use the validated and identified roles
        paths = validation.identified_roles
        
        # Fallback to old method if new validation didn't identify (shouldn't happen)
        if not paths or "SI" not in paths or "BL" not in paths:
            paths = identify_attachments(attachment_list)
        
        # ============================================================
        # Extract fields (uses enhanced label aliases from Feature 1)
        # ============================================================
        extracted["si"] = extract_attachment(inbox, paths["SI"], "SI")
        extracted["bl"] = extract_attachment(inbox, paths["BL"], "BL")
        
        # ============================================================
        # Compare documents (uses enhanced normalization from Feature 1)
        # ============================================================
        comparison = compare_documents(extracted["si"], extracted["bl"])
        
    except ReviewRequired as exc:
        submission = {
            "status": "NEEDS_REVIEW",
            "review_reason": exc.review_reason,
            "defect_fields": [],
            "has_defect": False,
        }
        detail = {
            "status": "NEEDS_REVIEW",
            "message": "Manual review required.",
            "review_reason": exc.review_reason,
            "internal_reason": exc.internal_reason,
            "detail": exc.detail,
            "attachments": paths or list(email.get("attachments", [])),
            "extracted": extracted,
            "mismatches": [],
        }
        return submission, detail
    
    # Build result from successful comparison
    defect_fields = [item["field"] for item in comparison["mismatches"]]
    
    submission = {
        "status": comparison["status"],
        "review_reason": None,
        "defect_fields": defect_fields,
        "has_defect": bool(defect_fields),
    }
    
    detail = {
        **comparison,
        "review_reason": None,
        "internal_reason": None,
        "attachments": paths,
        "extracted": extracted,
    }
    
    return submission, detail


def process_inbox(
    inbox: Any
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Main pipeline: process all emails in the inbox.
    """
    submission: dict[str, Any] = {}
    internal_results: dict[str, Any] = {}
    
    for email in inbox:
        email_id = email["email_id"]
        
        # Step 1: Classify the email
        classification = classify_email(email)
        category = classification["category"]
        
        # Step 2: Process based on category
        if category == BL_COMPARISON:
            # This needs SI vs BL comparison (uses our new features!)
            outcome, detail = _process_comparison(inbox, email)
        else:
            # Other categories don't need document comparison
            outcome = dict(DEFAULT_RESULT)
            detail = {
                "status": "OK",
                "message": "Classification completed; no document comparison required.",
                "review_reason": None,
                "internal_reason": None,
                "attachments": list(email.get("attachments", [])),
                "extracted": {},
                "mismatches": [],
            }
        
        submission[email_id] = {"category": category, **outcome}
        
        internal_results[email_id] = {
            "email_id": email_id,
            "category": category,
            "classification_rule": classification["rule"],
            **detail,
        }
    
    # Step 3: Generate summary statistics
    category_counts = Counter(record["category"] for record in submission.values())
    status_counts = Counter(record["status"] for record in submission.values())
    review_counts = Counter(
        record["review_reason"]
        for record in submission.values()
        if record["review_reason"] is not None
    )
    
    comparisons = [
        record for record in submission.values() 
        if record["category"] == BL_COMPARISON
    ]
    
    summary = {
        "emails_processed": len(submission),
        "category_counts": dict(sorted(category_counts.items())),
        "comparison_requests": len(comparisons),
        "comparisons_completed": sum(
            r["status"] in {"OK", "MISMATCH"} for r in comparisons
        ),
        "no_mismatch": sum(r["status"] == "OK" for r in comparisons),
        "mismatch": sum(r["status"] == "MISMATCH" for r in comparisons),
        "manual_review": sum(r["status"] == "NEEDS_REVIEW" for r in comparisons),
        "review_reason_counts": dict(sorted(review_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
    }
    
    return submission, internal_results, summary


def validate_submission(submission: dict[str, Any], sample: dict[str, Any]) -> None:
    """
    Validate that the submission format matches the expected schema.
    """
    if set(submission) != set(sample):
        missing = sorted(set(sample) - set(submission))
        extra = sorted(set(submission) - set(sample))
        raise ValueError(
            f"Submission email IDs do not match sample; "
            f"missing={missing}, extra={extra}"
        )
    
    expected_keys = {
        "category", "status", "review_reason", "defect_fields", "has_defect"
    }
    allowed_categories = {
        "BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"
    }
    allowed_statuses = {"OK", "MISMATCH", "NEEDS_REVIEW"}
    allowed_reasons = {
        None, "wrong_doc_type", "missing_attachment", 
        "unreadable", "missing_value"
    }
    
    for email_id, record in submission.items():
        if set(record) != expected_keys:
            raise ValueError(
                f"{email_id} has incorrect keys: {sorted(record)}"
            )
        if record["category"] not in allowed_categories:
            raise ValueError(
                f"{email_id} has invalid category: {record['category']}"
            )
        if record["status"] not in allowed_statuses:
            raise ValueError(
                f"{email_id} has invalid status: {record['status']}"
            )
        if record["review_reason"] not in allowed_reasons:
            raise ValueError(
                f"{email_id} has invalid review_reason: {record['review_reason']}"
            )
        if not isinstance(record["defect_fields"], list):
            raise ValueError(f"{email_id} defect_fields must be a list")
        if not isinstance(record["has_defect"], bool):
            raise ValueError(f"{email_id} has_defect must be a boolean")
        if record["has_defect"] != bool(record["defect_fields"]):
            raise ValueError(
                f"{email_id} has_defect and defect_fields disagree"
            )
