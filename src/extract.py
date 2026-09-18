"""Plain-text SI and BL attachment identification and field extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)

LABEL_ALIASES = {
    "shipper": {"shipper", "shipper/exporter", "shipper (principal or seller)"},
    "consignee": {"consignee", "consignee (non-negotiable)", "to the order of"},
    "notify_party": {"notify", "notify party", "notify party/intermediate consignee"},
    "port_of_loading": {"port of loading", "port of loading (pol)", "load port", "pol"},
    "port_of_discharge": {
        "port of discharge",
        "port of discharge (pod)",
        "discharge port",
        "pod",
    },
    "container_count": {
        "no. of containers",
        "no. of containers or packages",
        "total containers",
        "container count",
    },
    "gross_weight_kg": {
        "gross weight (kg)",
        "gross wt (kgs)",
        "gross weight毛重(kgs)",
        "gross weight",
    },
}

PARTY_FIELDS = {"shipper", "consignee", "notify_party"}
MISSING_MARKERS = {"", "n/a", "na", "tba", "tbd", "unknown", "-", "--"}


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", label).strip().casefold()


ALIAS_TO_FIELD = {
    _normalize_label(alias): field
    for field, aliases in LABEL_ALIASES.items()
    for alias in aliases
}


@dataclass
class ReviewRequired(Exception):
    review_reason: str
    internal_reason: str
    detail: str

    def __str__(self) -> str:
        return self.detail


def identify_attachments(paths: list[str]) -> dict[str, str]:
    """Identify SI and BL by their participant-bundle filename suffix."""
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
            f"Could not uniquely identify SI and BL attachments; unknown={unknown}, roles={roles}",
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
    compact = re.sub(r"\s+", " ", value).strip().casefold()
    return compact in MISSING_MARKERS or "???" in compact or "___" in compact


def _validate_document_type(text: str, role: str, path: str) -> None:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    expected = "SHIPPING INSTRUCTION" if role == "SI" else "BILL OF LADING"
    if expected not in first_line.upper():
        raise ReviewRequired(
            "wrong_doc_type",
            "wrong_document_type",
            f"{path} was assigned as {role}, but its first line is {first_line!r}",
        )


def parse_fields(text: str, role: str, path: str) -> dict[str, str]:
    _validate_document_type(text, role, path)
    extracted: dict[str, str] = {}
    active_party_field: str | None = None

    for raw_line in text.splitlines():
        if active_party_field and raw_line[:1].isspace() and raw_line.strip():
            extracted[active_party_field] = f"{extracted[active_party_field]} {raw_line.strip()}".strip()
            continue

        active_party_field = None
        if ":" not in raw_line:
            continue
        label, value = raw_line.split(":", 1)
        field = ALIAS_TO_FIELD.get(_normalize_label(label))
        if not field:
            continue

        value = value.strip()
        if field in extracted and extracted[field] != value:
            raise ReviewRequired(
                "unreadable",
                "duplicate_conflicting_field",
                f"{path} contains conflicting values for {field}",
            )
        extracted[field] = value
        if field in PARTY_FIELDS:
            active_party_field = field

    missing = [field for field in FIELDS if field not in extracted or _looks_missing(extracted[field])]
    if missing:
        raise ReviewRequired(
            "missing_value",
            "missing_required_value",
            f"{path} is missing reliable value(s): {', '.join(missing)}",
        )
    return extracted


def extract_attachment(inbox: Any, path: str, role: str) -> dict[str, str]:
    """Read and parse one supported plain-text attachment."""
    if Path(path).suffix.casefold() != ".txt":
        raise ReviewRequired(
            "unreadable",
            "unsupported_attachment_format",
            f"Basic version supports .txt only; cannot read {path}",
        )
    try:
        raw = inbox.read_bytes(path)
    except (OSError, ValueError) as exc:
        raise ReviewRequired(
            "unreadable",
            "attachment_read_failed",
            f"Could not read {path}: {exc}",
        ) from exc
    if not raw:
        raise ReviewRequired("unreadable", "empty_attachment", f"Attachment is empty: {path}")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ReviewRequired(
            "unreadable",
            "attachment_decode_failed",
            f"Could not decode {path} as UTF-8",
        ) from exc
    return parse_fields(text, role, path)
