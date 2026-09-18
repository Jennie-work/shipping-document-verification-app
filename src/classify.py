"""Explainable rules for the five required email categories."""

from __future__ import annotations

import re
from typing import Any


BL_COMPARISON = "BL_COMPARISON"
SI_REQUEST = "SI_REQUEST"
INVOICE_QUERY = "INVOICE_QUERY"
GENERAL = "GENERAL"
SPAM = "SPAM"


SPAM_DOMAINS = {
    "crypto-invest.net",
    "secure-mailbox.org",
    "logistics-deals.biz",
    "webmail-verify.co",
    "parcel-track.co",
    "prize-claims.info",
}

SPAM_PHRASES = (
    "claim your $1,000 gift card",
    "guaranteed 300% returns",
    "unpaid customs fee",
    "mailbox has exceeded its storage limit",
    "won a brand new iphone",
    "bank officer with an urgent business proposal",
    "free-iphone-winner.net",
    "webmail-verify.co",
)

INVOICE_SUBJECT_PATTERNS = (
    re.compile(r"\brak\s+billing\b.*\bmissing\s+gr\b", re.IGNORECASE),
    re.compile(r"\brequest\s+to\s+cancel\s+invoice\b", re.IGNORECASE),
    re.compile(r"\blocal\s+charges\s+fob\b", re.IGNORECASE),
    re.compile(r"\bmill\s+d\s*&\s*d\s+charges\b", re.IGNORECASE),
    re.compile(r"\btotal\s+freight\b", re.IGNORECASE),
)


def _clean_subject(subject: str) -> str:
    """Remove a leading reply marker while preserving the subject wording."""
    return re.sub(r"^\s*(?:re[_:]\s*)+", "", subject, flags=re.IGNORECASE).strip()


def classify_email(email: dict[str, Any]) -> dict[str, str]:
    """Return a category and the rule that produced it."""
    sender = str(email.get("from", "")).strip().lower()
    subject = str(email.get("subject", ""))
    body = str(email.get("body", ""))
    clean_subject = _clean_subject(subject)
    subject_lower = clean_subject.lower()
    combined_lower = f"{subject}\n{body}".lower()
    sender_domain = sender.rsplit("@", 1)[-1] if "@" in sender else ""

    if sender_domain in SPAM_DOMAINS:
        return {"category": SPAM, "rule": f"known spam sender domain: {sender_domain}"}
    if any(phrase in combined_lower for phrase in SPAM_PHRASES):
        return {"category": SPAM, "rule": "explicit spam or phishing phrase"}

    for pattern in INVOICE_SUBJECT_PATTERNS:
        if pattern.search(clean_subject):
            return {"category": INVOICE_QUERY, "rule": f"invoice subject pattern: {pattern.pattern}"}

    if re.match(r"^(?:request\s+si|cust\s+si|si\s+needed)(?:\b|\s*[_-])", subject_lower):
        return {"category": SI_REQUEST, "rule": "explicit SI request subject"}
    if re.match(r"^si\s+-", subject_lower):
        return {"category": SI_REQUEST, "rule": "shipping instruction subject"}

    if re.match(r"^(?:to\s+confirm\s+docs|request\s+bl\s+draft|draft\s+bl)(?:\b|\s*[_-])", subject_lower):
        return {"category": BL_COMPARISON, "rule": "explicit BL checking subject"}
    if re.match(r"^(?:aie|afemy|afrt|afptme)\s+-", subject_lower):
        return {"category": BL_COMPARISON, "rule": "coded BL comparison subject"}

    return {"category": GENERAL, "rule": "no specialized category rule matched"}
